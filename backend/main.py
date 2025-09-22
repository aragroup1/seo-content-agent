import os
import json
import asyncio
import re
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Boolean, Text, JSON
from sqlalchemy.orm import declarative_base, Session, sessionmaker
from dotenv import load_dotenv
from openai import OpenAI
import httpx
import logging
import traceback

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("main"); shopify_logger = logging.getLogger("shopify"); openai_logger = logging.getLogger("openai"); db_logger = logging.getLogger("database"); api_logger = logging.getLogger("api"); processor_logger = logging.getLogger("processor")
load_dotenv()

# --- Database ---
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"): DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else: DATABASE_URL = "sqlite:///./seo_agent.db"
engine = create_engine(DATABASE_URL); SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine); Base = declarative_base()

# --- Models ---
class Product(Base): __tablename__ = "products"; id=Column(Integer,primary_key=True); shopify_id=Column(String,unique=True,index=True); title=Column(String); handle=Column(String,nullable=True); status=Column(String,default="pending"); seo_written=Column(Boolean,default=False); created_at=Column(DateTime,default=datetime.utcnow); updated_at=Column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow); processed_at=Column(DateTime,nullable=True)
class Collection(Base): __tablename__ = "collections"; id=Column(Integer,primary_key=True); shopify_id=Column(String,unique=True,index=True); title=Column(String); handle=Column(String,nullable=True); products_count=Column(Integer,default=0); status=Column(String,default="pending"); seo_written=Column(Boolean,default=False); created_at=Column(DateTime,default=datetime.utcnow); updated_at=Column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow); processed_at=Column(DateTime,nullable=True)
class SEOContent(Base): __tablename__ = "seo_content"; id=Column(Integer,primary_key=True); item_id=Column(String,index=True); item_type=Column(String); item_title=Column(String); seo_title=Column(String); meta_description=Column(String,nullable=True); ai_description=Column(Text,nullable=True); generated_at=Column(DateTime,default=datetime.utcnow)
class SystemState(Base): __tablename__ = "system_state"; id=Column(Integer,primary_key=True); is_paused=Column(Boolean,default=False); auto_pause_triggered=Column(Boolean,default=False); last_scan=Column(DateTime,nullable=True); products_found_in_last_scan=Column(Integer,default=0); collections_found_in_last_scan=Column(Integer,default=0); total_items_processed=Column(Integer,default=0)
try: Base.metadata.create_all(bind=engine); db_logger.info("✅ DB tables verified")
except Exception as e: db_logger.error(f"❌ DB error: {e}")

# --- Helpers ---
def get_db():
    db = SessionLocal();
    try: yield db
    finally: db.close()
def init_system_state(db: Session):
    state = db.query(SystemState).first()
    if not state: state=SystemState(is_paused=False); db.add(state); db.commit()
    return state
def clean_input_text(text: str) -> str:
    if not text: return ""
    cleaned = re.sub(r'^KATEX_INLINE_OPEN.*KATEX_INLINE_CLOSE\s*', '', text)
    shipping_phrases = ["Large Letter Rate", "Big Parcel Rate", "Small Parcel Rate", "Parcel Rate"]
    pattern = r'\s*KATEX_INLINE_OPEN(?:' + '|'.join(shipping_phrases) + r')KATEX_INLINE_CLOSE\s*|\s*(?:' + '|'.join(shipping_phrases) + r')\s*'
    cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()
def sanitize_output_title(title: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'[^a-zA-Z0-9\s]', '', title)).strip()
def html_to_text(html_content: str) -> str:
    if not html_content: return ""
    return re.sub('<[^<]+?>', ' ', html_content).strip()

