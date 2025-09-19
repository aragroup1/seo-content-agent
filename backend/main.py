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
geo_logger = logging.getLogger("geo")

load_dotenv()

# Log configuration on startup
logger.info("="*60)
logger.info("STARTING AI SEO CONTENT AGENT - GEO OPTIMIZED")
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

# Define Base BEFORE using it in model classes
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
    geo_optimized = Column(Boolean, default=False)  # NEW: GEO optimization flag
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
    geo_optimized = Column(Boolean, default=False)  # NEW: GEO optimization flag
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
    
    # NEW: GEO-specific fields
    faq_content = Column(JSON)  # FAQ sections for AI snippets
    schema_markup = Column(JSON)  # Structured data
    voice_search_optimized = Column(Boolean, default=False)
    featured_snippet_content = Column(Text)  # Content optimized for featured snippets
    
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
    geo_optimization_enabled = Column(Boolean, default=True)  # NEW: GEO toggle

class APILog(Base):
    __tablename__ = "api_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    service = Column(String)
    action = Column(String)
    status = Column(String)
    message = Column(Text)
    details = Column(JSON, nullable=True)

# Create tables with migration handling
try:
    # Drop and recreate tables to handle schema changes
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db_logger.info("✅ Database tables recreated with new schema")
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
        state = SystemState(
            is_paused=False, 
            geo_optimization_enabled=True,
            total_items_processed=0
        )
        db.add(state)
        db.commit()
        db_logger.info("Initialized system state with GEO optimization enabled")
    return state

