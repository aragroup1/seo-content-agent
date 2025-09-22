import os
import json
import asyncio
import re
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Request
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
    id=Column(Integer,primary_key=True); shopify_id=Column(String,unique=True,index=True); title=Column(String); handle=Column(String,nullable=True); product_type=Column(String,nullable=True); vendor=Column(String,nullable=True); tags=Column(Text,nullable=True); status=Column(String,default="pending"); seo_written=Column(Boolean,default=False); created_at=Column(DateTime,default=datetime.utcnow); updated_at=Column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow); processed_at=Column(DateTime,nullable=True)

class Collection(Base):
    __tablename__ = "collections"
    id=Column(Integer,primary_key=True); shopify_id=Column(String,unique=True,index=True); title=Column(String); handle=Column(String,nullable=True); products_count=Column(Integer,default=0); status=Column(String,default="pending"); seo_written=Column(Boolean,default=False); created_at=Column(DateTime,default=datetime.utcnow); updated_at=Column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow); processed_at=Column(DateTime,nullable=True)

class SEOContent(Base):
    __tablename__ = "seo_content"
    id=Column(Integer,primary_key=True); item_id=Column(String,index=True); item_type=Column(String); item_title=Column(String); seo_title=Column(String); meta_description=Column(String,nullable=True); ai_description=Column(Text,nullable=True); generated_at=Column(DateTime,default=datetime.utcnow)

class SystemState(Base):
    __tablename__ = "system_state"
    id=Column(Integer,primary_key=True); is_paused=Column(Boolean,default=False); auto_pause_triggered=Column(Boolean,default=False); last_scan=Column(DateTime,nullable=True); products_found_in_last_scan=Column(Integer,default=0); collections_found_in_last_scan=Column(Integer,default=0); total_items_processed=Column(Integer,default=0)

try:
    Base.metadata.create_all(bind=engine)
    db_logger.info("✅ Database tables created/verified successfully")
except Exception as e:
    db_logger.error(f"❌ Database error on table creation: {e}")

# --- DB & Data Cleaning Helpers ---
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
    sanitized = re.sub(r'[^a-zA-Z0-9\s]', '', title)
    return re.sub(r'\s+', ' ', sanitized).strip()
def html_to_text(html_content: str) -> str:
    if not html_content: return ""
    return re.sub('<[^<]+?>', ' ', html_content).strip()

# --- Services (Shopify & AI) ---
class ShopifyService:
    def __init__(self):
        self.shop_domain=os.getenv("SHOPIFY_SHOP_DOMAIN"); self.access_token=os.getenv("SHOPIFY_ACCESS_TOKEN"); self.api_version="2024-01"; self.configured=bool(self.shop_domain and self.access_token)
        if self.configured: self.base_url=f"https://{self.shop_domain}/admin/api/{self.api_version}"; self.headers={"X-Shopify-Access-Token": self.access_token, "Content-Type": "application/json"}
    
    def _parse_next_page_info(self, link_header: Optional[str]) -> Optional[str]:
        """Extracts the page_info token from the Link header for cursor-based pagination."""
        if not link_header: return None
        match = re.search(r'<[^>]*[?&]page_info=([^&>]+)[^>]*>;\s*rel="next"', link_header)
        return match.group(1) if match else None

    async def get_all_paginated_resources(self, endpoint: str, resource_key: str):
        """Reliably fetches all items from a paginated Shopify endpoint."""
        if not self.configured: return []
        
        resources = []
        page_info = None
        page_count = 1
        
        url = f"{self.base_url}/{endpoint}.json?limit=250&fields=id,title,handle,body_html,product_type,vendor,tags,products_count"
        
        while url:
            try:
                async with httpx.AsyncClient() as c:
                    resp = await c.get(url, headers=self.headers, timeout=45)
                    resp.raise_for_status()
                    
                    data = resp.json().get(resource_key, [])
                    resources.extend(data)
                    shopify_logger.info(f"Fetched page {page_count} ({len(data)} items) from {endpoint}.")
                    
                    link_header = resp.headers.get("Link")
                    page_info = self._parse_next_page_info(link_header)
                    
                    if page_info:
                        url = f"{self.base_url}/{endpoint}.json?limit=250&fields=id,title,handle,body_html,product_type,vendor,tags,products_count&page_info={page_info}"
                        page_count += 1
                    else:
                        url = None # End of pages
            except Exception as e:
                shopify_logger.error(f"Failed to fetch page {page_count} from {endpoint}: {e}")
                break # Stop fetching on error
                
        shopify_logger.info(f"Total {resource_key} fetched: {len(resources)}")
        return resources

    async def get_all_products(self):
        return await self.get_all_paginated_resources("products", "products")
    
    async def get_all_collections(self):
        smart = await self.get_all_paginated_resources("smart_collections", "smart_collections")
        custom = await self.get_all_paginated_resources("custom_collections", "custom_collections")
        return smart + custom
        
    async def get_product_details(self, product_id: str):
        if not self.configured: return None
        url=f"{self.base_url}/products/{product_id}.json"
        async with httpx.AsyncClient() as c:
            try: resp=await c.get(url,headers=self.headers,params={"fields":"id,title,body_html,product_type,vendor"},timeout=20); resp.raise_for_status(); return resp.json().get("product")
            except Exception as e: shopify_logger.error(f"Failed to get details for product {product_id}: {e}"); return None
    async def update_product(self,product_id:str,title:Optional[str]=None,description:Optional[str]=None,meta_title:Optional[str]=None,meta_description:Optional[str]=None):
        if not self.configured: return False
        payload={"product":{"id":int(product_id)}}; metafields=[]
        if title: payload["product"]["title"]=title
        if description: payload["product"]["body_html"]=description
        if meta_title: metafields.append({"key":"title_tag","namespace":"global","value":meta_title,"type":"string"})
        if meta_description: metafields.append({"key":"description_tag","namespace":"global","value":meta_description,"type":"string"})
        if metafields: payload["product"]["metafields"]=metafields
        url=f"{self.base_url}/products/{product_id}.json"
        async with httpx.AsyncClient() as c:
            try: resp=await c.put(url,headers=self.headers,json=payload,timeout=30); resp.raise_for_status(); shopify_logger.info(f"✅ Shopify update successful for product {product_id}."); return True
            except Exception as e: shopify_logger.error(f"❌ Shopify update failed for product {product_id}: {e}"); return False

