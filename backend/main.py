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

load_dotenv()

# Log configuration on startup
logger.info("="*50)
logger.info("STARTING AI SEO CONTENT AGENT")
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
        state = SystemState(is_paused=False)
        db.add(state)
        db.commit()
        db_logger.info("Initialized system state")
    return state

# FastAPI app
app = FastAPI(title="AI SEO Content Agent", version="3.0.0")

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
            shopify_logger.error(traceback.format_exc())
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
            prompt = f"Generate 10 SEO keywords for this {item_type}: {item.get('title', '')}. Return only comma-separated keywords."
            
            openai_logger.info(f"📤 Sending request to OpenAI...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an SEO keyword research expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=150
            )
            
            keywords = response.choices[0].message.content.strip()
            keyword_list = [k.strip() for k in keywords.split(',')][:10]
            
            openai_logger.info(f"✅ Generated {len(keyword_list)} keywords: {keyword_list[:3]}...")
            return keyword_list
            
        except Exception as e:
            openai_logger.error(f"❌ Keyword research error: {str(e)}")
            return []

# Initialize services
shopify = ShopifyService()
ai_service = AIService()

# API Endpoints
@app.get("/")
async def root():
    return {
        "status": "AI SEO Agent Running",
        "version": "3.0.0",
        "shopify_configured": shopify.configured,
        "openai_configured": ai_service.client is not None
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
        
        # Collections stats
        total_collections = db.query(Collection).count()
        completed_collections = db.query(Collection).filter(Collection.status == "completed").count()
        pending_collections = db.query(Collection).filter(Collection.status == "pending").count()
        
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
                "updated": p.updated_at.isoformat() if p.updated_at else None
            })
        
        for c in recent_collections:
            recent_activity.append({
                "id": c.shopify_id,
                "title": c.title,
                "type": "collection",
                "status": c.status,
                "updated": c.updated_at.isoformat() if c.updated_at else None
            })
        
        recent_activity.sort(key=lambda x: x["updated"] or "", reverse=True)
        
        api_logger.info(f"📊 Dashboard data: {total_products} products, {total_collections} collections")
        
        return {
            "system": {
                "is_paused": state.is_paused,
                "auto_pause_triggered": state.auto_pause_triggered,
                "last_scan": state.last_scan.isoformat() if state.last_scan else None,
                "products_found_in_last_scan": state.products_found_in_last_scan,
                "collections_found_in_last_scan": state.collections_found_in_last_scan
            },
            "stats": {
                "products": {
                    "total": total_products,
                    "completed": completed_products,
                    "pending": pending_products
                },
                "collections": {
                    "total": total_collections,
                    "completed": completed_collections,
                    "pending": pending_collections
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
        
        # Log the results
        log_api_action(
            db, "system", "scan", "success",
            f"Scan complete: {new_products} new products, {new_collections} new collections",
            {
                "new_products": new_products,
                "existing_products": existing_products,
                "new_collections": new_collections,
                "existing_collections": existing_collections
            }
        )
        
        api_logger.info(f"""
        📊 SCAN RESULTS:
        ├── Products: {new_products} new, {existing_products} existing
        ├── Collections: {new_collections} new, {existing_collections} existing
        └── Total scanned: {len(products)} products, {len(collections)} collections
        """)
        
        return {
            "products_found": new_products,
            "collections_found": new_collections,
            "total_products": len(products),
            "total_collections": len(collections),
            "existing_products": existing_products,
            "existing_collections": existing_collections
        }
        
    except Exception as e:
        api_logger.error(f"❌ Scan error: {str(e)}")
        api_logger.error(traceback.format_exc())
        log_api_action(db, "system", "scan", "error", str(e))
        raise HTTPException(status_code=500, detail=str(e))

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
    
    # For now, just return the keywords (content generation can be added later)
    return {
        "success": True,
        "keywords": keywords,
        "message": "Keywords generated successfully"
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    logger.info(f"🚀 Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
