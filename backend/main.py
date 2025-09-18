import os
import json
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Boolean, Text, JSON, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker
from dotenv import load_dotenv
from openai import OpenAI
import httpx
import logging
import enum

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./seo_agent.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Enums
class ContentType(str, enum.Enum):
    PRODUCT = "product"
    COLLECTION = "collection"
    PAGE = "page"
    BLOG = "blog"

class ContentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    REVISION = "revision"

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
    item_type = Column(String)  # product, collection, page
    title = Column(String)
    url = Column(String, nullable=True)
    priority = Column(Integer, default=10)
    reason = Column(String, nullable=True)  # revision, new, custom
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

# Initialize system state
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

# FastAPI app
app = FastAPI(title="AI SEO Content Agent", version="3.0.0")

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
            logger.warning("Shopify credentials not configured")
            self.configured = False
        else:
            self.configured = True
            self.base_url = f"https://{self.shop_domain}/admin/api/{self.api_version}"
            self.headers = {
                "X-Shopify-Access-Token": self.access_token,
                "Content-Type": "application/json"
            }
    
    async def get_products(self, limit=250, since_id=None):
        """Fetch products from Shopify"""
        if not self.configured:
            logger.error("Shopify not configured")
            return []
            
        params = {"limit": limit}
        if since_id:
            params["since_id"] = since_id
            
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/products.json",
                    headers=self.headers,
                    params=params,
                    timeout=30
                )
                if response.status_code == 200:
                    products = response.json()["products"]
                    logger.info(f"Fetched {len(products)} products from Shopify")
                    return products
                else:
                    logger.error(f"Shopify API error: {response.status_code}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching products: {e}")
            return []
    
    async def get_collections(self, limit=250):
        """Fetch collections from Shopify"""
        if not self.configured:
            return []
            
        try:
            async with httpx.AsyncClient() as client:
                # Get smart collections
                smart_response = await client.get(
                    f"{self.base_url}/smart_collections.json",
                    headers=self.headers,
                    params={"limit": limit},
                    timeout=30
                )
                
                # Get custom collections
                custom_response = await client.get(
                    f"{self.base_url}/custom_collections.json",
                    headers=self.headers,
                    params={"limit": limit},
                    timeout=30
                )
                
                collections = []
                if smart_response.status_code == 200:
                    collections.extend(smart_response.json()["smart_collections"])
                if custom_response.status_code == 200:
                    collections.extend(custom_response.json()["custom_collections"])
                
                logger.info(f"Fetched {len(collections)} collections from Shopify")
                return collections
        except Exception as e:
            logger.error(f"Error fetching collections: {e}")
            return []
    
    async def update_product(self, product_id: str, seo_data: dict):
        """Update product with SEO content"""
        if not self.configured:
            return False
            
        update_data = {
            "product": {
                "id": product_id,
                "body_html": seo_data.get("ai_description", "")
            }
        }
        
        if seo_data.get("seo_title"):
            update_data["product"]["title"] = seo_data["seo_title"]
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"{self.base_url}/products/{product_id}.json",
                    headers=self.headers,
                    json=update_data,
                    timeout=30
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Error updating product: {e}")
            return False
    
    async def update_collection(self, collection_id: str, seo_data: dict):
        """Update collection with SEO content"""
        if not self.configured:
            return False
            
        # First, determine if it's a smart or custom collection
        collection_type = await self.get_collection_type(collection_id)
        
        update_data = {
            collection_type: {
                "id": collection_id,
                "body_html": seo_data.get("ai_description", "")
            }
        }
        
        if seo_data.get("seo_title"):
            update_data[collection_type]["title"] = seo_data["seo_title"]
        
        endpoint = f"{collection_type}s" if collection_type else "collections"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"{self.base_url}/{endpoint}/{collection_id}.json",
                    headers=self.headers,
                    json=update_data,
                    timeout=30
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Error updating collection: {e}")
            return False
    
    async def get_collection_type(self, collection_id: str):
        """Determine if collection is smart or custom"""
        if not self.configured:
            return None
            
        try:
            async with httpx.AsyncClient() as client:
                # Try smart collection first
                response = await client.get(
                    f"{self.base_url}/smart_collections/{collection_id}.json",
                    headers=self.headers,
                    timeout=30
                )
                if response.status_code == 200:
                    return "smart_collection"
                
                # Try custom collection
                response = await client.get(
                    f"{self.base_url}/custom_collections/{collection_id}.json",
                    headers=self.headers,
                    timeout=30
                )
                if response.status_code == 200:
                    return "custom_collection"
                    
        except Exception as e:
            logger.error(f"Error determining collection type: {e}")
        
        return None