class SmartAIService:
    # ... (No changes to this class, keep the existing code)
    # The full class is pasted below for completeness
    def __init__(self):
        self.api_key=os.getenv("OPENAI_API_KEY"); self.client=OpenAI(api_key=self.api_key) if self.api_key else None; self.model="gpt-3.5-turbo"
        if self.client: openai_logger.info(f"✅ AI Service configured - Smart Mode (model: {self.model})")
    async def generate_full_content(self, title: str, existing_description: str) -> dict:
        if not self.client: return{}
        prompt=f'Act as an expert SEO copy editor for the product "{title}". Use the existing description for context, but create a better, more complete version. Generate: 1. A new `title` (max 60 characters). 2. A new `description` in HTML (1-2 paragraphs, 100-150 words). Format the response as a valid JSON object with "title" and "description" keys. Existing Description: "{existing_description}"'
        try:
            resp=await asyncio.to_thread(self.client.chat.completions.create,model=self.model,messages=[{"role":"system","content":"You are a concise and professional SEO copywriter who improves existing text. Ensure your response is valid JSON."},{"role":"user","content":prompt}],temperature=0.7,max_tokens=400,response_format={"type":"json_object"})
            return json.loads(resp.choices[0].message.content)
        except Exception as e: openai_logger.error(f"AI full content error for '{title}': {e}"); return{}
    async def generate_meta_only_content(self, title: str, existing_description: str) -> dict:
        if not self.client: return{}
        prompt=f'Based on the product title "{title}" and this existing description: "{existing_description[:1000]}...", create: 1. A new main `title` for the product page (descriptive, 60-70 characters). 2. A new SEO `meta_title` for search engines (60-70 characters). 3. A compelling `meta_description` (max 155 chars). Format as a valid JSON object with "title", "meta_title", and "meta_description" keys.'
        try:
            resp=await asyncio.to_thread(self.client.chat.completions.create,model=self.model,messages=[{"role":"system","content":"You are an expert SEO copywriter creating metadata. Ensure your response is valid JSON."},{"role":"user","content":prompt}],temperature=0.7,max_tokens=300,response_format={"type":"json_object"})
            return json.loads(resp.choices[0].message.content)
        except Exception as e: openai_logger.error(f"AI meta only error for '{title}': {e}"); return{}

