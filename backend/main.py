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

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("main")
shopify_logger = logging.getLogger("shopify")
openai_logger = logging.getLogger("openai")
db_logger = logging.getLogger("database")
api_logger = logging.getLogger("api")
processor_logger = logging.getLogger("processor")

load_dotenv()

# --- Database Setup ---
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    DATABASE_URL = "sqlite:///./seo_agent.db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Database Models ---
class Product(Base):
    __tablename__ = "products"
    id=Column(Integer,primary_key=True,index=True); shopify_id=Column(String,unique=True,index=True); title=Column(String); handle=Column(String); product_type=Column(String,nullable=True); vendor=Column(String,nullable=True); tags=Column(Text,nullable=True); status=Column(String,default="pending"); seo_written=Column(Boolean,default=False); created_at=Column(DateTime,default=datetime.utcnow); updated_at=Column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow); processed_at=Column(DateTime,nullable=True)

class Collection(Base):
    __tablename__ = "collections"
    id=Column(Integer,primary_key=True,index=True); shopify_id=Column(String,unique=True,index=True); title=Column(String); handle=Column(String); products_count=Column(Integer,default=0); status=Column(String,default="pending"); seo_written=Column(Boolean,default=False); created_at=Column(DateTime,default=datetime.utcnow); updated_at=Column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow); processed_at=Column(DateTime,nullable=True)

class SEOContent(Base):
    __tablename__ = "seo_content"
    id=Column(Integer,primary_key=True,index=True); item_id=Column(String,index=True); item_type=Column(String); item_title=Column(String); seo_title=Column(String); ai_description=Column(Text); generated_at=Column(DateTime,default=datetime.utcnow)

class SystemState(Base):
    __tablename__ = "system_state"
    id=Column(Integer,primary_key=True); is_paused=Column(Boolean,default=False); auto_pause_triggered=Column(Boolean,default=False); last_scan=Column(DateTime,nullable=True); products_found_in_last_scan=Column(Integer,default=0); collections_found_in_last_scan=Column(Integer,default=0); total_items_processed=Column(Integer,default=0)

try:
    Base.metadata.create_all(bind=engine)
    db_logger.info("✅ Database tables created/verified successfully")
except Exception as e:
    db_logger.error(f"❌ Database error on table creation: {e}")

# --- Pydantic Models & DB Helpers ---
def get_db():
    db = SessionLocal();
    try: yield db
    finally: db.close()

def init_system_state(db: Session):
    state = db.query(SystemState).first()
    if not state: state=SystemState(is_paused=False); db.add(state); db.commit()
    return state

# --- Data Cleaning and Sanitization Helpers ---
def clean_input_title(title: str) -> str:
    """Removes prefixes like (M), (S), (Parcel Rate) from titles before sending to AI."""
    cleaned_title = re.sub(r'^KATEX_INLINE_OPEN.*KATEX_INLINE_CLOSE\s*', '', title)
    return cleaned_title.strip()

def sanitize_output_title(title: str) -> str:
    """Removes special characters (including hyphens) from AI-generated titles."""
    # This new, stricter regex ONLY keeps letters, numbers, and spaces.
    sanitized = re.sub(r'[^a-zA-Z0-9\s]', '', title)
    # Replace multiple spaces with a single space
    sanitized = re.sub(r'\s+', ' ', sanitized)
    return sanitized.strip()

