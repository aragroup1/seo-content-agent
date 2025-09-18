import os
import json
import asyncio
from datetime import datetime
from typing import List, Deque
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Boolean, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker
from dotenv import load_dotenv
from openai import OpenAI
import httpx
import logging
from collections import deque

# --- Live Log Handler ---
class LiveLogHandler:
    def __init__(self, max_size=100):
        self.logs: Deque[dict] = deque(maxlen=max_size)

    def add_log(self, level: str, message: str):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level.upper(),
            "message": message
        }
        self.logs.append(log_entry)
        # Also print to console for Railway logs
        print(f"[{log_entry['level']}] {log_entry['message']}")

    def get_logs(self) -> List[dict]:
        return list(self.logs)

live_logger = LiveLogHandler()

# --- Standard Setup ---
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./seo_agent.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Database Models (Unchanged) ---
class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    shopify_id = Column(String, unique=True, index=True)
    title = Column(String)
    handle = Column(String)
    product_type = Column(String)
    vendor = Column(String)
    tags = Column(Text)
    status = Column(String, default="pending")
    seo_written = Column(Boolean, default=False)
    keywords_researched = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

class Collection(Base):
    __tablename__ = "collections"
    id = Column(Integer, primary_key=True, index=True)
    shopify_id = Column(String, unique=True, index=True)
    title = Column(String)
    handle = Column(String)
    products_count = Column(Integer, default=0)
    status = Column(String, default="pending")
    seo_written = Column(Boolean, default=False)
    keywords_researched = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

class ManualQueue(Base):
    __tablename__ = "manual_queue"
    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(String, index=True)
    item_type = Column(String)
    title = Column(String)
    url = Column(String, nullable=True)
    priority = Column(Integer, default=10)
    reason = Column(String, nullable=True)
    status = Column(String, default="pending")
    added_by = Column(String, default="manual")
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

class SEOContent(Base):
    __tablename__ = "seo_content"
    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(String, index=True)
    item_type = Column(String)
    item_title = Column(String)
    seo_title = Column(String)
    meta_description = Column(String)
    ai_description = Column(Text)
    keywords_used = Column(JSON)
    version = Column(Integer, default=1)
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

# --- FastAPI App and Dependencies ---
app = FastAPI(title="AI SEO Content Agent", version="3.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# --- Shopify Service with Logging ---
class ShopifyService:
    def __init__(self):
        # ... (init code is the same)
        self.shop_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        self.access_token = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
        self.api_version = "2024-01"
        self.configured = bool(self.shop_domain and self.access_token)
        if self.configured:
            self.base_url = f"https://{self.shop_domain}/admin/api/{self.api_version}"
            self.headers = {"X-Shopify-Access-Token": self.access_token, "Content-Type": "application/json"}
        else:
            live_logger.add_log("warn", "Shopify credentials are not configured!")

    async def get_products(self, limit=50):
        if not self.configured: return []
        live_logger.add_log("info", "Connecting to Shopify to fetch products...")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/products.json", headers=self.headers, params={"limit": limit}, timeout=30)
                if response.status_code == 200:
                    products = response.json()["products"]
                    live_logger.add_log("info", f"Successfully fetched {len(products)} products from Shopify.")
                    return products
                else:
                    live_logger.add_log("error", f"Shopify API error (Products): {response.status_code} - {response.text}")
                    return []
        except Exception as e:
            live_logger.add_log("error", f"HTTP Error fetching products: {e}")
            return []
    # ... (other Shopify methods like get_collections, update_product etc. would also have logging) ...

# --- AI Service with Logging ---
class AIService:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None
        if not self.client:
            live_logger.add_log("warn", "OpenAI API key not configured!")
    
    async def research_keywords(self, item: dict, item_type: str = "product"):
        if not self.client: return []
        live_logger.add_log("info", f"Researching keywords for {item_type}: '{item.get('title')}'...")
        # ... (rest of the keyword research logic) ...
        live_logger.add_log("info", f"Keywords found: {['keyword1', 'keyword2'][:3]}...")
        return ['keyword1', 'keyword2', 'keyword3'] # Dummy data for now

    async def generate_seo_content(self, item: dict, keywords: List[str], item_type: str = "product"):
        if not self.client: return {}
        live_logger.add_log("info", f"Generating content for '{item.get('title')}' with OpenAI...")
        # ... (rest of the content generation logic) ...
        live_logger.add_log("info", f"Content successfully generated for '{item.get('title')}'!")
        return {"seo_title": "AI Title", "meta_description": "AI Meta", "ai_description": "AI Body"} # Dummy data

shopify = ShopifyService()
ai_service = AIService()

# --- API Endpoints ---
@app.get("/")
async def root():
    return {"status": "AI SEO Agent Running", "version": "3.1.0"}

@app.post("/api/scan")
async def scan_all(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    live_logger.add_log("info", "Scan request received.")
    # ... (the rest of your scan_all function logic here) ...
    # Add logging inside the function loops:
    products = await shopify.get_products()
    new_products = 0
    for product in products:
        # ... your logic ...
        if not db.query(Product).filter(Product.shopify_id == str(product.get('id'))).first():
            new_products += 1
            live_logger.add_log("info", f"Found new product: {product.get('title')}")
    live_logger.add_log("info", f"Scan complete. Found {new_products} new products.")
    return {"message": "Scan complete", "products_found": new_products}

# --- NEW LOGS ENDPOINT ---
@app.get("/api/live-logs")
async def get_live_logs():
    """Returns the most recent logs for the dashboard."""
    return {"logs": live_logger.get_logs()}

# ... (Include all your other endpoints: /api/dashboard, /api/manual-queue, etc.) ...
# Ensure to copy the rest of your main.py file content here. I've omitted it for brevity.
@app.get("/api/dashboard")
async def get_dashboard(db: Session = Depends(get_db)):
    # ... Your existing dashboard logic ...
    return {} # Placeholder
