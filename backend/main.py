import os
import json
import psycopg2
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from openai import OpenAI
import shopify

# --- Configuration & Initialization ---
load_dotenv()
app = FastAPI(title="AI SEO Content Agent", version="2.0.0")

# CORS for frontend communication
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)

# --- Database Connection ---
def get_db_connection():
    # Railway provides the DATABASE_URL automatically
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    return conn

# --- Shopify Connection ---
def get_shopify_client():
    shop_url = os.environ.get("SHOPIFY_SHOP_URL") # e.g., "your-shop-name.myshopify.com"
    api_version = os.environ.get("SHOPIFY_API_VERSION", "2024-04")
    # This is for a "Custom App" with "Admin API access token"
    private_app_password = os.environ.get("SHOPIFY_ADMIN_API_PASSWORD")

    if not all([shop_url, private_app_password]):
        raise ValueError("Shopify credentials are not set in environment variables.")

    session = shopify.Session(shop_url, api_version, private_app_password)
    shopify.ShopifyResource.activate_session(session)
    return shopify

# --- Pydantic Models ---
class SEOOutput(BaseModel):
    seo_title: str
    meta_description: str
    ai_description: str

class SystemStatus(BaseModel):
    is_paused: bool
    total_products: int
    processed_products: int
    pending_products: int

# --- Core SEO & AI Functions ---

def perform_keyword_research(product_title: str) -> list[str]:
    """
    Placeholder for keyword research.
    For now, it just cleans up the title into potential keywords.
    """
    print(f"Performing keyword research for: {product_title}")
    # A simple implementation: split title and add variations
    keywords = product_title.lower().split()
    keywords.append(f"buy {product_title.lower()}")
    keywords.append(f"best {product_title.lower()}")
    return list(set(keywords))[:5] # Return top 5 unique keywords

def generate_seo_content_for_product(product_title: str, keywords: list[str]) -> dict:
    """Generates SEO content using OpenAI."""
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    system_prompt = "You are an expert e-commerce SEO copywriter..." # Same prompt as before
    user_prompt = f"""
    Product Title: "{product_title}"
    Target Keywords: {', '.join(keywords)}
    Generate SEO content in JSON format with keys "seo_title", "meta_description", "ai_description".
    """
    chat_completion = client.chat.completions.create(
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        model="gpt-4o-mini", response_format={"type": "json_object"}
    )
    content = chat_completion.choices[0].message.content
    return json.loads(content)

def process_single_product(product_id: int, product_title: str):
    """The full pipeline for one product."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        print(f"Processing product ID {product_id}: {product_title}")
        # 1. Keyword Research
        keywords = perform_keyword_research(product_title)

        # 2. Generate Content
        seo_content = generate_seo_content_for_product(product_title, keywords)

        # 3. Update Shopify (Optional - for safety, we'll just log for now)
        # shopify_client = get_shopify_client()
        # product_to_update = shopify.Product.find(product_id)
        # product_to_update.title = seo_content['seo_title']
        # product_to_update.body_html = seo_content['ai_description']
        # product_to_update.save()
        print(f"Generated content for product {product_id}. In a real scenario, this would update Shopify.")

        # 4. Update our database to mark as 'completed'
        cur.execute(
            """
            UPDATE products
            SET status = 'completed', seo_title = %s, meta_description = %s, ai_description = %s, updated_at = NOW()
            WHERE shopify_id = %s
            """,
            (seo_content['seo_title'], seo_content['meta_description'], seo_content['ai_description'], product_id)
        )
        conn.commit()
    except Exception as e:
        print(f"Error processing product {product_id}: {e}")
        cur.execute("UPDATE products SET status = 'failed', updated_at = NOW() WHERE shopify_id = %s", (product_id,))
        conn.commit()
    finally:
        cur.close()
        conn.close()

# --- API Endpoints ---

@app.get("/", tags=["Status"])
async def health_check():
    return {"status": "ok", "message": "AI SEO Agent v2 is running."}

@app.post("/scan-products", tags=["Actions"])
async def scan_products(background_tasks: BackgroundTasks):
    """Scans Shopify for new products and adds them to the processing queue."""
    try:
        shopify_client = get_shopify_client()
        conn = get_db_connection()
        cur = conn.cursor()

        # Get existing product IDs from our database
        cur.execute("SELECT shopify_id FROM products")
        existing_ids = {row[0] for row in cur.fetchall()}

        # Get all product IDs from Shopify
        all_shopify_products = shopify_client.Product.find()
        new_products_found = []

        for product in all_shopify_products:
            if product.id not in existing_ids:
                new_products_found.append(product)

        # Failsafe: if too many new products, don't do anything.
        if len(new_products_found) > 100:
             # In a real app, you'd set a 'paused' flag here.
            return {"message": f"Failsafe triggered! Found {len(new_products_found)} new products. System paused."}

        # Add new products to our database with 'pending' status
        for product in new_products_found:
            cur.execute(
                "INSERT INTO products (shopify_id, title, status) VALUES (%s, %s, 'pending')",
                (product.id, product.title)
            )
        conn.commit()
        
        # Start processing in the background
        for product in new_products_found:
            background_tasks.add_task(process_single_product, product.id, product.title)

        cur.close()
        conn.close()
        return {"message": f"Scan complete. Found and queued {len(new_products_found)} new products for processing."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status", tags=["Status"], response_model=SystemStatus)
async def get_system_status():
    """Provides a snapshot of the system's state."""
    conn = get_db_connection()
    cur = conn.cursor()
    # For now, pause is not implemented, so it's always false
    is_paused = False
    cur.execute("SELECT COUNT(*) FROM products")
    total_products = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM products WHERE status = 'completed'")
    processed_products = cur.fetchone()[0]
    pending_products = total_products - processed_products
    cur.close()
    conn.close()
    return {
        "is_paused": is_paused,
        "total_products": total_products,
        "processed_products": processed_products,
        "pending_products": pending_products,
    }

# This is a one-time setup endpoint. Run it once after deploying.
@app.post("/setup-database", tags=["Setup"])
async def setup_database():
    """Initializes the database table."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            shopify_id BIGINT UNIQUE NOT NULL,
            title TEXT,
            status VARCHAR(20) DEFAULT 'pending',
            seo_title TEXT,
            meta_description TEXT,
            ai_description TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    """)
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "Database table 'products' is ready."}
