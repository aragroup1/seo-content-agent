import os
import json
import asyncio
import re
from datetime import datetime
from typing import Optional, Dict

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Boolean, Text
from sqlalchemy.orm import declarative_base, Session, sessionmaker
from dotenv import load_dotenv
from openai import OpenAI
import httpx
import logging
import traceback

# ------------------- Logging -------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("main")
shopify_logger = logging.getLogger("shopify")
openai_logger = logging.getLogger("openai")
db_logger = logging.getLogger("database")
api_logger = logging.getLogger("api")
processor_logger = logging.getLogger("processor")

load_dotenv()

# ------------------- Database -------------------
DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///./seo_agent.db"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    shopify_id = Column(String, unique=True, index=True)
    title = Column(String)
    handle = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending|processing|completed|failed
    seo_written = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

class Collection(Base):
    __tablename__ = "collections"
    id = Column(Integer, primary_key=True)
    shopify_id = Column(String, unique=True, index=True)
    title = Column(String)
    handle = Column(String, nullable=True)
    products_count = Column(Integer, default=0)
    status = Column(String, default="pending")
    seo_written = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

class SEOContent(Base):
    __tablename__ = "seo_content"
    id = Column(Integer, primary_key=True)
    item_id = Column(String, index=True)
    item_type = Column(String)  # product|collection
    item_title = Column(String)
    seo_title = Column(String)  # meta_title or title when full rewrite
    meta_description = Column(String, nullable=True)
    ai_description = Column(Text, nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow)

class SystemState(Base):
    __tablename__ = "system_state"
    id = Column(Integer, primary_key=True)
    is_paused = Column(Boolean, default=False)
    auto_pause_triggered = Column(Boolean, default=False)
    last_scan = Column(DateTime, nullable=True)
    products_found_in_last_scan = Column(Integer, default=0)
    collections_found_in_last_scan = Column(Integer, default=0)
    total_items_processed = Column(Integer, default=0)

Base.metadata.create_all(bind=engine)
db_logger.info("✅ Database tables created/verified successfully")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_system_state(db: Session):
    state = db.query(SystemState).first()
    if not state:
        state = SystemState(is_paused=False)
        db.add(state)
        db.commit()
    return state

# ------------------- Cleaners -------------------
SHIPPING_PHRASES = ["Large Letter Rate", "Big Parcel Rate", "Small Parcel Rate", "Parcel Rate"]

