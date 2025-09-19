import os
import json
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Boolean, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker
from dotenv import load_dotenv
from openai import OpenAI
import httpx
import logging
import traceback

# Enhanced logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create separate loggers
shopify_logger = logging.getLogger("shopify")
openai_logger = logging.getLogger("openai")
db_logger = logging.getLogger("database")
api_logger = logging.getLogger("api")
processor_logger = logging.getLogger("processor")

load_dotenv()

# Log configuration on startup
logger.info("="*60)
logger.info("STARTING AI SEO + GEO CONTENT AGENT")
logger.info("="*60)

# Check environment variables
env_vars = {
    "OPENAI_API_KEY": "***" if os.getenv("OPENAI_API_KEY") else "NOT SET",
    "SHOPIFY_ACCESS_TOKEN": "***" if os.getenv("SHOPIFY_ACCESS_TOKEN") else "NOT SET",
    "SHOPIFY_SHOP_DOMAIN": os.getenv("SHOPIFY_SHOP_DOMAIN", "NOT SET"),
    "DATABASE_URL": "***" if os.getenv("DATABASE_URL") else "NOT SET"
}

for key, value in env_vars.items():
    logger.info(f"Environment: {key} = {value}")

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./seo_agent.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    db_logger.info("Using PostgreSQL database")
else:
    db_logger.info("Using SQLite database")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Define Base BEFORE using it
Base = declarative_base()

# Database Models
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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

class SEOContent(Base):
    __tablename__ = "seo_content"
    
    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(String, index=True)
    item_type = Column(String)
    item_title = Column(String)
    seo_title = Column(String)
    ai_description = Column(Text)
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
    auto_processing_enabled = Column(Boolean, default=True)

class APILog(Base):
    __tablename__ = "api_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    service = Column(String)
    action = Column(String)
    status = Column(String)
    message = Column(Text)
    details = Column(JSON, nullable=True)

# Create/update tables
try:
    Base.metadata.create_all(bind=engine)
    db_logger.info("✅ Database tables created/verified successfully")
except Exception as e:
    db_logger.error(f"❌ Database error: {e}")

