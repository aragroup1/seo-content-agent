from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import asyncio
import os
from contextlib import asynccontextmanager

from database import get_db, Product, SEOContent, QueueItem
from shopify_service import ShopifyService
from ai_service import AIContentGenerator
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Initialize services
shopify = ShopifyService()
ai_generator = AIContentGenerator()
scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    scheduler.start()
    schedule_jobs()
    yield
    # Shutdown
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def schedule_jobs():
    """Schedule recurring jobs"""
    scheduler.add_job(scan_new_products, 'interval', hours=1, id='scan_products', replace_existing=True)
    scheduler.add_job(process_queue, 'interval', minutes=5, id='process_queue', replace_existing=True)

async def scan_new_products():
    """Scan Shopify for new products"""
    db = next(get_db())
    try:
        products = await shopify.get_products(limit=250)
        new_count = 0
        
        for product in products:
            existing = db.query(Product).filter(Product.shopify_id == str(product['id'])).first()
            
            if not existing:
                new_product = Product(
                    shopify_id=str(product['id']),
                    title=product['title'],
                    handle=product.get('handle'),
                    product_type=product.get('product_type'),
                    vendor=product.get('vendor'),
                    tags=str(product.get('tags', '')),
                    status='pending',
                    priority=10
                )
                db.add(new_product)
                
                queue_item = QueueItem(
                    shopify_id=str(product['id']),
                    priority=10,
                    status='pending'
                )
                db.add(queue_item)
                new_count += 1
        
        db.commit()
        print(f"Found {new_count} new products")
        
    except Exception as e:
        print(f"Scan error: {e}")
        db.rollback()
    finally:
        db.close()

async def process_queue():
    """Process products in queue"""
    db = next(get_db())
    try:
        queue_items = db.query(QueueItem).filter(
            QueueItem.status == 'pending'
        ).order_by(
            QueueItem.priority.desc(),
            QueueItem.created_at
        ).limit(5).all()
        
        for item in queue_items:
            try:
                item.status = 'processing'
                db.commit()
                
                product_data = await shopify.get_product(item.shopify_id)
                
                if product_data:
                    keywords = await ai_generator.generate_keywords(product_data)
                    seo_content = await ai_generator.generate_seo_content(product_data, keywords)
                    
                    seo_record = SEOContent(
                        product_id=item.shopify_id,
                        seo_title=seo_content.get('seo_title'),
                        meta_description=seo_content.get('meta_description'),
                        ai_description=seo_content.get('ai_description'),
                        alt_text=seo_content.get('alt_text'),
                        keywords=keywords,
                        focus_keyword=keywords[0] if keywords else '',
                        seo_score=85
                    )
                    db.add(seo_record)
                    
                    success = await shopify.update_product(item.shopify_id, seo_content)
                    
                    if success:
                        item.status = 'completed'
                        item.processed_at = datetime.utcnow()
                        
                        product = db.query(Product).filter(
                            Product.shopify_id == item.shopify_id
                        ).first()
                        if product:
                            product.status = 'completed'
                            product.processed_at = datetime.utcnow()
                    else:
                        item.status = 'failed'
                        item.error_message = 'Failed to update Shopify'
                else:
                    item.status = 'failed'
                    item.error_message = 'Product not found'
                
                item.attempts += 1
                db.commit()
                await asyncio.sleep(2)
                
            except Exception as e:
                print(f"Processing error: {e}")
                item.status = 'failed'
                item.error_message = str(e)
                item.attempts += 1
                db.commit()
        
    except Exception as e:
        print(f"Queue error: {e}")
    finally:
        db.close()

@app.get("/")
async def root():
    return {"status": "SEO Content Agent Running"}

@app.get("/api/stats")
async def get_stats(db: Session = Depends(get_db)):
    """Get dashboard statistics"""
    total_products = db.query(Product).count()
    completed = db.query(Product).filter(Product.status == 'completed').count()
    pending = db.query(Product).filter(Product.status == 'pending').count()
    in_queue = db.query(QueueItem).filter(QueueItem.status == 'pending').count()
    
    today = datetime.utcnow().date()
    today_start = datetime.combine(today, datetime.min.time())
    
    new_today = db.query(Product).filter(Product.created_at >= today_start).count()
    processed_today = db.query(Product).filter(Product.processed_at >= today_start).count()
    
    return {
        "total_products": total_products,
        "completed": completed,
        "pending": pending,
        "in_queue": in_queue,
        "new_today": new_today,
        "processed_today": processed_today,
        "completion_rate": round((completed / total_products * 100) if total_products > 0 else 0, 1)
    }

@app.get("/api/products")
async def get_products(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get products list"""
    query = db.query(Product)
    if status:
        query = query.filter(Product.status == status)
    
    products = query.offset(skip).limit(limit).all()
    return {"products": products, "total": query.count()}

@app.post("/api/products/{product_id}/generate")
async def generate_content(product_id: str, db: Session = Depends(get_db)):
    """Generate content for a product"""
    queue_item = QueueItem(
        shopify_id=product_id,
        priority=10,
        status='pending'
    )
    db.add(queue_item)
    db.commit()
    
    return {"message": "Queued for processing", "product_id": product_id}

@app.post("/api/scan")
async def trigger_scan(background_tasks: BackgroundTasks):
    """Trigger product scan"""
    background_tasks.add_task(scan_new_products)
    return {"message": "Scan initiated"}

@app.post("/api/process-queue")
async def trigger_queue_processing(background_tasks: BackgroundTasks):
    """Trigger queue processing"""
    background_tasks.add_task(process_queue)
    return {"message": "Processing initiated"}

@app.get("/api/queue")
async def get_queue(db: Session = Depends(get_db)):
    """Get queue status"""
    queue_items = db.query(QueueItem).filter(
        QueueItem.status == 'pending'
    ).order_by(
        QueueItem.priority.desc(),
        QueueItem.created_at
    ).limit(20).all()
    
    return {
        "queue": queue_items,
        "total_pending": db.query(QueueItem).filter(QueueItem.status == 'pending').count()
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
