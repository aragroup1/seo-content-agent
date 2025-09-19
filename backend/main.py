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

# Create separate loggers for each component
shopify_logger = logging.getLogger("shopify")
openai_logger = logging.getLogger("openai")
db_logger = logging.getLogger("database")
api_logger = logging.getLogger("api")
processor_logger = logging.getLogger("processor")

load_dotenv()

# Log configuration on startup
logger.info("="*50)
logger.info("STARTING AI SEO CONTENT AGENT - AUTOMATIC MODE")
logger.info("="*50)

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

# FIXED: Define Base BEFORE using it in model classes
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

# Create tables
try:
    Base.metadata.create_all(bind=engine)
    db_logger.info("✅ Database tables created/verified successfully")
except Exception as e:
    db_logger.error(f"❌ Database error: {e}")

# Pydantic Models
class ManualQueueItem(BaseModel):
    item_id: str
    item_type: str = "product"
    title: str
    url: Optional[str] = None
    reason: str = "revision"

class GenerateContentRequest(BaseModel):
    item_id: str
    item_type: str
    regenerate: bool = False

# Database helpers
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def log_api_action(db: Session, service: str, action: str, status: str, message: str, details: dict = None):
    """Log API actions to database for tracking"""
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
        state = SystemState(is_paused=False, auto_processing_enabled=True)
        db.add(state)
        db.commit()
        db_logger.info("Initialized system state")
    return state

# FastAPI app
app = FastAPI(title="AI SEO Content Agent", version="3.1.0")