# FastAPI app
app = FastAPI(title="AI SEO Content Agent - GEO Optimized", version="4.0.0")

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
        """Update product with GEO-optimized content"""
        if not self.configured:
            shopify_logger.warning("⚠️ Cannot update product - Shopify not configured")
            return False
        
        shopify_logger.info(f"📝 Updating product {product_id} with GEO content")
        
        # Build comprehensive product description with GEO optimization
        description = seo_data.get("ai_description", "")
        
        # Add FAQ section if available
        if seo_data.get("faq_content"):
            faq_html = self._build_faq_html(seo_data["faq_content"])
            description += f"\n\n{faq_html}"
        
        # Add structured data as HTML comments for later processing
        if seo_data.get("schema_markup"):
            schema_comment = f"<!-- SCHEMA_DATA: {json.dumps(seo_data['schema_markup'])} -->"
            description = schema_comment + "\n" + description
        
        update_data = {
            "product": {
                "id": product_id,
                "body_html": description,
                "metafields": [
                    {
                        "namespace": "seo",
                        "key": "geo_optimized",
                        "value": "true",
                        "type": "single_line_text_field"
                    }
                ]
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
                    shopify_logger.info(f"✅ Successfully updated product {product_id} with GEO content")
                    return True
                else:
                    shopify_logger.error(f"❌ Failed to update product {product_id}: {response.status_code}")
                    return False
                    
        except Exception as e:
            shopify_logger.error(f"❌ Exception updating product {product_id}: {e}")
            return False
    
    def _build_faq_html(self, faq_content: List[Dict]) -> str:
        """Build HTML for FAQ section with schema markup"""
        html = '<div class="faq-section">\n<h3>Frequently Asked Questions</h3>\n'
        
        for faq in faq_content:
            html += f'''
<div class="faq-item" itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
    <h4 itemprop="name">{faq.get("question", "")}</h4>
    <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
        <p itemprop="text">{faq.get("answer", "")}</p>
    </div>
</div>
'''
        
        html += '</div>'
        return html

# GEO-Optimized AI Service
class GEOAIService:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key)
            self.model = "gpt-3.5-turbo"
            geo_logger.info(f"✅ GEO AI Service configured with model: {self.model}")
        else:
            geo_logger.warning("⚠️ OpenAI API key not configured")
            self.client = None
    
    async def research_geo_keywords(self, item: dict, item_type: str = "product") -> List[str]:
        """Research keywords optimized for Generative Engine Optimization"""
        if not self.client:
            geo_logger.error("❌ Cannot research keywords - OpenAI not configured")
            return []
        
        geo_logger.info(f"🔍 Researching GEO keywords for {item_type}: {item.get('title', 'Unknown')}")
        
        try:
            if item_type == "collection":
                prompt = f"""
                Generate 10 GEO-optimized keywords for this collection, focusing on Generative AI search patterns:
                
                Collection: {item.get('title', '')}
                Products in collection: {item.get('products_count', 0)}
                
                Focus on:
                1. Conversational search queries (how people ask AI assistants)
                2. Question-based keywords ("what is best...", "how to choose...")
                3. Comparison keywords ("vs", "compared to", "difference between")
                4. Intent-driven phrases ("buy", "reviews", "guide")
                5. Long-tail natural language queries
                6. Voice search friendly phrases
                
                Return only comma-separated keywords that work well with AI search engines.
                """
            else:
                prompt = f"""
                Generate 10 GEO-optimized keywords for this product, focusing on Generative AI search patterns:
                
                Product: {item.get('title', '')}
                Type: {item.get('product_type', '')}
                Brand: {item.get('vendor', '')}
                
                Focus on:
                1. Conversational search queries (how people ask AI assistants)
                2. Question-based keywords ("what is the best...", "how does...work")
                3. Problem-solution keywords ("for [problem]", "helps with...")
                4. Comparison keywords ("vs competitors", "alternative to...")
                5. Buying intent phrases ("buy online", "best price", "reviews")
                6. Voice search friendly natural language
                
                Return only comma-separated keywords optimized for AI search engines.
                """
            
            geo_logger.info(f"📤 Sending GEO keyword request to OpenAI...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a Generative Engine Optimization (GEO) expert specializing in keywords that perform well with AI search engines like ChatGPT, Bard, and Claude."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.6,
                max_tokens=200
            )
            
            keywords = response.choices[0].message.content.strip()
            keyword_list = [k.strip().lower() for k in keywords.split(',')][:10]
            
            geo_logger.info(f"✅ Generated {len(keyword_list)} GEO keywords: {keyword_list[:3]}...")
            return keyword_list
            
        except Exception as e:
            geo_logger.error(f"❌ GEO keyword research error: {str(e)}")
            return []
    
    async def generate_geo_content(self, item: dict, keywords: List[str], item_type: str = "product") -> dict:
        """Generate content optimized for Generative Engine Optimization"""
        if not self.client:
            geo_logger.error("❌ Cannot generate GEO content - OpenAI not configured")
            return {}
        
        geo_logger.info(f"🚀 Generating GEO-optimized content for {item_type}: {item.get('title', 'Unknown')}")
        
        try:
            if item_type == "collection":
                prompt = f"""
                Create GEO-optimized content for this collection that performs well with AI search engines:
                
                Collection: {item.get('title', '')}
                Products in collection: {item.get('products_count', 0)}
                Target Keywords: {', '.join(keywords[:6])}
                
                Generate JSON with ALL these fields:
                {{
                    "seo_title": "SEO title (max 60 chars, natural language, question-answering friendly)",
                    "meta_description": "Meta description (max 155 chars, conversational, includes value proposition)",
                    "ai_description": "Collection description (400-500 words in HTML with <p>, <h3>, and <ul> tags. Write in natural, conversational tone. Include buying guides, comparisons, and answer common questions. Use structured formatting that AI can easily parse and quote.)",
                    "faq_content": [
                        {{"question": "What makes this collection special?", "answer": "Detailed answer"}},
                        {{"question": "How to choose the right product?", "answer": "Detailed answer"}},
                        {{"question": "What are the key benefits?", "answer": "Detailed answer"}}
                    ],
                    "featured_snippet_content": "Concise 50-word answer optimized for featured snippets that directly answers 'What is [collection name]?'",
                    "schema_markup": {{
                        "@type": "CollectionPage",
                        "name": "{item.get('title', '')}",
                        "description": "Brief description",
                        "numberOfItems": {item.get('products_count', 0)}
                    }}
                }}
                
                Optimize for:
                - Natural language patterns AI engines understand
                - Question-answer format
                - Clear, scannable structure
                - Conversational tone
                - Value-focused messaging
                """
            else:
                prompt = f"""
                Create GEO-optimized content for this product that performs well with AI search engines:
                
                Product: {item.get('title', '')}
                Type: {item.get('product_type', '')}
                Brand: {item.get('vendor', '')}
                Target Keywords: {', '.join(keywords[:6])}
                
                Generate JSON with ALL these fields:
                {{
                    "seo_title": "SEO title (max 60 chars, natural language, benefit-focused)",
                    "meta_description": "Meta description (max 155 chars, conversational, clear value prop)",
                    "ai_description": "Product description (300-400 words in HTML with <p>, <h3>, and <ul> tags. Write conversationally. Include benefits, use cases, and comparisons. Structure for easy AI parsing and quoting.)",
                    "faq_content": [
                        {{"question": "What problem does this solve?", "answer": "Detailed answer"}},
                        {{"question": "How does it work?", "answer": "Detailed answer"}},
                        {{"question": "Why choose this over alternatives?", "answer": "Detailed answer"}}
                    ],
                    "featured_snippet_content": "Concise 50-word answer optimized for 'What is [product name]?' queries",
                    "schema_markup": {{
                        "@type": "Product",
                        "name": "{item.get('title', '')}",
                        "category": "{item.get('product_type', '')}",
                        "brand": "{item.get('vendor', '')}"
                    }}
                }}
                
                Optimize for:
                - Conversational AI interactions
                - Question-answer format
                - Benefit-driven language
                - Natural language patterns
                - Clear value propositions
                """
            
            geo_logger.info(f"📤 Sending GEO content generation request to OpenAI...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a Generative Engine Optimization (GEO) expert. Create content that AI search engines like ChatGPT, Claude, and Bard can easily understand, parse, and recommend to users. Focus on natural language, clear structure, and direct answers to common questions."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1500,
                response_format={"type": "json_object"}
            )
            
            content = json.loads(response.choices[0].message.content)
            
            # Ensure content limits
            if content.get("seo_title"):
                content["seo_title"] = content["seo_title"][:60]
            if content.get("meta_description"):
                content["meta_description"] = content["meta_description"][:155]
            
            # Ensure FAQ content exists
            if not content.get("faq_content"):
                content["faq_content"] = []
            
            # Mark as voice search optimized if FAQ content exists
            content["voice_search_optimized"] = len(content.get("faq_content", [])) >= 3
            
            geo_logger.info(f"✅ Successfully generated GEO-optimized content")
            geo_logger.info(f"   📝 FAQs: {len(content.get('faq_content', []))} questions")
            geo_logger.info(f"   🗣️ Voice optimized: {content.get('voice_search_optimized', False)}")
            
            return content
            
        except Exception as e:
            geo_logger.error(f"❌ GEO content generation error: {str(e)}")
            return {}

# Initialize services
shopify = ShopifyService()
geo_ai = GEOAIService()

# AUTOMATIC GEO-OPTIMIZED PROCESSING
async def process_pending_items():
    """🚀 Process pending items with GEO optimization"""
    db = SessionLocal()
    try:
        processor_logger.info("="*60)
        processor_logger.info("🚀 STARTING GEO-OPTIMIZED CONTENT GENERATION")
        processor_logger.info("="*60)
        
        # Check if system is paused
        state = db.query(SystemState).first()
        if not state:
            state = init_system_state(db)
        
        if state.is_paused:
            processor_logger.warning("⏸️ System is paused - stopping processing")
            return
        
        if not state.geo_optimization_enabled:
            processor_logger.warning("⏸️ GEO optimization disabled - stopping")
            return
        
        # Get pending items
        pending_products = db.query(Product).filter(
            Product.status == "pending"
        ).limit(2).all()  # Process 2 products at a time (GEO content is more complex)
        
        pending_collections = db.query(Collection).filter(
            Collection.status == "pending"  
        ).limit(1).all()  # Process 1 collection at a time
        
        total_processed = 0
        
        processor_logger.info(f"📋 Found {len(pending_products)} pending products, {len(pending_collections)} pending collections")
        
        # Process products with GEO optimization
        for product in pending_products:
            processor_logger.info(f"🎯 Processing product with GEO: {product.title}")
            
            product.status = "processing"
            product.updated_at = datetime.utcnow()
            db.commit()
            
            try:
                # Step 1: GEO keyword research
                processor_logger.info(f"🔍 Step 1: GEO keyword research...")
                keywords = await geo_ai.research_geo_keywords({
                    "title": product.title,
                    "product_type": product.product_type,
                    "vendor": product.vendor
                }, "product")
                
                if not keywords:
                    raise Exception("No GEO keywords generated")
                
                # Step 2: Generate GEO-optimized content
                processor_logger.info(f"🚀 Step 2: Generating GEO content...")
                geo_content = await geo_ai.generate_geo_content({
                    "title": product.title,
                    "product_type": product.product_type,
                    "vendor": product.vendor
                }, keywords, "product")
                
                if not geo_content:
                    raise Exception("No GEO content generated")
                
                # Step 3: Save comprehensive SEO content
                processor_logger.info(f"💾 Step 3: Saving GEO content...")
                seo_record = SEOContent(
                    item_id=product.shopify_id,
                    item_type="product",
                    item_title=product.title,
                    seo_title=geo_content.get("seo_title", ""),
                    meta_description=geo_content.get("meta_description", ""),
                    ai_description=geo_content.get("ai_description", ""),
                    keywords_used=keywords,
                    faq_content=geo_content.get("faq_content", []),
                    schema_markup=geo_content.get("schema_markup", {}),
                    voice_search_optimized=geo_content.get("voice_search_optimized", False),
                    featured_snippet_content=geo_content.get("featured_snippet_content", "")
                )
                db.add(seo_record)
                
                # Step 4: Update Shopify with GEO content
                shopify_updated = False
                if geo_content.get("ai_description"):
                    processor_logger.info(f"🔄 Step 4: Updating Shopify with GEO content...")
                    shopify_updated = await shopify.update_product(product.shopify_id, geo_content)
                
                # Step 5: Mark as completed and GEO optimized
                product.status = "completed"
                product.seo_written = True
                product.geo_optimized = True
                product.processed_at = datetime.utcnow()
                product.keywords_researched = keywords
                product.updated_at = datetime.utcnow()
                
                log_api_action(db, "geo_processor", "product_completed", "success", 
                             f"GEO optimized product: {product.title}", 
                             {
                                 "keywords_count": len(keywords),
                                 "faq_count": len(geo_content.get("faq_content", [])),
                                 "voice_optimized": geo_content.get("voice_search_optimized", False),
                                 "shopify_updated": shopify_updated
                             })
                
                total_processed += 1
                processor_logger.info(f"✅ GEO SUCCESS: Product '{product.title}' completed!")
                processor_logger.info(f"   🔍 Keywords: {len(keywords)} GEO keywords")
                processor_logger.info(f"   ❓ FAQs: {len(geo_content.get('faq_content', []))} questions")
                processor_logger.info(f"   🗣️ Voice optimized: {geo_content.get('voice_search_optimized', False)}")
                processor_logger.info(f"   🔄 Shopify: {'Updated with GEO content' if shopify_updated else 'Skipped'}")
                
            except Exception as e:
                product.status = "failed"
                product.updated_at = datetime.utcnow()
                processor_logger.error(f"❌ GEO FAILED: Product '{product.title}': {e}")
                log_api_action(db, "geo_processor", "product_failed", "error", str(e))
            
            db.commit()
            processor_logger.info("⏰ Waiting 8 seconds before next product...")
            await asyncio.sleep(8)  # Longer delay for GEO processing
        
        # Process collections with GEO optimization
        for collection in pending_collections:
            processor_logger.info(f"🎯 Processing collection with GEO: {collection.title}")
            
            collection.status = "processing"
            collection.updated_at = datetime.utcnow()
            db.commit()
            
            try:
                # GEO keyword research for collection
                keywords = await geo_ai.research_geo_keywords({
                    "title": collection.title,
                    "products_count": collection.products_count
                }, "collection")
                
                if not keywords:
                    raise Exception("No GEO keywords generated")
                
                # Generate GEO content for collection
                geo_content = await geo_ai.generate_geo_content({
                    "title": collection.title,
                    "products_count": collection.products_count
                }, keywords, "collection")
                
                if not geo_content:
                    raise Exception("No GEO content generated")
                
                # Save GEO content
                seo_record = SEOContent(
                    item_id=collection.shopify_id,
                    item_type="collection",
                    item_title=collection.title,
                    seo_title=geo_content.get("seo_title", ""),
                    meta_description=geo_content.get("meta_description", ""),
                    ai_description=geo_content.get("ai_description", ""),
                    keywords_used=keywords,
                    faq_content=geo_content.get("faq_content", []),
                    schema_markup=geo_content.get("schema_markup", {}),
                    voice_search_optimized=geo_content.get("voice_search_optimized", False),
                    featured_snippet_content=geo_content.get("featured_snippet_content", "")
                )
                db.add(seo_record)
                
                collection.status = "completed"
                collection.seo_written = True
                collection.geo_optimized = True
                collection.processed_at = datetime.utcnow()
                collection.keywords_researched = keywords
                collection.updated_at = datetime.utcnow()
                
                total_processed += 1
                processor_logger.info(f"✅ GEO SUCCESS: Collection '{collection.title}' completed!")
                
            except Exception as e:
                collection.status = "failed"
                collection.updated_at = datetime.utcnow()
                processor_logger.error(f"❌ GEO FAILED: Collection '{collection.title}': {e}")
            
            db.commit()
            await asyncio.sleep(8)
        
        # Final summary
        processor_logger.info("="*60)
        processor_logger.info(f"🎉 GEO PROCESSING BATCH COMPLETE")
        processor_logger.info(f"📊 Total items processed: {total_processed}")
        processor_logger.info(f"🚀 All content optimized for Generative AI engines")
        processor_logger.info("="*60)
        
        # Update system stats
        if state:
            state.total_items_processed += total_processed
            db.commit()
        
    except Exception as e:
        processor_logger.error(f"❌ Critical GEO processing error: {e}")
        processor_logger.error(traceback.format_exc())
    finally:
        db.close()

# API Endpoints
@app.get("/")
async def root():
    return {
        "status": "AI SEO Agent Running - GEO Optimized",
        "version": "4.0.0 - Generative Engine Optimization",
        "shopify_configured": shopify.configured,
        "openai_configured": geo_ai.client is not None,
        "features": [
            "generative_engine_optimization", 
            "geo_keyword_research", 
            "faq_generation",
            "voice_search_optimization",
            "featured_snippet_optimization",
            "schema_markup",
            "conversational_content"
        ]
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
            "openai": "configured" if geo_ai.client else "not configured"
        },
        "geo_features": {
            "keyword_research": "enabled",
            "faq_generation": "enabled",
            "voice_search_optimization": "enabled",
            "featured_snippets": "enabled",
            "schema_markup": "enabled"
        }
    }

