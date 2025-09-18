import os
import json
import psycopg2
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from openai import OpenAI
import shopify

# --- Configuration & Initialization ---
load_dotenv()
app = FastAPI(title="AI SEO Content Agent", version="2.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- Database & Shopify Connections ---
def get_db_connection():
    return psycopg2.connect(os.environ['DATABASE_URL'])

def get_shopify_client():
    session = shopify.Session(os.environ["SHOPIFY_SHOP_URL"], os.environ.get("SHOPIFY_API_VERSION", "2024-04"), os.environ["SHOPIFY_ADMIN_API_PASSWORD"])
    shopify.ShopifyResource.activate_session(session)
    return shopify

# --- Pydantic Models ---
class ManualQueueInput(BaseModel):
    item_id: int
    item_type: str = Field(..., pattern="^(product|collection)$") # Enforce type
    title: str

class SystemStatus(BaseModel):
    is_paused: bool
    total_products: int
    processed_products: int
    total_collections: int
    processed_collections: int
    log_messages: list[str]

# --- Core SEO & AI Logic ---
def perform_keyword_research(title: str, item_type: str) -> list[str]:
    print(f"Keyword research for {item_type}: {title}")
    keywords = title.lower().split()
    keywords.append(f"buy {title.lower()}" if item_type == 'product' else f"{title.lower()} collection")
    return list(set(keywords))[:5]

def generate_seo_content(title: str, keywords: list[str], item_type: str) -> dict:
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    type_specific_prompt = "for a product page." if item_type == 'product' else "for a collection/category page."
    system_prompt = f"You are an expert e-commerce SEO copywriter. Generate compelling, SEO-optimized content {type_specific_prompt} Output must be a single, valid JSON object with keys 'seo_title', 'meta_description', and 'ai_description'."
    user_prompt = f"Title: '{title}', Target Keywords: {', '.join(keywords)}. Requirements: seo_title (max 60 chars), meta_description (max 155 chars), ai_description (200-250 words)."
    
    completion = client.chat.completions.create(
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        model="gpt-4o-mini", response_format={"type": "json_object"}
    )
    return json.loads(completion.choices[0].message.content)

def process_item_task(item_id: int, title: str, item_type: str):
    conn, cur = None, None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        log(f"Processing {item_type} ID {item_id}: {title}")
        
        keywords = perform_keyword_research(title, item_type)
        seo_content = generate_seo_content(title, keywords, item_type)
        
        table = 'products' if item_type == 'product' else 'collections'
        id_column = 'shopify_product_id' if item_type == 'product' else 'shopify_collection_id'
        
        cur.execute(
            f"""
            UPDATE {table} SET status = 'completed', seo_title = %s, meta_description = %s, ai_description = %s, updated_at = NOW()
            WHERE {id_column} = %s
            """,
            (seo_content['seo_title'], seo_content['meta_description'], seo_content['ai_description'], item_id)
        )
        conn.commit()
        log(f"Successfully processed {item_type} ID {item_id}.")
    except Exception as e:
        log(f"ERROR processing {item_type} ID {item_id}: {e}", "error")
        if conn and cur:
            cur.execute(f"UPDATE {table} SET status = 'failed' WHERE {id_column} = %s", (item_id,))
            conn.commit()
    finally:
        if cur: cur.close()
        if conn: conn.close()

# --- Logging System ---
def log(message: str, level: str = "info"):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO logs (level, message) VALUES (%s, %s)", (level, message))
    conn.commit()
    cur.close()
    conn.close()

# --- API Endpoints ---
@app.post("/scan-all", tags=["Actions"])
async def scan_all(background_tasks: BackgroundTasks):
    shopify_client = get_shopify_client()
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Process Products
    cur.execute("SELECT shopify_product_id FROM products")
    existing_product_ids = {row[0] for row in cur.fetchall()}
    new_products = [p for p in shopify_client.Product.find() if p.id not in existing_product_ids]
    
    # Process Collections
    cur.execute("SELECT shopify_collection_id FROM collections")
    existing_collection_ids = {row[0] for row in cur.fetchall()}
    new_collections = [c for c in shopify_client.SmartCollection.find() + shopify_client.CustomCollection.find() if c.id not in existing_collection_ids]
    
    if len(new_products) + len(new_collections) > 100:
        log("Failsafe triggered! Found > 100 new items. Pausing scan.", "warning")
        return {"message": f"Failsafe triggered! Found {len(new_products)} products and {len(new_collections)} collections."}
    
    for p in new_products:
        cur.execute("INSERT INTO products (shopify_product_id, title) VALUES (%s, %s)", (p.id, p.title))
        background_tasks.add_task(process_item_task, p.id, p.title, 'product')
        
    for c in new_collections:
        cur.execute("INSERT INTO collections (shopify_collection_id, title) VALUES (%s, %s)", (c.id, c.title))
        background_tasks.add_task(process_item_task, c.id, c.title, 'collection')

    conn.commit()
    cur.close()
    conn.close()
    
    msg = f"Scan complete. Queued {len(new_products)} new products and {len(new_collections)} new collections."
    log(msg)
    return {"message": msg}

@app.post("/requeue-manual", tags=["Actions"])
async def requeue_manual(item: ManualQueueInput, background_tasks: BackgroundTasks):
    log(f"Manual requeue requested for {item.item_type} ID {item.item_id}")
    background_tasks.add_task(process_item_task, item.item_id, item.title, item.item_type)
    return {"message": f"{item.item_type.capitalize()} '{item.title}' has been re-queued for processing."}

@app.get("/status", tags=["Status"], response_model=SystemStatus)
async def get_system_status():
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM products")
    total_products = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM products WHERE status = 'completed'")
    processed_products = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM collections")
    total_collections = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM collections WHERE status = 'completed'")
    processed_collections = cur.fetchone()[0]

    cur.execute("SELECT message FROM logs ORDER BY created_at DESC LIMIT 5")
    log_messages = [row[0] for row in cur.fetchall()]

    cur.close()
    conn.close()
    
    return {
        "is_paused": False, # Pausing logic not yet implemented
        "total_products": total_products, "processed_products": processed_products,
        "total_collections": total_collections, "processed_collections": processed_collections,
        "log_messages": log_messages
    }

@app.post("/setup-database", tags=["Setup"])
async def setup_database():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY, shopify_product_id BIGINT UNIQUE NOT NULL, title TEXT, status VARCHAR(20) DEFAULT 'pending',
            seo_title TEXT, meta_description TEXT, ai_description TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS collections (
            id SERIAL PRIMARY KEY, shopify_collection_id BIGINT UNIQUE NOT NULL, title TEXT, status VARCHAR(20) DEFAULT 'pending',
            seo_title TEXT, meta_description TEXT, ai_description TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS logs (
            id SERIAL PRIMARY KEY, level VARCHAR(10) DEFAULT 'info', message TEXT, created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    conn.commit()
    cur.close()
    conn.close()
    log("Database setup complete. Tables created.")
    return {"message": "Database tables for products, collections, and logs are ready."}