# Middleware for request logging
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
                shopify_logger.info(f"📡 GET {url}")
                
                response = await client.get(
                    url,
                    headers=self.headers,
                    params=params,
                    timeout=30
                )
                
                shopify_logger.info(f"📨 Response status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    products = data.get("products", [])
                    shopify_logger.info(f"✅ Successfully fetched {len(products)} products")
                    return products
                else:
                    error_msg = f"Shopify API error: {response.status_code} - {response.text}"
                    shopify_logger.error(f"❌ {error_msg}")
                    return []
                    
        except Exception as e:
            shopify_logger.error(f"❌ Exception fetching products: {str(e)}")
            return []
    
    async def get_collections(self, limit=250):
        """Fetch collections from Shopify"""
        if not self.configured:
            shopify_logger.error("❌ Cannot fetch collections - Shopify not configured")
            return []
        
        shopify_logger.info(f"🔍 Fetching collections from Shopify")
        
        try:
            async with httpx.AsyncClient() as client:
                collections = []
                
                # Get smart collections
                shopify_logger.info("📡 Fetching smart collections...")
                smart_response = await client.get(
                    f"{self.base_url}/smart_collections.json",
                    headers=self.headers,
                    params={"limit": limit},
                    timeout=30
                )
                
                if smart_response.status_code == 200:
                    smart_collections = smart_response.json().get("smart_collections", [])
                    collections.extend(smart_collections)
                    shopify_logger.info(f"✅ Found {len(smart_collections)} smart collections")
                
                # Get custom collections
                shopify_logger.info("📡 Fetching custom collections...")
                custom_response = await client.get(
                    f"{self.base_url}/custom_collections.json",
                    headers=self.headers,
                    params={"limit": limit},
                    timeout=30
                )
                
                if custom_response.status_code == 200:
                    custom_collections = custom_response.json().get("custom_collections", [])
                    collections.extend(custom_collections)
                    shopify_logger.info(f"✅ Found {len(custom_collections)} custom collections")
                
                shopify_logger.info(f"✅ Total collections fetched: {len(collections)}")
                return collections
                
        except Exception as e:
            shopify_logger.error(f"❌ Exception fetching collections: {str(e)}")
            return []
    
    async def update_product(self, product_id: str, seo_data: dict):
        """Update product with SEO content"""
        if not self.configured:
            shopify_logger.warning("⚠️ Cannot update product - Shopify not configured")
            return False
        
        shopify_logger.info(f"📝 Updating product {product_id} in Shopify")
        
        update_data = {
            "product": {
                "id": product_id,
                "body_html": seo_data.get("ai_description", "")
            }
        }
        
        # Note: Shopify doesn't allow updating the main title via API for existing products
        # We'll focus on description for now
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"{self.base_url}/products/{product_id}.json",
                    headers=self.headers,
                    json=update_data,
                    timeout=30
                )
                
                if response.status_code == 200:
                    shopify_logger.info(f"✅ Successfully updated product {product_id}")
                    return True
                else:
                    shopify_logger.error(f"❌ Failed to update product {product_id}: {response.status_code}")
                    shopify_logger.error(f"Response: {response.text}")
                    return False
                    
        except Exception as e:
            shopify_logger.error(f"❌ Exception updating product {product_id}: {e}")
            return False
    
    async def update_collection(self, collection_id: str, seo_data: dict):
        """Update collection with SEO content"""
        if not self.configured:
            return False
        
        shopify_logger.info(f"📝 Updating collection {collection_id} in Shopify")
        
        # Try updating as custom collection first, then smart collection
        for collection_type in ["custom_collections", "smart_collections"]:
            try:
                update_data = {
                    collection_type[:-1]: {  # Remove 's' from the end
                        "id": collection_id,
                        "body_html": seo_data.get("ai_description", "")
                    }
                }
                
                async with httpx.AsyncClient() as client:
                    response = await client.put(
                        f"{self.base_url}/{collection_type}/{collection_id}.json",
                        headers=self.headers,
                        json=update_data,
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        shopify_logger.info(f"✅ Successfully updated collection {collection_id} as {collection_type}")
                        return True
                        
            except Exception as e:
                continue
        
        shopify_logger.error(f"❌ Failed to update collection {collection_id}")
        return False

# AI Service
class AIService:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key)
            self.model = "gpt-3.5-turbo"
            openai_logger.info(f"✅ OpenAI configured with model: {self.model}")
        else:
            openai_logger.warning("⚠️ OpenAI API key not configured")
            self.client = None
    
    async def research_keywords(self, item: dict, item_type: str = "product") -> List[str]:
        """Research keywords for any item type"""
        if not self.client:
            openai_logger.error("❌ Cannot research keywords - OpenAI not configured")
            return []
        
        openai_logger.info(f"🔍 Researching keywords for {item_type}: {item.get('title', 'Unknown')}")
        
        try:
            if item_type == "collection":
                prompt = f"""
                Generate 8 high-value SEO keywords for this collection:
                Collection: {item.get('title', '')}
                Products in collection: {item.get('products_count', 0)}
                
                Focus on:
                - Category keywords
                - Buying intent terms
                - Long-tail variations
                - Popular search terms
                
                Return only comma-separated keywords.
                """
            else:
                prompt = f"""
                Generate 8 high-value SEO keywords for this product:
                Product: {item.get('title', '')}
                Type: {item.get('product_type', '')}
                Brand: {item.get('vendor', '')}
                
                Focus on:
                - Product-specific keywords
                - Buyer intent terms
                - Brand + product combinations
                - Feature-based keywords
                
                Return only comma-separated keywords.
                """
            
            openai_logger.info(f"📤 Sending keyword request to OpenAI...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert SEO keyword researcher specializing in e-commerce."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=150
            )
            
            keywords = response.choices[0].message.content.strip()
            keyword_list = [k.strip() for k in keywords.split(',')][:8]
            
            openai_logger.info(f"✅ Generated {len(keyword_list)} keywords: {keyword_list[:3]}...")
            return keyword_list
            
        except Exception as e:
            openai_logger.error(f"❌ Keyword research error: {str(e)}")
            return []
    
    async def generate_seo_content(self, item: dict, keywords: List[str], item_type: str = "product") -> dict:
        """Generate complete SEO content"""
        if not self.client:
            openai_logger.error("❌ Cannot generate content - OpenAI not configured")
            return {}
        
        openai_logger.info(f"📝 Generating SEO content for {item_type}: {item.get('title', 'Unknown')}")
        
        try:
            if item_type == "collection":
                prompt = f"""
                Create SEO-optimized content for this collection:
                
                Collection: {item.get('title', '')}
                Products in collection: {item.get('products_count', 0)}
                Target Keywords: {', '.join(keywords[:5])}
                
                Generate JSON with:
                {{
                    "seo_title": "SEO title (max 60 chars, include main keyword)",
                    "meta_description": "Meta description (max 155 chars, compelling for collection pages)",
                    "ai_description": "Collection description (300-400 words in HTML format with <p> tags. Describe the collection theme, highlight key products/categories, include buying guides, use keywords naturally, add calls to action)"
                }}
                """
            else:
                prompt = f"""
                Create SEO-optimized content for this product:
                
                Product: {item.get('title', '')}
                Type: {item.get('product_type', '')}
                Brand: {item.get('vendor', '')}
                Target Keywords: {', '.join(keywords[:5])}
                
                Generate JSON with:
                {{
                    "seo_title": "SEO title (max 60 chars, include main keyword)",
                    "meta_description": "Meta description (max 155 chars, compelling and click-worthy)",
                    "ai_description": "Product description (200-300 words in HTML format with <p> tags. Focus on benefits, use keywords naturally, include features, add urgency/social proof)"
                }}
                """
            
            openai_logger.info(f"📤 Sending content generation request to OpenAI...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert e-commerce SEO copywriter. Create compelling, keyword-rich content that converts."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1200,
                response_format={"type": "json_object"}
            )
            
            content = json.loads(response.choices[0].message.content)
            openai_logger.info(f"✅ Successfully generated SEO content")
            
            # Ensure content is within limits
            if content.get("seo_title"):
                content["seo_title"] = content["seo_title"][:60]
            if content.get("meta_description"):
                content["meta_description"] = content["meta_description"][:155]
            
            return content
            
        except Exception as e:
            openai_logger.error(f"❌ Content generation error: {str(e)}")
            return {}