# --- Services (Shopify & AI) ---
class ShopifyService:
    def __init__(self):
        self.shop_domain = os.getenv("SHOPIFY_SHOP_DOMAIN")
        self.access_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
        self.api_version = "2024-01"
        self.configured = bool(self.shop_domain and self.access_token)
        if self.configured: self.base_url = f"https://{self.shop_domain}/admin/api/{self.api_version}"; self.headers = {"X-Shopify-Access-Token": self.access_token, "Content-Type": "application/json"}
        else: shopify_logger.warning("⚠️ Shopify credentials not configured")
    async def get_products(self, limit=250):
        if not self.configured: return []
        async with httpx.AsyncClient() as c:
            try: resp = await c.get(f"{self.base_url}/products.json", headers=self.headers, params={"limit": limit,"fields":"id,title,handle,product_type,vendor,tags"}, timeout=30); resp.raise_for_status(); return resp.json().get("products", [])
            except Exception as e: shopify_logger.error(f"Failed to get products: {e}"); return []
    async def get_collections(self, limit=250):
        if not self.configured: return []
        async with httpx.AsyncClient() as c:
            try:
                smart = await c.get(f"{self.base_url}/smart_collections.json", headers=self.headers, params={"limit": limit,"fields":"id,title,handle,products_count"}, timeout=30)
                custom = await c.get(f"{self.base_url}/custom_collections.json", headers=self.headers, params={"limit": limit,"fields":"id,title,handle,products_count"}, timeout=30)
                collections = []
                if smart.status_code == 200: collections.extend(smart.json().get("smart_collections", []))
                if custom.status_code == 200: collections.extend(custom.json().get("custom_collections", []))
                return collections
            except Exception as e: shopify_logger.error(f"Failed to get collections: {e}"); return []
    async def update_product(self, product_id: str, title: str, description: str):
        if not self.configured: return False
        update_data = {"product": {"id": int(product_id), "title": title, "body_html": description}}
        url = f"{self.base_url}/products/{product_id}.json"
        async with httpx.AsyncClient() as c:
            try: resp = await c.put(url, headers=self.headers, json=update_data, timeout=30); resp.raise_for_status(); shopify_logger.info(f"✅ Successfully updated product {product_id} on Shopify."); return True
            except Exception as e: shopify_logger.error(f"❌ Failed to update product {product_id} on Shopify: {e}"); return False
    async def update_collection(self, collection_id: str, title: str, description: str):
        if not self.configured: return False
        update_data = {"custom_collection": {"id": int(collection_id), "title": title, "body_html": description}}
        url = f"{self.base_url}/custom_collections/{collection_id}.json"
        async with httpx.AsyncClient() as c:
            try: resp = await c.put(url, headers=self.headers, json=update_data, timeout=30); resp.raise_for_status(); shopify_logger.info(f"✅ Successfully updated collection {collection_id} on Shopify."); return True
            except httpx.HTTPStatusError as http_err:
                if http_err.response.status_code == 404:
                    update_data = {"smart_collection": {"id": int(collection_id), "title": title, "body_html": description}}
                    url = f"{self.base_url}/smart_collections/{collection_id}.json"
                    resp = await c.put(url, headers=self.headers, json=update_data, timeout=30); resp.raise_for_status(); shopify_logger.info(f"✅ Successfully updated smart_collection {collection_id} on Shopify."); return True
                else: raise http_err
            except Exception as e: shopify_logger.error(f"❌ Failed to update collection {collection_id} on Shopify: {e}"); return False

class CostEffectiveAIService:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None
        self.model = "gpt-3.5-turbo"
        if self.client: openai_logger.info(f"✅ AI Service configured - Cost-effective mode (model: {self.model})")
        else: openai_logger.warning("⚠️ OpenAI API key not configured")
    async def generate_seo_geo_content(self, item_title: str, item_type: str = "product") -> dict:
        if not self.client: return {}
        openai_logger.info(f"💰 Generating cost-effective content for: {item_title}")
        prompt = f"""
        Create SEO and AI-search optimized content for this e-commerce {item_type}: "{item_title}".
        Generate:
        1. A new `title` for the Shopify page. Max 60 characters. It must be compelling and clean of special characters.
        2. A new `description` in HTML format. It must be **no more than 2 short paragraphs** (100-150 words total). The first paragraph explains what it is and its main benefit. The second paragraph explains why to choose it.
        Format the response as a single, valid JSON object with two keys: "title" and "description".
        """
        try:
            resp = await asyncio.to_thread(self.client.chat.completions.create, model=self.model, messages=[{"role": "system", "content": "You are an expert SEO copywriter. Be concise, professional, and cost-effective."}, {"role": "user", "content": prompt}], temperature=0.7, max_tokens=400, response_format={"type": "json_object"})
            content = json.loads(resp.choices[0].message.content)
            openai_logger.info(f"✅ Generated raw content for {item_title}")
            return content
        except Exception as e: openai_logger.error(f"❌ AI generation error for {item_title}: {e}"); return {}