# AI Service
class AIService:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key)
            self.model = "gpt-3.5-turbo"
        else:
            logger.warning("OpenAI API key not configured")
            self.client = None
    
    async def research_keywords(self, item: dict, item_type: str = "product") -> List[str]:
        """Research keywords for any item type"""
        if not self.client:
            return []
        
        try:
            if item_type == "collection":
                prompt = f"""
                Collection: {item.get('title', '')}
                Products Count: {item.get('products_count', 0)}
                
                Generate 10 high-value SEO keywords for this collection page.
                Include category keywords, buying intent terms, and long-tail variations.
                Return ONLY a comma-separated list of keywords.
                """
            else:
                prompt = f"""
                Product: {item.get('title', '')}
                Type: {item.get('product_type', '')}
                Vendor: {item.get('vendor', '')}
                
                Generate 10 high-value SEO keywords for this product.
                Consider search volume, buyer intent, and long-tail variations.
                Return ONLY a comma-separated list of keywords.
                """
            
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
            logger.info(f"Researched keywords for {item.get('title', 'item')}: {keyword_list[:3]}...")
            return keyword_list
            
        except Exception as e:
            logger.error(f"Keyword research error: {e}")
            return []
    
    async def generate_seo_content(self, item: dict, keywords: List[str], item_type: str = "product") -> dict:
        """Generate SEO content for any item type"""
        if not self.client:
            return {}
        
        try:
            if item_type == "collection":
                prompt = f"""
                Collection: {item.get('title', '')}
                Keywords: {', '.join(keywords[:5])}
                
                Generate SEO content for this collection page:
                1. seo_title (max 60 chars, include main keyword)
                2. meta_description (max 155 chars, compelling for collection pages)
                3. ai_description (300-400 words, HTML format)
                   - Describe the collection theme
                   - Highlight key products/categories
                   - Include buying guides or tips
                   - Use keywords naturally
                   - Add calls to action
                
                Return as JSON with keys: seo_title, meta_description, ai_description
                """
            else:
                prompt = f"""
                Product: {item.get('title', '')}
                Type: {item.get('product_type', '')}
                Keywords: {', '.join(keywords[:5])}
                
                Generate SEO-optimized content:
                1. seo_title (max 60 chars, include main keyword)
                2. meta_description (max 155 chars, compelling)
                3. ai_description (200-300 words, HTML format, naturally include keywords)
                
                Return as JSON with keys: seo_title, meta_description, ai_description
                """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert e-commerce SEO copywriter."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1000,
                response_format={"type": "json_object"}
            )
            
            content = json.loads(response.choices[0].message.content)
            logger.info(f"Generated SEO content for {item.get('title', 'item')}")
            return content
            
        except Exception as e:
            logger.error(f"Content generation error: {e}")
            return {}

# Initialize services
shopify = ShopifyService()
ai_service = AIService()

# API Endpoints
@app.get("/")
async def root():
    return {"status": "AI SEO Agent Running", "version": "3.0.0"}

@app.get("/api/dashboard")
async def get_dashboard(db: Session = Depends(get_db)):
    """Get comprehensive dashboard data"""
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
    
    # Recent activity (combined)
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
    
    return {
        "system": {
            "is_paused": state.is_paused,
            "auto_pause_triggered": state.auto_pause_triggered,
            "last_scan": state.last_scan,
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

@app.post("/api/scan")
async def scan_all(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Scan for products and collections"""
    state = db.query(SystemState).first()
    if not state:
        state = init_system_state(db)
    
    if state.is_paused:
        return {"error": "System is paused", "paused": True}
    
    logger.info("Starting scan...")
    
    # Scan products
    products = await shopify.get_products()
    new_products = 0
    
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
    
    # Scan collections
    collections = await shopify.get_collections()
    new_collections = 0
    
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
    
    # Update system state
    state.last_scan = datetime.utcnow()
    state.products_found_in_last_scan = new_products
    state.collections_found_in_last_scan = new_collections
    
    # Safety check
    total_new = new_products + new_collections
    if total_new > 100:
        state.is_paused = True
        state.auto_pause_triggered = True
        logger.warning(f"AUTO-PAUSE: Found {total_new} new items")
    
    db.commit()
    
    return {
        "products_found": new_products,
        "collections_found": new_collections,
        "total_products": len(products),
        "total_collections": len(collections)
    }

@app.post("/api/manual-queue")
async def add_to_manual_queue(item: ManualQueueItem, db: Session = Depends(get_db)):
    """Add item to manual processing queue"""
    queue_item = ManualQueue(
        item_id=item.item_id,
        item_type=item.item_type,
        title=item.title,
        url=item.url,
        reason=item.reason,
        priority=15,  # Higher priority for manual items
        status="pending"
    )
    db.add(queue_item)
    db.commit()
    
    logger.info(f"Added {item.item_type} '{item.title}' to manual queue")
    
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
        
        db.commit()
        
        return {
            "success": True,
            "content": content,
            "keywords": keywords
        }
    
    return {"success": False, "error": "Failed to generate content"}

@app.post("/api/pause")
async def toggle_pause(db: Session = Depends(get_db)):
    """Toggle system pause state"""
    state = db.query(SystemState).first()
    if not state:
        state = init_system_state(db)
    
    state.is_paused = not state.is_paused
    state.auto_pause_triggered = False
    db.commit()
    
    return {"is_paused": state.is_paused}

@app.get("/api/logs")
async def get_logs(db: Session = Depends(get_db)):
    """Get recent generation logs"""
    logs = db.query(SEOContent).order_by(
        SEOContent.generated_at.desc()
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
            for log in logs
        ]
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