# Initialize services
shopify = ShopifyService()
ai_service = AIService()

# AUTOMATIC PROCESSING FUNCTIONS
async def process_pending_items():
    """🚀 MAIN PROCESSING FUNCTION - Process pending items automatically"""
    db = SessionLocal()
    try:
        processor_logger.info("="*50)
        processor_logger.info("🚀 STARTING AUTOMATIC CONTENT GENERATION")
        processor_logger.info("="*50)
        
        # Check if system is paused
        state = db.query(SystemState).first()
        if state and state.is_paused:
            processor_logger.warning("⏸️ System is paused - stopping processing")
            return
        
        if state and not state.auto_processing_enabled:
            processor_logger.warning("⏸️ Auto-processing disabled - stopping")
            return
        
        # Get pending items (small batches to respect API limits)
        pending_products = db.query(Product).filter(
            Product.status == "pending"
        ).limit(3).all()  # Process 3 products at a time
        
        pending_collections = db.query(Collection).filter(
            Collection.status == "pending"  
        ).limit(2).all()  # Process 2 collections at a time
        
        total_processed = 0
        
        processor_logger.info(f"📋 Found {len(pending_products)} pending products, {len(pending_collections)} pending collections")
        
        # Process products
        for product in pending_products:
            processor_logger.info(f"🎯 Processing product: {product.title}")
            
            # Update status to processing
            product.status = "processing"
            product.updated_at = datetime.utcnow()
            db.commit()
            
            try:
                # Step 1: Research keywords
                processor_logger.info(f"🔍 Step 1: Researching keywords...")
                keywords = await ai_service.research_keywords({
                    "title": product.title,
                    "product_type": product.product_type,
                    "vendor": product.vendor
                }, "product")
                
                if not keywords:
                    raise Exception("No keywords generated")
                
                # Step 2: Generate SEO content
                processor_logger.info(f"📝 Step 2: Generating SEO content...")
                seo_content = await ai_service.generate_seo_content({
                    "title": product.title,
                    "product_type": product.product_type,
                    "vendor": product.vendor
                }, keywords, "product")
                
                if not seo_content:
                    raise Exception("No SEO content generated")
                
                # Step 3: Save to database
                processor_logger.info(f"💾 Step 3: Saving content to database...")
                seo_record = SEOContent(
                    item_id=product.shopify_id,
                    item_type="product",
                    item_title=product.title,
                    seo_title=seo_content.get("seo_title", ""),
                    meta_description=seo_content.get("meta_description", ""),
                    ai_description=seo_content.get("ai_description", ""),
                    keywords_used=keywords
                )
                db.add(seo_record)
                
                # Step 4: Update Shopify (if description was generated)
                shopify_updated = False
                if seo_content.get("ai_description"):
                    processor_logger.info(f"🔄 Step 4: Updating Shopify...")
                    shopify_updated = await shopify.update_product(product.shopify_id, seo_content)
                
                # Step 5: Mark as completed
                product.status = "completed"
                product.seo_written = True
                product.processed_at = datetime.utcnow()
                product.keywords_researched = keywords
                product.updated_at = datetime.utcnow()
                
                # Log the success
                log_api_action(db, "processor", "product_completed", "success", 
                             f"Completed product: {product.title}", 
                             {
                                 "keywords_count": len(keywords),
                                 "shopify_updated": shopify_updated,
                                 "seo_title_length": len(seo_content.get("seo_title", "")),
                                 "meta_desc_length": len(seo_content.get("meta_description", ""))
                             })
                
                total_processed += 1
                processor_logger.info(f"✅ SUCCESS: Product '{product.title}' completed!")
                processor_logger.info(f"   📊 Keywords: {len(keywords)} generated")
                processor_logger.info(f"   📝 Content: SEO title, meta desc, description generated")
                processor_logger.info(f"   🔄 Shopify: {'Updated' if shopify_updated else 'Skipped'}")
                
            except Exception as e:
                product.status = "failed"
                product.updated_at = datetime.utcnow()
                processor_logger.error(f"❌ FAILED: Product '{product.title}' failed: {e}")
                log_api_action(db, "processor", "product_failed", "error", str(e), {"product_title": product.title})
            
            db.commit()
            
            # Rate limiting - wait between products
            processor_logger.info("⏰ Waiting 5 seconds before next product...")
            await asyncio.sleep(5)
        
        # Process collections
        for collection in pending_collections:
            processor_logger.info(f"🎯 Processing collection: {collection.title}")
            
            collection.status = "processing"
            collection.updated_at = datetime.utcnow()
            db.commit()
            
            try:
                # Research keywords for collection
                processor_logger.info(f"🔍 Researching keywords for collection...")
                keywords = await ai_service.research_keywords({
                    "title": collection.title,
                    "products_count": collection.products_count
                }, "collection")
                
                if not keywords:
                    raise Exception("No keywords generated")
                
                # Generate SEO content for collection
                processor_logger.info(f"📝 Generating SEO content for collection...")
                seo_content = await ai_service.generate_seo_content({
                    "title": collection.title,
                    "products_count": collection.products_count
                }, keywords, "collection")
                
                if not seo_content:
                    raise Exception("No SEO content generated")
                
                # Save to database
                seo_record = SEOContent(
                    item_id=collection.shopify_id,
                    item_type="collection",
                    item_title=collection.title,
                    seo_title=seo_content.get("seo_title", ""),
                    meta_description=seo_content.get("meta_description", ""),
                    ai_description=seo_content.get("ai_description", ""),
                    keywords_used=keywords
                )
                db.add(seo_record)
                
                # Update Shopify collection
                shopify_updated = False
                if seo_content.get("ai_description"):
                    processor_logger.info(f"🔄 Updating collection in Shopify...")
                    shopify_updated = await shopify.update_collection(collection.shopify_id, seo_content)
                
                collection.status = "completed"
                collection.seo_written = True
                collection.processed_at = datetime.utcnow()
                collection.keywords_researched = keywords
                collection.updated_at = datetime.utcnow()
                
                total_processed += 1
                processor_logger.info(f"✅ SUCCESS: Collection '{collection.title}' completed!")
                
            except Exception as e:
                collection.status = "failed"
                collection.updated_at = datetime.utcnow()
                processor_logger.error(f"❌ FAILED: Collection '{collection.title}' failed: {e}")
                log_api_action(db, "processor", "collection_failed", "error", str(e), {"collection_title": collection.title})
            
            db.commit()
            await asyncio.sleep(5)
        
        # Final summary
        processor_logger.info("="*50)
        processor_logger.info(f"🎉 PROCESSING BATCH COMPLETE")
        processor_logger.info(f"📊 Total items processed: {total_processed}")
        processor_logger.info(f"💰 OpenAI API calls made: ~{total_processed * 2} (keywords + content)")
        processor_logger.info("="*50)
        
        # Update system stats
        if state:
            state.total_items_processed += total_processed
            db.commit()
        
        # Schedule next batch if there are more pending items
        remaining_products = db.query(Product).filter(Product.status == "pending").count()
        remaining_collections = db.query(Collection).filter(Collection.status == "pending").count()
        
        if remaining_products > 0 or remaining_collections > 0:
            processor_logger.info(f"📋 Remaining: {remaining_products} products, {remaining_collections} collections")
            processor_logger.info("⏰ Next batch will be processed in 2 minutes...")
        else:
            processor_logger.info("🏁 All items processed! System on standby for new items.")
        
    except Exception as e:
        processor_logger.error(f"❌ Critical processing error: {e}")
        processor_logger.error(traceback.format_exc())
    finally:
        db.close()