# --- Background Processing Logic ---
async def process_pending_items(db: Session):
    processor_logger.info("="*60 + "\n🚀 STARTING AUTOMATED CONTENT GENERATION RUN\n" + "="*60)
    
    pending_products = db.query(Product).filter(Product.status == 'pending').limit(5).all()
    processor_logger.info(f"Found {len(pending_products)} pending products to process.")
    for product in pending_products:
        original_title = product.title
        try:
            product.status = 'processing'; db.commit()
            cleaned_title = clean_input_title(original_title)
            processor_logger.info(f"⚙️ Processing product: '{original_title}' -> CLEANED to -> '{cleaned_title}'")
            content = await ai_service.generate_seo_geo_content(cleaned_title, "product")
            if not content or "title" not in content or "description" not in content: raise Exception("Content generation failed or returned invalid format")
            sanitized_title = sanitize_output_title(content["title"])
            processor_logger.info(f"✨ AI title: '{content['title']}' -> SANITIZED to -> '{sanitized_title}'")
            success = await shopify.update_product(product.shopify_id, sanitized_title, content["description"])
            if not success: raise Exception("Shopify API update failed")
            product.status = 'completed'; product.seo_written = True; product.processed_at = datetime.utcnow()
            seo_record = SEOContent(item_id=product.shopify_id, item_type='product', item_title=sanitized_title, seo_title=sanitized_title, ai_description=content["description"])
            db.add(seo_record)
            processor_logger.info(f"✅ Successfully processed product: {sanitized_title}")
        except Exception as e:
            product.status = 'failed'
            processor_logger.error(f"❌ Failed to process product '{original_title}': {e}"); traceback.print_exc()
        finally: db.commit(); await asyncio.sleep(3)

    pending_collections = db.query(Collection).filter(Collection.status == 'pending').limit(2).all()
    processor_logger.info(f"Found {len(pending_collections)} pending collections to process.")
    for collection in pending_collections:
        original_title = collection.title
        try:
            collection.status = 'processing'; db.commit()
            cleaned_title = clean_input_title(original_title)
            processor_logger.info(f"⚙️ Processing collection: '{original_title}' -> CLEANED to -> '{cleaned_title}'")
            content = await ai_service.generate_seo_geo_content(cleaned_title, "collection")
            if not content or "title" not in content or "description" not in content: raise Exception("Content generation failed or returned invalid format")
            sanitized_title = sanitize_output_title(content["title"])
            processor_logger.info(f"✨ AI title: '{content['title']}' -> SANITIZED to -> '{sanitized_title}'")
            success = await shopify.update_collection(collection.shopify_id, sanitized_title, content["description"])
            if not success: raise Exception("Shopify API update failed")
            collection.status = 'completed'; collection.seo_written = True; collection.processed_at = datetime.utcnow()
            seo_record = SEOContent(item_id=collection.shopify_id, item_type='collection', item_title=sanitized_title, seo_title=sanitized_title, ai_description=content["description"])
            db.add(seo_record)
            processor_logger.info(f"✅ Successfully processed collection: {sanitized_title}")
        except Exception as e:
            collection.status = 'failed'
            processor_logger.error(f"❌ Failed to process collection '{original_title}': {e}"); traceback.print_exc()
        finally: db.commit(); await asyncio.sleep(3)
    processor_logger.info("🏁 Background processing run finished.")