def clean_input_text(text: str) -> str:
    if not text:
        return ""
    t = text
    t = re.sub(r'#?value!?', '', t, flags=re.IGNORECASE)  # remove excel artifacts like #VALUE!
    t = re.sub(r'^KATEX_INLINE_OPEN.*KATEX_INLINE_CLOSE\s*', '', t)  # remove leading (M), (S), etc
    patt = r'\s*KATEX_INLINE_OPEN(?:' + '|'.join(map(re.escape, SHIPPING_PHRASES)) + r')KATEX_INLINE_CLOSE\s*|\s*(?:' + '|'.join(map(re.escape, SHIPPING_PHRASES)) + r')\s*'
    t = re.sub(patt, ' ', t, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', t).strip()

def sanitize_output_title(title: str) -> str:
    if not title:
        return ""
    sanitized = re.sub(r'[^a-zA-Z0-9\s]', '', title)
    return re.sub(r'\s+', ' ', sanitized).strip()

def html_to_text(html: str) -> str:
    if not html:
        return ""
    return re.sub('<[^<]+?>', ' ', html).strip()

# ------------------- Shopify Service -------------------
class ShopifyService:
    def __init__(self):
        self.shop_domain = os.getenv("SHOPIFY_SHOP_DOMAIN")
        self.access_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
        self.api_version = "2024-01"
        self.configured = bool(self.shop_domain and self.access_token)
        if self.configured:
            self.base_url = f"https://{self.shop_domain}/admin/api/{self.api_version}"
            self.headers = {"X-Shopify-Access-Token": self.access_token, "Content-Type": "application/json"}
        else:
            shopify_logger.warning("⚠️ Shopify credentials not configured")

    async def get_products_page(self, limit=250, since_id=None):
        params = {"limit": limit, "fields": "id,title,handle"}
        if since_id:
            params["since_id"] = since_id
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{self.base_url}/products.json", headers=self.headers, params=params, timeout=45)
            r.raise_for_status()
            return r.json().get("products", [])

    async def get_all_products(self, limit=250):
        if not self.configured:
            return []
        products, since_id, page = [], None, 1
        while True:
            try:
                batch = await self.get_products_page(limit=limit, since_id=since_id)
                shopify_logger.info(f"Fetched {len(batch)} products (page {page})")
                if not batch:
                    break
                products.extend(batch)
                since_id = batch[-1]["id"]
                page += 1
                if len(products) >= 500000:
                    break
            except httpx.HTTPStatusError as e:
                shopify_logger.error(f"Shopify products page failed: {e}")
                break
        return products

    async def get_collections_page(self, endpoint: str, page_info: Optional[str] = None, limit=250):
        params = {"limit": limit, "fields": "id,title,handle,products_count"}
        if page_info:
            params["page_info"] = page_info
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{self.base_url}/{endpoint}.json", headers=self.headers, params=params, timeout=45)
            r.raise_for_status()
            return r

    def _parse_next_page_info(self, link_header: Optional[str]) -> Optional[str]:
        if not link_header:
            return None
        m = re.search(r'<[^>]*[?&]page_info=([^&>]+)[^>]*>;\s*rel="next"', link_header)
        return m.group(1) if m else None

    async def get_all_collections(self, limit=250):
        if not self.configured:
            return []
        collections = []
        # smart collections
        page_info = None
        while True:
            try:
                resp = await self.get_collections_page("smart_collections", page_info=page_info, limit=limit)
                data = resp.json().get("smart_collections", [])
                collections.extend(data)
                next_pi = self._parse_next_page_info(resp.headers.get("Link"))
                if not next_pi:
                    break
                page_info = next_pi
            except httpx.HTTPStatusError as e:
                shopify_logger.error(f"Shopify smart_collections page failed: {e}")
                break
        # custom collections
        page_info = None
        while True:
            try:
                resp = await self.get_collections_page("custom_collections", page_info=page_info, limit=limit)
                data = resp.json().get("custom_collections", [])
                collections.extend(data)
                next_pi = self._parse_next_page_info(resp.headers.get("Link"))
                if not next_pi:
                    break
                page_info = next_pi
            except httpx.HTTPStatusError as e:
                shopify_logger.error(f"Shopify custom_collections page failed: {e}")
                break

        shopify_logger.info(f"Total collections fetched: {len(collections)}")
        return collections

    async def get_product_details(self, product_id: str):
        if not self.configured:
            return None
        url = f"{self.base_url}/products/{product_id}.json"
        async with httpx.AsyncClient() as c:
            try:
                r = await c.get(url, headers=self.headers, params={"fields": "id,title,body_html,product_type,vendor"}, timeout=30)
                r.raise_for_status()
                return r.json().get("product")
            except Exception as e:
                shopify_logger.error(f"Failed to get product details {product_id}: {e}")
                return None

    async def update_product(self, product_id: str, title: Optional[str] = None, description: Optional[str] = None,
                             meta_title: Optional[str] = None, meta_description: Optional[str] = None):
        if not self.configured:
            return False
        payload = {"product": {"id": int(product_id)}}
        metafields = []
        if title:
            payload["product"]["title"] = title
        if description:
            payload["product"]["body_html"] = description
        if meta_title:
            metafields.append({"key": "title_tag", "namespace": "global", "value": meta_title, "type": "string"})
        if meta_description:
            metafields.append({"key": "description_tag", "namespace": "global", "value": meta_description, "type": "string"})
        if metafields:
            payload["product"]["metafields"] = metafields

        async with httpx.AsyncClient() as c:
            try:
                resp = await c.put(f"{self.base_url}/products/{product_id}.json",
                                   headers=self.headers, json=payload, timeout=45)
                resp.raise_for_status()
                shopify_logger.info(f"✅ Shopify update successful for product {product_id}")
                return True
            except Exception as e:
                shopify_logger.error(f"❌ Shopify update failed for product {product_id}: {e}")
                return False

# ------------------- AI Service (JSON prompts) -------------------
class SmartAIService:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=api_key) if api_key else None
        self.model = "gpt-3.5-turbo"
        if self.client:
            openai_logger.info("✅ AI Service configured - Smart Mode (model: gpt-3.5-turbo)")

    async def generate_full_content(self, title: str, existing_description: str) -> dict:
        if not self.client:
            return {}
        prompt = f'''
Act as an expert SEO copy editor for the product "{title}". Use the existing description (below) as context, but create a better, more complete version.

Return a JSON object with exactly these keys:
- "title": descriptive page title, aim ~60–70 characters, no special characters
- "description": HTML with 1–2 short paragraphs, total 100–150 words

Existing Description:
"{existing_description}"
'''
        try:
            resp = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=self.model,
                messages=[
                    {"role": "system", "content": "You write concise, clean e‑commerce copy. Return valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.6,
                max_tokens=420,
                response_format={"type": "json_object"}
            )
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            openai_logger.error(f"AI full content error for '{title}': {e}")
            return {}

    async def generate_meta_only_content(self, title: str, existing_description: str) -> dict:
        if not self.client:
            return {}
        prompt = f'''
Based on the product title "{title}" and the existing description (below), create ONLY the page title and meta tags.

Return a JSON object with exactly these keys:
- "title": descriptive page title, aim ~60–70 characters, no special characters
- "meta_title": SEO title for search engines, ~60–70 characters
- "meta_description": SEO description <= 155 characters

Existing Description:
"{existing_description[:1000]}"
'''
        try:
            resp = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=self.model,
                messages=[
                    {"role": "system", "content": "You write concise, clean SEO metadata. Return valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.6,
                max_tokens=280,
                response_format={"type": "json_object"}
            )
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            openai_logger.error(f"AI meta-only error for '{title}': {e}")
            return {}

shopify = ShopifyService()
ai_service = SmartAIService()

# ------------------- Bulk Scan -------------------
async def bulk_scan(db: Session) -> Dict[str, int]:
    products = await shopify.get_all_products(limit=250)
    collections = await shopify.get_all_collections(limit=250)

    new_p = 0
    for prod in products:
        sid = str(prod.get("id"))
        title = prod.get("title") or ""
        handle = prod.get("handle") or ""
        if not db.query(Product).filter(Product.shopify_id == sid).first():
            db.add(Product(shopify_id=sid, title=title, handle=handle, status="pending"))
            new_p += 1

    new_c = 0
    for col in collections:
        sid = str(col.get("id"))
        title = col.get("title") or ""
        handle = col.get("handle") or ""
        count = int(col.get("products_count", 0) or 0)
        if not db.query(Collection).filter(Collection.shopify_id == sid).first():
            db.add(Collection(shopify_id=sid, title=title, handle=handle, products_count=count, status="pending"))
            new_c += 1

    state = db.query(SystemState).first() or init_system_state(db)
    state.last_scan = datetime.utcnow()
    state.products_found_in_last_scan = new_p
    state.collections_found_in_last_scan = new_c
    db.commit()

    api_logger.info(f"Bulk scan added: {new_p} products, {new_c} collections")
    return {"new_products": new_p, "new_collections": new_c}

# ------------------- Processing -------------------
async def process_pending_items(db: Session):
    processor_logger.info("=" * 60 + "\n🚀 STARTING SMART CONTENT OPTIMIZATION RUN\n" + "=" * 60)
    WORD_COUNT_THRESHOLD = int(os.getenv("DESCRIPTION_WORD_COUNT_THRESHOLD", "100"))
    processor_logger.info(f"Smart Mode Active: Word count threshold is {WORD_COUNT_THRESHOLD} words.")

    pending_products = db.query(Product).filter(Product.status.in_(["pending", "failed"])).limit(5).all()
    processor_logger.info(f"Found {len(pending_products)} pending products to process.")

    for p in pending_products:
        original_title = p.title
        try:
            p.status = "processing"
            db.commit()

            details = await shopify.get_product_details(p.shopify_id)
            if not details:
                raise Exception("Failed to load product details")

            existing_html = details.get("body_html", "")
            cleaned_title = sanitize_output_title(clean_input_text(original_title))
            cleaned_desc_text = clean_input_text(html_to_text(existing_html))
            word_count = len(cleaned_desc_text.split())

            processor_logger.info(f"⚙️ Processing: '{original_title}' -> '{cleaned_title}' (desc words: {word_count})")

            if word_count >= WORD_COUNT_THRESHOLD:
                # META ONLY MODE
                content = await ai_service.generate_meta_only_content(cleaned_title, cleaned_desc_text)
                if not content or "title" not in content or "meta_title" not in content or "meta_description" not in content:
                    raise Exception("Meta-only AI output invalid")
                title_new = sanitize_output_title(content["title"])
                ok = await shopify.update_product(
                    p.shopify_id,
                    title=title_new,
                    meta_title=content["meta_title"],
                    meta_description=content["meta_description"]
                )
                if not ok:
                    raise Exception("Shopify meta-only update failed")
                record = SEOContent(
                    item_id=p.shopify_id, item_type="product",
                    item_title=title_new, seo_title=content["meta_title"],
                    meta_description=content["meta_description"]
                )
                db.add(record)
            else:
                # FULL REWRITE MODE
                content = await ai_service.generate_full_content(cleaned_title, cleaned_desc_text)
                if not content or "title" not in content or "description" not in content:
                    raise Exception("Full-rewrite AI output invalid")
                title_new = sanitize_output_title(content["title"])
                desc_new = content["description"]
                ok = await shopify.update_product(
                    p.shopify_id,
                    title=title_new,
                    description=desc_new
                )
                if not ok:
                    raise Exception("Shopify full-rewrite update failed")
                record = SEOContent(
                    item_id=p.shopify_id, item_type="product",
                    item_title=title_new, seo_title=title_new,
                    ai_description=desc_new
                )
                db.add(record)

            p.status = "completed"
            p.seo_written = True
            p.processed_at = datetime.utcnow()
            db.commit()
            processor_logger.info(f"✅ Completed: {title_new}")

        except Exception as e:
            p.status = "failed"
            db.commit()
            processor_logger.error(f"❌ Failed: {original_title} -> {e}")
            processor_logger.error(traceback.format_exc())
        finally:
            await asyncio.sleep(2)

    processor_logger.info("🏁 Background processing run finished.")

# ------------------- FastAPI app -------------------
app = FastAPI(title="AI SEO Content Agent", version="auto-worker-1.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or lock to your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/api/health")
def health():
    return {"ok": True, "service": "backend", "time": datetime.utcnow().isoformat()}

@app.post("/api/scan")
async def scan_all(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    state = db.query(SystemState).first() or init_system_state(db)
    if state.is_paused:
        return {"error": "System is paused"}
    try:
        counts = await bulk_scan(db)
        if not state.is_paused and (counts["new_products"] + counts["new_collections"]) > 0:
            background_tasks.add_task(process_pending_items, db)
        return {"queued": counts, "paused": state.is_paused}
    except Exception as e:
        api_logger.error(f"Scan failed: {e}")
        api_logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/process-queue")
async def trigger_processing(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    state = db.query(SystemState).first()
    if state and state.is_paused:
        return {"error": "System is paused"}
    background_tasks.add_task(process_pending_items, db)
    return {"message": "Processing started"}

@app.get("/api/dashboard")
async def get_dashboard(db: Session = Depends(get_db)):
    state = db.query(SystemState).first() or init_system_state(db)
    total_products = db.query(Product).count()
    completed_products = db.query(Product).filter(Product.status == "completed").count()
    pending_products = db.query(Product).filter(Product.status == "pending").count()
    total_collections = db.query(Collection).count()
    completed_collections = db.query(Collection).filter(Collection.status == "completed").count()
    pending_collections = db.query(Collection).filter(Collection.status == "pending").count()
    recent_products = db.query(Product).order_by(Product.updated_at.desc()).limit(5).all()
    recent_collections = db.query(Collection).order_by(Collection.updated_at.desc()).limit(5).all()
    recent_activity = [
        {"id": p.shopify_id, "title": p.title, "type": "product", "status": p.status, "updated": p.updated_at.isoformat() if p.updated_at else None}
        for p in recent_products
    ] + [
        {"id": c.shopify_id, "title": c.title, "type": "collection", "status": c.status, "updated": c.updated_at.isoformat() if c.updated_at else None}
        for c in recent_collections
    ]
    recent_activity.sort(key=lambda x: x["updated"] or "", reverse=True)
    return {
        "system": {
            "is_paused": state.is_paused,
            "auto_pause_triggered": state.auto_pause_triggered,
            "last_scan": state.last_scan.isoformat() if state.last_scan else None,
            "products_found_in_last_scan": state.products_found_in_last_scan,
            "collections_found_in_last_scan": state.collections_found_in_last_scan
        },
        "stats": {
            "products": {"total": total_products, "completed": completed_products, "pending": pending_products},
            "collections": {"total": total_collections, "completed": completed_collections, "pending": pending_collections},
            "total_completed": completed_products + completed_collections
        },
        "recent_activity": recent_activity[:10]
    }

@app.post("/api/pause")
async def toggle_pause(db: Session = Depends(get_db)):
    state = db.query(SystemState).first() or init_system_state(db)
    state.is_paused = not state.is_paused
    state.auto_pause_triggered = False
    db.commit()
    return {"is_paused": state.is_paused}

from pydantic import BaseModel
class ManualQueueItem(BaseModel):
    item_id: str
    item_type: str = "product"
    title: str
    url: Optional[str] = None
    reason: str = "revision"

@app.get("/api/manual-queue")
async def manual_queue_list():
    return {"items": []}

@app.post("/api/manual-queue")
async def manual_queue_add(item: ManualQueueItem):
    return {"message": "queued", "item": item.dict()}

@app.delete("/api/manual-queue/{qid}")
async def manual_queue_delete(qid: int):
    return {"message": "removed", "id": qid}