# API Endpoints
@app.get("/")
async def root():
    return {
        "status": "AI SEO Agent Running",
        "version": "3.1.0 - Automatic Processing",
        "shopify_configured": shopify.configured,
        "openai_configured": ai_service.client is not None,
        "features": ["automatic_processing", "keyword_research", "content_generation", "shopify_updates"]
    }

@app.get("/api/health")
async def health_check():
    """Detailed health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "database": "connected",
            "shopify": "configured" if shopify.configured else "not configured",
            "openai": "configured" if ai_service.client else "not configured"
        },
        "features": {
            "automatic_processing": "enabled",
            "content_generation": "enabled",
            "shopify_updates": "enabled"
        }
    }

@app.get("/api/dashboard")
async def get_dashboard(db: Session = Depends(get_db)):
    """Get comprehensive dashboard data"""
    api_logger.info("📊 Fetching dashboard data")
    
    try:
        state = db.query(SystemState).first()
        if not state:
            state = init_system_state(db)
        
        # Products stats
        total_products = db.query(Product).count()
        completed_products = db.query(Product).filter(Product.status == "completed").count()
        pending_products = db.query(Product).filter(Product.status == "pending").count()
        processing_products = db.query(Product).filter(Product.status == "processing").count()
        
        # Collections stats
        total_collections = db.query(Collection).count()
        completed_collections = db.query(Collection).filter(Collection.status == "completed").count()
        pending_collections = db.query(Collection).filter(Collection.status == "pending").count()
        processing_collections = db.query(Collection).filter(Collection.status == "processing").count()
        
        # Manual queue stats
        manual_queue_count = db.query(ManualQueue).filter(ManualQueue.status == "pending").count()
        
        # Recent activity
        recent_products = db.query(Product).order_by(Product.updated_at.desc()).limit(5).all()
        recent_collections = db.query(Collection).order_by(Collection.updated_at.desc()).limit(5).all()
        
        # Today's stats
        today = datetime.utcnow().date()
        today_start = datetime.combine(today, datetime.min.time())
        
        processed_today = (
            db.query(Product).filter(Product.processed_at >= today_start).count() +
            db.query(Collection).filter(Collection.processed_at >= today_start).count()
        )
        
        recent_activity = []
        for p in recent_products:
            recent_activity.append({
                "id": p.shopify_id,
                "title": p.title,
                "type": "product",
                "status": p.status,
                "updated": p.updated_at.isoformat() if p.updated_at else None,
                "keywords_count": len(p.keywords_researched) if p.keywords_researched else 0
            })
        
        for c in recent_collections:
            recent_activity.append({
                "id": c.shopify_id,
                "title": c.title,
                "type": "collection",
                "status": c.status,
                "updated": c.updated_at.isoformat() if c.updated_at else None,
                "keywords_count": len(c.keywords_researched) if c.keywords_researched else 0
            })
        
        recent_activity.sort(key=lambda x: x["updated"] or "", reverse=True)
        
        api_logger.info(f"📊 Dashboard data: {total_products} products, {total_collections} collections")
        
        return {
            "system": {
                "is_paused": state.is_paused,
                "auto_pause_triggered": state.auto_pause_triggered,
                "auto_processing_enabled": state.auto_processing_enabled,
                "last_scan": state.last_scan.isoformat() if state.last_scan else None,
                "products_found_in_last_scan": state.products_found_in_last_scan,
                "collections_found_in_last_scan": state.collections_found_in_last_scan,
                "total_items_processed": state.total_items_processed
            },
            "stats": {
                "products": {
                    "total": total_products,
                    "completed": completed_products,
                    "pending": pending_products,
                    "processing": processing_products
                },
                "collections": {
                    "total": total_collections,
                    "completed": completed_collections,
                    "pending": pending_collections,
                    "processing": processing_collections
                },
                "manual_queue": manual_queue_count,
                "processed_today": processed_today,
                "total_completed": completed_products + completed_collections
            },
            "recent_activity": recent_activity[:10]
        }
        
    except Exception as e:
        api_logger.error(f"❌ Dashboard error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scan")
async def scan_all(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Scan for products and collections"""
    api_logger.info("🚀 Starting scan operation")
    
    try:
        state = db.query(SystemState).first()
        if not state:
            state = init_system_state(db)
        
        if state.is_paused:
            api_logger.warning("⏸️ System is paused - scan aborted")
            return {"error": "System is paused", "paused": True}
        
        # Log the scan attempt
        log_api_action(db, "system", "scan", "started", "Starting product and collection scan")
        
        # Scan products
        api_logger.info("📦 Scanning products...")
        products = await shopify.get_products()
        new_products = 0
        existing_products = 0
        
        for product in products:
            shopify_id = str(product.get('id'))
            existing = db.query(Product).filter(Product.shopify_id == shopify_id).first()
            
            if not existing:
                new_product = Product(
                    shopify_id=shopify_id,
                    title=product.get('title', ''),
                    handle=product.get('handle', ''),
                    product_type=product.get('product_type', ''),
                    vendor=product.get('vendor', ''),
                    tags=str(product.get('tags', '')),
                    status='pending'
                )
                db.add(new_product)
                new_products += 1
                api_logger.info(f"✅ Added new product: {product.get('title', 'Unknown')}")
            else:
                existing_products += 1
        
        # Scan collections
        api_logger.info("📚 Scanning collections...")
        collections = await shopify.get_collections()
        new_collections = 0
        existing_collections = 0
        
        for collection in collections:
            shopify_id = str(collection.get('id'))
            existing = db.query(Collection).filter(Collection.shopify_id == shopify_id).first()
            
            if not existing:
                new_collection = Collection(
                    shopify_id=shopify_id,
                    title=collection.get('title', ''),
                    handle=collection.get('handle', ''),
                    products_count=collection.get('products_count', 0),
                    status='pending'
                )
                db.add(new_collection)
                new_collections += 1
                api_logger.info(f"✅ Added new collection: {collection.get('title', 'Unknown')}")
            else:
                existing_collections += 1
        
        # Update system state
        state.last_scan = datetime.utcnow()
        state.products_found_in_last_scan = new_products
        state.collections_found_in_last_scan = new_collections
        
        # Safety check
        total_new = new_products + new_collections
        if total_new > 100:
            state.is_paused = True
            state.auto_pause_triggered = True
            api_logger.warning(f"⚠️ AUTO-PAUSE: Found {total_new} new items (limit: 100)")
        
        db.commit()
        
        # 🚀 AUTO-TRIGGER PROCESSING for new items
        if not state.is_paused and total_new > 0:
            api_logger.info(f"🚀 Auto-triggering content generation for {total_new} new items")
            background_tasks.add_task(process_pending_items)
        
        # Log the results
        log_api_action(
            db, "system", "scan", "success",
            f"Scan complete: {new_products} new products, {new_collections} new collections",
            {
                "new_products": new_products,
                "existing_products": existing_products,
                "new_collections": new_collections,
                "existing_collections": existing_collections,
                "auto_processing_triggered": total_new > 0 and not state.is_paused
            }
        )
        
        api_logger.info(f"""
        📊 SCAN RESULTS:
        ├── Products: {new_products} new, {existing_products} existing
        ├── Collections: {new_collections} new, {existing_collections} existing
        ├── Total scanned: {len(products)} products, {len(collections)} collections
        └── Auto-processing: {'Triggered' if total_new > 0 and not state.is_paused else 'Not triggered'}
        """)
        
        return {
            "products_found": new_products,
            "collections_found": new_collections,
            "total_products": len(products),
            "total_collections": len(collections),
            "existing_products": existing_products,
            "existing_collections": existing_collections,
            "auto_processing_triggered": total_new > 0 and not state.is_paused
        }
        
    except Exception as e:
        api_logger.error(f"❌ Scan error: {str(e)}")
        api_logger.error(traceback.format_exc())
        log_api_action(db, "system", "scan", "error", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/process-pending")
async def trigger_processing(background_tasks: BackgroundTasks):
    """Manually trigger processing of pending items"""
    api_logger.info("🚀 Manual processing triggered")
    background_tasks.add_task(process_pending_items)
    return {"message": "Processing started", "status": "success"}

@app.post("/api/pause")
async def toggle_pause(db: Session = Depends(get_db)):
    """Toggle system pause state"""
    state = db.query(SystemState).first()
    if not state:
        state = init_system_state(db)
    
    state.is_paused = not state.is_paused
    state.auto_pause_triggered = False
    db.commit()
    
    status = "paused" if state.is_paused else "running"
    api_logger.info(f"🔄 System status changed to: {status}")
    
    return {"is_paused": state.is_paused}

@app.get("/api/logs")
async def get_logs(db: Session = Depends(get_db)):
    """Get recent generation logs and API logs"""
    try:
        # Get SEO content logs
        seo_logs = db.query(SEOContent).order_by(
            SEOContent.generated_at.desc()
        ).limit(20).all()
        
        # Get API logs
        api_logs = db.query(APILog).order_by(
            APILog.timestamp.desc()
        ).limit(50).all()
        
        return {
            "logs": [
                {
                    "item_id": log.item_id,
                    "item_type": log.item_type,
                    "item_title": log.item_title,
                    "keywords_used": log.keywords_used,
                    "seo_title": log.seo_title,
                    "meta_description": log.meta_description,
                    "generated_at": log.generated_at.isoformat()
                }
                for log in seo_logs
            ],
            "api_logs": [
                {
                    "timestamp": log.timestamp.isoformat(),
                    "service": log.service,
                    "action": log.action,
                    "status": log.status,
                    "message": log.message,
                    "details": log.details
                }
                for log in api_logs
            ]
        }
    except Exception as e:
        api_logger.error(f"❌ Error fetching logs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Additional endpoints for manual queue, etc.
@app.post("/api/manual-queue")
async def add_to_manual_queue(item: ManualQueueItem, db: Session = Depends(get_db)):
    """Add item to manual processing queue"""
    queue_item = ManualQueue(
        item_id=item.item_id,
        item_type=item.item_type,
        title=item.title,
        url=item.url,
        reason=item.reason,
        priority=15,
        status="pending"
    )
    db.add(queue_item)
    db.commit()
    
    api_logger.info(f"Added {item.item_type} '{item.title}' to manual queue")
    
    return {"message": "Item added to queue", "id": queue_item.id}

@app.get("/api/manual-queue")
async def get_manual_queue(db: Session = Depends(get_db)):
    """Get manual queue items"""
    items = db.query(ManualQueue).filter(
        ManualQueue.status == "pending"
    ).order_by(ManualQueue.created_at.desc()).all()
    
    return {
        "items": [
            {
                "id": item.id,
                "item_id": item.item_id,
                "item_type": item.item_type,
                "title": item.title,
                "reason": item.reason,
                "created_at": item.created_at.isoformat()
            }
            for item in items
        ]
    }

@app.delete("/api/manual-queue/{item_id}")
async def remove_from_manual_queue(item_id: int, db: Session = Depends(get_db)):
    """Remove item from manual queue"""
    item = db.query(ManualQueue).filter(ManualQueue.id == item_id).first()
    if item:
        db.delete(item)
        db.commit()
        return {"message": "Item removed from queue"}
    raise HTTPException(status_code=404, detail="Item not found")

@app.post("/api/generate-content")
async def generate_content(request: GenerateContentRequest, db: Session = Depends(get_db)):
    """Generate content for specific item"""
    item_data = None
    
    if request.item_type == "product":
        item_data = db.query(Product).filter(Product.shopify_id == request.item_id).first()
    elif request.item_type == "collection":
        item_data = db.query(Collection).filter(Collection.shopify_id == request.item_id).first()
    
    if not item_data:
        raise HTTPException(status_code=404, detail="Item not found")
    
    # Research keywords
    keywords = await ai_service.research_keywords(
        {"title": item_data.title},
        request.item_type
    )
    
    # Generate content
    content = await ai_service.generate_seo_content(
        {"title": item_data.title},
        keywords,
        request.item_type
    )
    
    if content:
        # Save to database
        seo_record = SEOContent(
            item_id=request.item_id,
            item_type=request.item_type,
            item_title=item_data.title,
            seo_title=content.get("seo_title", ""),
            meta_description=content.get("meta_description", ""),
            ai_description=content.get("ai_description", ""),
            keywords_used=keywords
        )
        db.add(seo_record)
        
        # Update item status
        item_data.status = "completed"
        item_data.seo_written = True
        item_data.processed_at = datetime.utcnow()
        item_data.keywords_researched = keywords
        
        db.commit()
        
        return {
            "success": True,
            "content": content,
            "keywords": keywords
        }
    
    return {"success": False, "error": "Failed to generate content"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    logger.info(f"🚀 Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