# --- Background Processing Logic ---
async def process_pending_items(db:Session):
    processor_logger.info("="*60+"\n🚀 STARTING SMART CONTENT OPTIMIZATION RUN\n"+"="*60)
    WORD_COUNT_THRESHOLD=int(os.getenv("DESCRIPTION_WORD_COUNT_THRESHOLD",100))
    processor_logger.info(f"Smart Mode Active: Word count threshold is {WORD_COUNT_THRESHOLD} words.")
    pending_products=db.query(Product).filter(Product.status.in_(['pending','failed'])).limit(5).all()
    processor_logger.info(f"Found {len(pending_products)} pending products to process.")
    for product_stub in pending_products:
        original_title=product_stub.title
        try:
            product_stub.status='processing'; db.commit()
            full_product=await shopify.get_product_details(product_stub.shopify_id)
            if not full_product: raise Exception("Could not fetch full product details from Shopify.")
            existing_description_html=full_product.get('body_html','')
            cleaned_title=clean_input_text(original_title)
            cleaned_description_text=clean_input_text(html_to_text(existing_description_html))
            word_count=len(cleaned_description_text.split())
            processor_logger.info(f"⚙️ Processing: '{original_title}' -> '{cleaned_title}' (desc words: {word_count})")
            if word_count>=WORD_COUNT_THRESHOLD:
                processor_logger.info(f"🎯 Meta Only Mode for '{cleaned_title}'")
                content=await ai_service.generate_meta_only_content(cleaned_title,cleaned_description_text)
                if not content or"title"not in content or"meta_title"not in content or"meta_description"not in content: raise Exception("Meta-only AI output invalid")
                sanitized_title=sanitize_output_title(content["title"])
                success=await shopify.update_product(product_stub.shopify_id,title=sanitized_title,meta_title=content["meta_title"],meta_description=content["meta_description"])
                if not success: raise Exception("Shopify API update failed.")
            else:
                processor_logger.info(f"✍️ Full Rewrite Mode for '{cleaned_title}'")
                content=await ai_service.generate_full_content(cleaned_title,cleaned_description_text)
                if not content or"title"not in content or"description"not in content: raise Exception("Full-rewrite AI output invalid")
                sanitized_title=sanitize_output_title(content["title"])
                success=await shopify.update_product(product_stub.shopify_id,title=sanitized_title,description=content["description"])
                if not success: raise Exception("Shopify API update failed.")
            product_stub.status='completed'; product_stub.seo_written=True; product_stub.processed_at=datetime.utcnow()
            seo_record=SEOContent(item_id=product_stub.shopify_id,item_type='product',item_title=sanitized_title,seo_title=content.get("meta_title",sanitized_title),ai_description=content.get("description"),meta_description=content.get("meta_description"))
            db.add(seo_record); processor_logger.info(f"✅ Successfully processed: {sanitized_title}")
        except Exception as e:
            product_stub.status='failed'; processor_logger.error(f"❌ Failed to process product '{original_title}': {e}"); traceback.print_exc()
        finally: db.commit(); await asyncio.sleep(3)
    processor_logger.info("🏁 Background processing run finished.")

# --- FastAPI App & Endpoints ---
app=FastAPI(title="AI SEO Content Agent",version="FINAL-PAGINATED")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
shopify=ShopifyService()
ai_service=SmartAIService()

@app.get("/")
def root(): return{"status":"ok"}

@app.post("/api/scan")
async def scan_all(background_tasks: BackgroundTasks,db: Session=Depends(get_db)):
    state=db.query(SystemState).first();
    if not state: state=init_system_state(db)
    if state.is_paused: return{"error":"System is paused"}
    
    products = await shopify.get_all_products()
    new_products=0
    for p in products:
        if not db.query(Product).filter(Product.shopify_id==str(p.get('id'))).first():
            db.add(Product(shopify_id=str(p.get('id')),title=p.get('title'),handle=p.get('handle'),status='pending')); new_products+=1
    
    collections = await shopify.get_all_collections()
    new_collections=0
    for c in collections:
        if not db.query(Collection).filter(Collection.shopify_id==str(c.get('id'))).first():
            db.add(Collection(shopify_id=str(c.get('id')),title=c.get('title'),handle=c.get('handle'),products_count=c.get('products_count',0),status='pending')); new_collections+=1
    
    state.last_scan=datetime.utcnow(); state.products_found_in_last_scan=new_products; state.collections_found_in_last_scan=new_collections
    if (new_products+new_collections)>100: state.is_paused=True; state.auto_pause_triggered=True
    db.commit()
    
    if not state.is_paused and(new_products>0 or new_collections>0):
        background_tasks.add_task(process_pending_items,db)
        
    return{"products_found":new_products,"collections_found":new_collections}

# ... (All other endpoints like /process-queue, /dashboard, /pause, /cron/run-tasks remain the same)
# You MUST paste the full code for your other endpoints here for a complete file.