# --- FastAPI App & Endpoints ---
app = FastAPI(title="AI SEO Content Agent", version="FINAL-CLEAN")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
shopify = ShopifyService()
ai_service = CostEffectiveAIService()

@app.get("/")
def root(): return {"status": "ok"}

@app.post("/api/scan")
async def scan_all(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    state = db.query(SystemState).first();
    if not state: state = init_system_state(db)
    if state.is_paused: return {"error": "System is paused"}
    products = await shopify.get_products(); new_products = 0
    for p in products:
        if not db.query(Product).filter(Product.shopify_id == str(p.get('id'))).first():
            db.add(Product(shopify_id=str(p.get('id')), title=p.get('title'), handle=p.get('handle'), product_type=p.get('product_type'), vendor=p.get('vendor'), tags=str(p.get('tags')), status='pending')); new_products += 1
    collections = await shopify.get_collections(); new_collections = 0
    for c in collections:
        if not db.query(Collection).filter(Collection.shopify_id == str(c.get('id'))).first():
            db.add(Collection(shopify_id=str(c.get('id')), title=c.get('title'), handle=c.get('handle'), products_count=c.get('products_count',0), status='pending')); new_collections += 1
    state.last_scan=datetime.utcnow(); state.products_found_in_last_scan=new_products; state.collections_found_in_last_scan=new_collections
    if (new_products+new_collections)>100: state.is_paused=True; state.auto_pause_triggered=True
    db.commit()
    if not state.is_paused and (new_products > 0 or new_collections > 0):
        background_tasks.add_task(process_pending_items, db)
    return {"products_found":new_products, "collections_found":new_collections}

@app.post("/api/process-queue")
async def trigger_processing(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    state = db.query(SystemState).first()
    if state and state.is_paused: return {"error":"System is paused"}
    background_tasks.add_task(process_pending_items, db)
    return {"message": "Processing task started in the background."}

@app.get("/api/dashboard")
async def get_dashboard(db: Session = Depends(get_db)):
    state = db.query(SystemState).first();
    if not state: state = init_system_state(db)
    total_products = db.query(Product).count(); completed_products = db.query(Product).filter(Product.status == "completed").count(); pending_products = db.query(Product).filter(Product.status == "pending").count()
    total_collections = db.query(Collection).count(); completed_collections = db.query(Collection).filter(Collection.status == "completed").count(); pending_collections = db.query(Collection).filter(Collection.status == "pending").count()
    recent_products = db.query(Product).order_by(Product.updated_at.desc()).limit(5).all()
    recent_collections = db.query(Collection).order_by(Collection.updated_at.desc()).limit(5).all()
    recent_activity = [{'id':p.shopify_id,'title':p.title,'type':'product','status':p.status,'updated':p.updated_at.isoformat() if p.updated_at else None} for p in recent_products] + [{'id':c.shopify_id,'title':c.title,'type':'collection','status':c.status,'updated':c.updated_at.isoformat() if c.updated_at else None} for c in recent_collections]
    recent_activity.sort(key=lambda x: x["updated"] or "", reverse=True)
    return {
        "system": {"is_paused": state.is_paused, "auto_pause_triggered": state.auto_pause_triggered, "last_scan": state.last_scan.isoformat() if state.last_scan else None},
        "stats": { "products": {"total": total_products, "completed": completed_products, "pending": pending_products}, "collections": {"total": total_collections, "completed": completed_collections, "pending": pending_collections}, "total_completed": completed_products + completed_collections },
        "recent_activity": recent_activity[:10]
    }

@app.post("/api/pause")
async def toggle_pause(db: Session = Depends(get_db)):
    state = db.query(SystemState).first();
    if not state: state = init_system_state(db)
    state.is_paused = not state.is_paused; state.auto_pause_triggered = False; db.commit()
    return {"is_paused": state.is_paused}