# --- Services ---
class ShopifyService:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.shop_domain = os.getenv("SHOPIFY_SHOP_DOMAIN"); self.access_token = os.getenv("SHOPIFY_ACCESS_TOKEN"); self.api_version = "2024-01"; self.configured = bool(self.shop_domain and self.access_token)
        if self.configured: self.base_url = f"https://{self.shop_domain}/admin/api/{self.api_version}"; self.headers = {"X-Shopify-Access-Token": self.access_token, "Content-Type": "application/json"}
    async def get_all_paginated_resources(self, endpoint: str, resource_key: str, fields: str):
        if not self.configured: return []
        resources, page_info, page_count = [], None, 1
        url = f"{self.base_url}/{endpoint}.json?limit=250&fields={fields}"
        while url:
            try:
                resp = await self.client.get(url, headers=self.headers, timeout=45)
                resp.raise_for_status()
                data = resp.json().get(resource_key, [])
                resources.extend(data)
                shopify_logger.info(f"Fetched page {page_count} ({len(data)} items) from {endpoint}.")
                link_header = resp.headers.get("Link")
                match = re.search(r'<[^>]*[?&]page_info=([^&>]+)[^>]*>;\s*rel="next"', link_header or "")
                page_info = match.group(1) if match else None
                if page_info: url = f"{self.base_url}/{endpoint}.json?limit=250&fields={fields}&page_info={page_info}"; page_count += 1
                else: url = None
            except Exception as e: shopify_logger.error(f"Failed to fetch page {page_count} from {endpoint}: {e}"); break
        return resources
    async def get_all_products(self): return await self.get_all_paginated_resources("products", "products", "id,title")
    async def get_all_collections(self):
        smart = await self.get_all_paginated_resources("smart_collections", "smart_collections", "id,title,products_count")
        custom = await self.get_all_paginated_resources("custom_collections", "custom_collections", "id,title,products_count")
        return smart + custom
    async def get_product_details(self, product_id: str):
        if not self.configured: return None
        try: resp = await self.client.get(f"{self.base_url}/products/{product_id}.json", headers=self.headers, params={"fields":"id,title,body_html"}, timeout=20); resp.raise_for_status(); return resp.json().get("product")
        except Exception as e: shopify_logger.error(f"Failed to get details for product {product_id}: {e}"); return None
    async def update_product(self, product_id: str, title: Optional[str]=None, description: Optional[str]=None, meta_title: Optional[str]=None, meta_description: Optional[str]=None):
        if not self.configured: return False
        payload={"product":{"id":int(product_id)}}; metafields=[]
        if title: payload["product"]["title"]=title
        if description: payload["product"]["body_html"]=description
        if meta_title: metafields.append({"key":"title_tag","namespace":"global","value":meta_title,"type":"string"})
        if meta_description: metafields.append({"key":"description_tag","namespace":"global","value":meta_description,"type":"string"})
        if metafields: payload["product"]["metafields"]=metafields
        try: resp = await self.client.put(f"{self.base_url}/products/{product_id}.json", headers=self.headers, json=payload, timeout=30); resp.raise_for_status(); return True
        except Exception as e: shopify_logger.error(f"Shopify update failed for product {product_id}: {e}"); return False

class SmartAIService:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.openai_configured = bool(self.api_key)
        self.model = "gpt-3.5-turbo"
        if self.openai_configured: self.openai_headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
    async def generate_full_content(self, title: str, existing_description: str) -> dict:
        if not self.openai_configured: return {}
        prompt = f'Act as an expert SEO copy editor for the product "{title}". Use the existing description for context, but create a better, more complete version. Generate: 1. A new `title` (max 60 characters). 2. A new `description` in HTML (1-2 paragraphs, 100-150 words). Format the response as a valid JSON object with "title" and "description" keys. Existing Description: "{existing_description}"'
        payload = {"model": self.model, "messages": [{"role":"system","content":"You are a concise and professional SEO copywriter who improves existing text. Ensure your response is valid JSON."},{"role":"user","content":prompt}], "temperature":0.7, "max_tokens":400, "response_format":{"type":"json_object"}}
        try:
            resp = await self.client.post("https://api.openai.com/v1/chat/completions", headers=self.openai_headers, json=payload, timeout=60)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e: openai_logger.error(f"AI full content error for '{title}': {e}"); return {}
    async def generate_meta_only_content(self, title: str, existing_description: str) -> dict:
        if not self.openai_configured: return {}
        prompt = f'Based on the product title "{title}" and this existing description: "{existing_description[:1000]}...", create: 1. A new main `title` for the product page (descriptive, 60-70 characters). 2. A new SEO `meta_title` for search engines (60-70 characters). 3. A compelling `meta_description` (max 155 chars). Format the response as a valid JSON object with "title", "meta_title", and "meta_description" keys.'
        payload = {"model": self.model, "messages": [{"role":"system","content":"You are an expert SEO copywriter creating metadata. Ensure your response is valid JSON."},{"role":"user","content":prompt}], "temperature":0.7, "max_tokens":300, "response_format":{"type":"json_object"}}
        try:
            resp = await self.client.post("https://api.openai.com/v1/chat/completions", headers=self.openai_headers, json=payload, timeout=60)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e: openai_logger.error(f"AI meta only error for '{title}': {e}"); return {}

# --- App Context & Lifespan ---
app_state = {}
@asyncio.contextmanager
async def lifespan(app: FastAPI):
    app_state["http_client"] = httpx.AsyncClient()
    yield
    await app_state["http_client"].aclose()