@app.get("/api/dashboard")
async def get_dashboard(db: Session = Depends(get_db)):
    """Get comprehensive dashboard data"""
    api_logger.info("📊 Fetching GEO dashboard data")
    
    try:
        state = db.query(SystemState).first()
        if not state:
            state = init_system_state(db)
        
        # Products stats
        total_products = db.query(Product).count()
        completed_products = db.query(Product).filter(Product.status == "completed").count()
        pending_products = db.query(Product).filter(Product.status == "pending").count()
        processing_products = db.query(Product).filter(Product.status == "processing").count()
        geo_optimized_products = db.query(Product).filter(Product.geo_optimized == True).count()
        
        # Collections stats
        total_collections = db.query(Collection).count()
        completed_collections = db.query(Collection).filter(Collection.status == "completed").count()
        pending_collections = db.query(Collection).filter(Collection.status == "pending").count()
        processing_collections = db.query(Collection).filter(Collection.status == "processing").count()
        geo_optimized_collections = db.query(Collection).filter(Collection.geo_optimized == True).count()
        
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
        
        # GEO-specific stats
        voice_optimized_count = db.query(SEOContent).filter(
            SEOContent.voice_search_optimized == True
        ).count()
        
        faq_enabled_count = db.query(SEOContent).filter(
            SEOContent.faq_content.isnot(None)
        ).count()
        
        recent_activity = []
        for p in recent_products:
            recent_activity.append({
                "id": p.shopify_id,
                "title": p.title,
                "type": "product",
                "status": p.status,
                "geo_optimized": p.geo_optimized,
                "updated": p.updated_at.isoformat() if p.updated_at else None,
                "keywords_count": len(p.keywords_researched) if p.keywords_researched else 0
            })
        
        for c in recent_collections:
            recent_activity.append({
                "id": c.shopify_id,
                "title": c.title,
                "type": "collection",
                "status": c.status,
                "geo_optimized": c.geo_optimized,
                "updated": c.updated_at.isoformat() if c.updated_at else None,
                "keywords_count": len(c.keywords_researched) if c.keywords_researched else 0
            })
        
        recent_activity.sort(key=lambda x: x["updated"] or "", reverse=True)
        
        return {
            "system": {
                "is_paused": state.is_paused,
                "auto_pause_triggered": state.auto_pause_triggered,
                "geo_optimization_enabled": state.geo_optimization_enabled,
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
                    "processing": processing_products,
                    "geo_optimized": geo_optimized_products
                },
                "collections": {
                    "total": total_collections,
                    "completed": completed_collections,
                    "pending": pending_collections,
                    "processing": processing_collections,
                    "geo_optimized": geo_optimized_collections
                },
                "geo_features": {
                    "voice_optimized": voice_optimized_count,
                    "faq_enabled": faq_enabled_count,
                    "total_geo_optimized": geo_optimized_products + geo_optimized_collections
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
    api_logger.info("🚀 Starting GEO scan operation")
    
    try:
        state = db.query(SystemState).first()
        if not state:
            state = init_system_state(db)
        
        if state.is_paused:
            api_logger.warning("⏸️ System is paused - scan aborted")
            return {"error": "System is paused", "paused": True}
        
        log_api_action(db, "system", "geo_scan", "started", "Starting GEO-optimized scan")
        
        # Scan products
        api_logger.info("📦 Scanning products for GEO optimization...")
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
                    status='pending',
                    geo_optimized=False
                )
                db.add(new_product)
                new_products += 1
                api_logger.info(f"✅ Added new product for GEO: {product.get('title', 'Unknown')}")
            else:
                existing_products += 1
        
        # Scan collections
        api_logger.info("📚 Scanning collections for GEO optimization...")
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
                    status='pending',
                    geo_optimized=False
                )
                db.add(new_collection)
                new_collections += 1
                api_logger.info(f"✅ Added new collection for GEO: {collection.get('title', 'Unknown')}")
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
            api_logger.warning(f"⚠️ AUTO-PAUSE: Found {total_new} new items")
        
        db.commit()
        
        # Auto-trigger GEO processing
        if not state.is_paused and total_new > 0:
            api_logger.info(f"🚀 Auto-triggering GEO optimization for {total_new} new items")
            background_tasks.add_task(process_pending_items)
        
        log_api_action(db, "system", "geo_scan", "success",
                     f"GEO scan complete: {new_products} products, {new_collections} collections",
                     {"geo_processing_triggered": total_new > 0 and not state.is_paused})
        
        return {
            "products_found": new_products,
            "collections_found": new_collections,
            "total_products": len(products),
            "total_collections": len(collections),
            "existing_products": existing_products,
            "existing_collections": existing_collections,
            "geo_processing_triggered": total_new > 0 and not state.is_paused
        }
        
    except Exception as e:
        api_logger.error(f"❌ GEO scan error: {str(e)}")
        log_api_action(db, "system", "geo_scan", "error", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/process-pending")
async def trigger_processing(background_tasks: BackgroundTasks):
    """Manually trigger GEO processing"""
    api_logger.info("🚀 Manual GEO processing triggered")
    background_tasks.add_task(process_pending_items)
    return {"message": "GEO processing started", "status": "success"}

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
    api_logger.info(f"🔄 GEO system status: {status}")
    
    return {"is_paused": state.is_paused}

@app.get("/api/logs")
async def get_logs(db: Session = Depends(get_db)):
    """Get recent GEO logs"""
    try:
        # Get SEO content logs with GEO data
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
                    "faq_count": len(log.faq_content) if log.faq_content else 0,
                    "voice_optimized": log.voice_search_optimized,
                    "has_schema": bool(log.schema_markup),
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
        api_logger.error(f"❌ Error fetching GEO logs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Manual queue endpoints
@app.post("/api/manual-queue")
async def add_to_manual_queue(item: ManualQueueItem, db: Session = Depends(get_db)):
    """Add item to manual GEO processing queue"""
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
    
    api_logger.info(f"Added {item.item_type} '{item.title}' to GEO manual queue")
    
    return {"message": "Item added to GEO queue", "id": queue_item.id}

@app.get("/api/manual-queue")
async def get_manual_queue(db: Session = Depends(get_db)):
    """Get manual GEO queue items"""
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
    """Remove item from manual GEO queue"""
    item = db.query(ManualQueue).filter(ManualQueue.id == item_id).first()
    if item:
        db.delete(item)
        db.commit()
        return {"message": "Item removed from GEO queue"}
    raise HTTPException(status_code=404, detail="Item not found")

@app.post("/api/generate-content")
async def generate_content(request: GenerateContentRequest, db: Session = Depends(get_db)):
    """Generate GEO content for specific item"""
    item_data = None
    
    if request.item_type == "product":
        item_data = db.query(Product).filter(Product.shopify_id == request.item_id).first()
    elif request.item_type == "collection":
        item_data = db.query(Collection).filter(Collection.shopify_id == request.item_id).first()
    
    if not item_data:
        raise HTTPException(status_code=404, detail="Item not found")
    
    # Research GEO keywords
    keywords = await geo_ai.research_geo_keywords(
        {"title": item_data.title},
        request.item_type
    )
    
    # Generate GEO content
    content = await geo_ai.generate_geo_content(
        {"title": item_data.title},
        keywords,
        request.item_type
    )
    
    if content:
        # Save GEO content
        seo_record = SEOContent(
            item_id=request.item_id,
            item_type=request.item_type,
            item_title=item_data.title,
            seo_title=content.get("seo_title", ""),
            meta_description=content.get("meta_description", ""),
            ai_description=content.get("ai_description", ""),
            keywords_used=keywords,
            faq_content=content.get("faq_content", []),
            schema_markup=content.get("schema_markup", {}),
            voice_search_optimized=content.get("voice_search_optimized", False),
            featured_snippet_content=content.get("featured_snippet_content", "")
        )
        db.add(seo_record)
        
        # Update item status
        item_data.status = "completed"
        item_data.seo_written = True
        item_data.geo_optimized = True
        item_data.processed_at = datetime.utcnow()
        item_data.keywords_researched = keywords
        
        db.commit()
        
        return {
            "success": True,
            "content": content,
            "keywords": keywords,
            "geo_features": {
                "faq_count": len(content.get("faq_content", [])),
                "voice_optimized": content.get("voice_search_optimized", False),
                "has_schema": bool(content.get("schema_markup")),
                "featured_snippet": bool(content.get("featured_snippet_content"))
            }
        }
    
    return {"success": False, "error": "Failed to generate GEO content"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    logger.info(f"🚀 Starting GEO-optimized server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