# Database helpers
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def log_api_action(db: Session, service: str, action: str, status: str, message: str, details: dict = None):
    """Log API actions to database"""
    try:
        log_entry = APILog(
            service=service,
            action=action,
            status=status,
            message=message,
            details=details
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to log API action: {e}")

def init_system_state(db: Session):
    state = db.query(SystemState).first()
    if not state:
        state = SystemState(
            is_paused=False,
            auto_processing_enabled=True
        )
        db.add(state)
        db.commit()
        db_logger.info("Initialized system state")
    return state

# FastAPI app
app = FastAPI(title="AI SEO + GEO Content Agent", version="5.0.0")

# Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = datetime.utcnow()
    api_logger.info(f"📥 {request.method} {request.url.path}")
    
    response = await call_next(request)
    
    process_time = (datetime.utcnow() - start_time).total_seconds()
    api_logger.info(f"📤 {request.method} {request.url.path} - {response.status_code} - {process_time:.2f}s")
    
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shopify Service
class ShopifyService:
    def __init__(self):
        self.shop_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        self.access_token = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
        self.api_version = "2024-01"
        
        if not self.shop_domain or not self.access_token:
            shopify_logger.warning("⚠️ Shopify credentials not configured")
            self.configured = False
        else:
            self.configured = True
            self.base_url = f"https://{self.shop_domain}/admin/api/{self.api_version}"
            self.headers = {
                "X-Shopify-Access-Token": self.access_token,
                "Content-Type": "application/json"
            }
            shopify_logger.info(f"✅ Shopify configured for: {self.shop_domain}")
    
    async def get_products(self, limit=250, since_id=None):
        """Fetch products from Shopify"""
        if not self.configured:
            shopify_logger.error("❌ Cannot fetch products - Shopify not configured")
            return []
        
        shopify_logger.info(f"🔍 Fetching products from Shopify (limit={limit})")
        
        params = {"limit": limit}
        if since_id:
            params["since_id"] = since_id
            
        try:
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/products.json"
                response = await client.get(
                    url,
                    headers=self.headers,
                    params=params,
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    products = data.get("products", [])
                    shopify_logger.info(f"✅ Successfully fetched {len(products)} products")
                    return products
                else:
                    shopify_logger.error(f"❌ Shopify API error: {response.status_code}")
                    return []
                    
        except Exception as e:
            shopify_logger.error(f"❌ Exception fetching products: {str(e)}")
            return []
    
    async def get_collections(self, limit=250):
        """Fetch collections from Shopify"""
        if not self.configured:
            return []
        
        try:
            async with httpx.AsyncClient() as client:
                collections = []
                
                # Get smart collections
                smart_response = await client.get(
                    f"{self.base_url}/smart_collections.json",
                    headers=self.headers,
                    params={"limit": limit},
                    timeout=30
                )
                
                if smart_response.status_code == 200:
                    collections.extend(smart_response.json().get("smart_collections", []))
                
                # Get custom collections
                custom_response = await client.get(
                    f"{self.base_url}/custom_collections.json",
                    headers=self.headers,
                    params={"limit": limit},
                    timeout=30
                )
                
                if custom_response.status_code == 200:
                    collections.extend(custom_response.json().get("custom_collections", []))
                
                shopify_logger.info(f"✅ Total collections fetched: {len(collections)}")
                return collections
                
        except Exception as e:
            shopify_logger.error(f"❌ Exception fetching collections: {str(e)}")
            return []
    
    async def update_product(self, product_id: str, title: str, description: str):
        """Update product title and description in Shopify"""
        if not self.configured:
            return False
        
        update_data = {
            "product": {
                "id": product_id,
                "title": title,
                "body_html": description
            }
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"{self.base_url}/products/{product_id}.json",
                    headers=self.headers,
                    json=update_data,
                    timeout=30
                )
                
                if response.status_code == 200:
                    shopify_logger.info(f"✅ Updated product {product_id}")
                    return True
                else:
                    shopify_logger.error(f"❌ Failed to update product {product_id}: {response.status_code}")
                    return False
                    
        except Exception as e:
            shopify_logger.error(f"❌ Exception updating product: {e}")
            return False

# Cost-Effective AI Service
class CostEffectiveAIService:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key)
            self.model = "gpt-3.5-turbo"  # Most cost-effective
            openai_logger.info(f"✅ AI Service configured - Cost-effective mode")
        else:
            openai_logger.warning("⚠️ OpenAI API key not configured")
            self.client = None
    
    async def generate_seo_geo_content(self, item: dict, item_type: str = "product") -> dict:
        """Generate SEO + GEO optimized content in ONE API call (cost-effective)"""
        if not self.client:
            return {}
        
        openai_logger.info(f"💰 Generating cost-effective content for: {item.get('title', '')}")
        
        try:
            # Single prompt for both title and description
            prompt = f"""
            Create SEO and AI-search optimized content for this {item_type}:
            
            {item_type.title()}: {item.get('title', '')}
            Type: {item.get('product_type', '')}
            Brand: {item.get('vendor', '')}
            
            Generate:
            1. SEO Title (max 60 chars): Include main keyword, benefit, and brand if space allows
            2. Description (1-2 paragraphs ONLY, 100-150 words total):
               - First paragraph: What it is, key benefits, and main use case
               - Second paragraph: Why choose this, unique value proposition
               - Use natural language that AI assistants can understand
               - Include relevant keywords naturally
               - Answer "What is this?" and "Why buy this?"
            
            Format response as JSON:
            {{
                "title": "SEO optimized title here",
                "description": "First paragraph here.<br><br>Second paragraph here."
            }}
            
            Keep it concise and cost-effective. No extra content.
            """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert SEO copywriter. Be concise and cost-effective."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=300,  # Limited tokens for cost
                response_format={"type": "json_object"}
            )
            
            content = json.loads(response.choices[0].message.content)
            
            # Ensure title is within limit
            if content.get("title"):
                content["title"] = content["title"][:60]
            
            openai_logger.info(f"✅ Generated content - Title: {len(content.get('title', ''))} chars")
            return content
            
        except Exception as e:
            openai_logger.error(f"❌ AI generation error: {str(e)}")
            return {}

# Initialize services
shopify = ShopifyService()
ai_service = CostEffectiveAIService()

# Background processor
async def process_pending_items():
    """Process pending items with cost-effective approach"""
    db = SessionLocal()
    try:
        processor_logger.info("="*60)
        processor_logger.info("🚀 STARTING AUTOMATED CONTENT GENERATION")
        processor_logger.info("💰 Cost-effective mode: 1-2 paragraphs per product")
        processor_logger.info("="*60)
        
        # Check system state
        state = db