app = FastAPI(title="AI SEO Content Agent", version="STABLE-FINAL", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- Background Processing ---
async def process_pending_items(db: Session, http_client: httpx.AsyncClient):
    shopify = ShopifyService(http_client); ai_service = SmartAIService(http_client)
    processor_logger.info("="*60 + "\n🚀 STARTING SMART CONTENT OPTIMIZATION RUN\n" + "="*60)
    WORD_COUNT_THRESHOLD = int(os.getenv("DESCRIPTION_WORD_COUNT_THRESHOLD", 100))
    pending_products = db.query(Product).filter(Product.status.in_(['pending', 'failed'])).limit(5).all()
    processor_logger.info(f"Found {len(pending_products)} pending products to process.")
    for product_stub in pending_products:
        original_title = product_stub.title
        try:
            product_stub.status = 'processing'; db.commit()
            full_product = await shopify.get_product_details(product_stub.shopify_id)
            if not full_product: raise Exception("Could not fetch full product details")
            existing_desc = full_product.get('body_html', '')
            cleaned_title = clean_input_text(original_title); cleaned_desc_text = clean_input_text(html_to_text(existing_desc))
            word_count = len(cleaned_desc_text.split())
            processor_logger.info(f"⚙️ Processing: '{original_title}' -> '{cleaned_title}' (desc words: {word_count})")
            content_str = ""
            if word_count >= WORD_COUNT_THRESHOLD:
                processor_logger.info(f"🎯 Meta Only Mode")
                content_str = await ai_service.generate_meta_only_content(cleaned_title, cleaned_desc_text)
                content = json.loads(content_str)
                if not content or "title" not in content: raise Exception("Meta-only AI output invalid")
                sanitized_title = sanitize_output_title(content["title"])
                success = await shopify.update_product(product_stub.shopify_id, title=sanitized_title, meta_title=content.get("meta_title"), meta_description=content.get("meta_description"))
            else:
                processor_logger.info(f"✍️ Full Rewrite Mode")
                content_str = await ai_service.generate_full_content(cleaned_title, cleaned_desc_text)
                content = json.loads(content_str)
                if not content or "title" not in content: raise Exception("Full-rewrite AI output invalid")
                sanitized_title = sanitize_output_title(content["title"])
                success = await shopify.update_product(product_stub.shopify_id, title=sanitized_title, description=content.get("description"))
            if not success: raise Exception("Shopify API update failed.")
            product_stub.status = 'completed'; product_stub.seo_written = True; product_stub.processed_at = datetime.utcnow()
            db.add(SEOContent(item_id=product_stub.shopify_id, item_type='product', item_title=sanitized_title, seo_title=content.get("meta_title", sanitized_title), ai_description=content.get("description"), meta_description=content.get("meta_description")))
            processor_logger.info(f"✅ Completed: {sanitized_title}")
        except Exception as e:
            product_stub.status = 'failed'; processor_logger.error(f"❌ Failed: {original_title} -> {e}"); traceback.print_exc()
        finally: db.commit(); await asyncio.sleep(2)
    processor_logger.info("🏁 Background processing run finished.")

# --- API Endpoints ---
@app.get("/")
def root(): return {"status": "ok"}

@app.get("/api/health")
def health(): return {"ok": True, "service": "backend", "time": datetime.utcnow().isoformat()}

@app.post("/api/scan")
async def scan_all(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    state = db.query(SystemState).first() or init_system_state(db)
    if state.is_paused: return {"error": "System is paused"}
    shopify = ShopifyService(app_state["http_client"])
    products = await shopify.get_all_products(); new_products = 0
    existing_pids = {r[0] for r in db.query(Product.shopify_id).all()}
    for p in products:
        if str(p.get('id')) not in existing_pids: db.add(Product(shopify_id=str(p.get('id')), title=p.get('title'), status='pending')); new_products += 1
    db.commit()
    return {"products_found": new_products, "message": "Scan complete."}

@app.post("/api/process-queue")
async def trigger_processing(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    state = db.query(SystemState).first()
    if state and state.is_paused: return {"error":"System is paused"}
    background_tasks.add_task(process_pending_items, db, app_state["http_client"])
    return {"message": "Processing task started."}

@app.get("/api/dashboard")
async def get_dashboard(db: Session = Depends(get_db)):
    state = db.query(SystemState).first() or init_system_state(db)
    total_products = db.query(Product).count()
    completed = db.query(Product).filter(Product.status == "completed").count()
    pending = db.query(Product).filter(Product.status.in_(["pending", "failed"])).count()
    recent = db.query(Product).order_by(Product.updated_at.desc()).limit(5).all()
    return {
        "system": {"is_paused": state.is_paused, "last_scan": state.last_scan.isoformat() if state.last_scan else None},
        "stats": {"products": {"total": total_products, "completed": completed, "pending": pending}},
        "recent_activity": [{'id': p.shopify_id, 'title': p.title, 'status': p.status, 'updated': p.updated_at.isoformat()} for p in recent]
    }

@app.post("/api/pause")
async def toggle_pause(db: Session = Depends(get_db)):
    state = db.query(SystemState).first() or init_system_state(db)
    state.is_paused = not state.is_paused; db.commit()
    return {"is_paused": state.is_paused}

@app.get("/api/logs")
async def get_logs(db: Session = Depends(get_db)):
    logs = db.query(SEOContent).order_by(SEOContent.generated_at.desc()).limit(50).all()
    return {"logs": [{'item_id': log.item_id, 'item_type': log.item_type, 'item_title': log.item_title, 'generated_at': log.generated_at.isoformat()} for log in logs]}
