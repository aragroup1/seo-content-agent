import os
from typing import List, Dict, Optional
from dotenv import load_dotenv
import httpx
import json

load_dotenv()

class ShopifyService:
    def __init__(self):
        self.shop_domain = os.getenv("SHOPIFY_SHOP_DOMAIN")
        self.access_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
        self.api_version = "2024-01"
        self.base_url = f"https://{self.shop_domain}/admin/api/{self.api_version}"
        self.headers = {
            "X-Shopify-Access-Token": self.access_token,
            "Content-Type": "application/json"
        }
    
    async def get_products(self, limit=250, since_id=None):
        """Fetch products from Shopify"""
        params = {"limit": limit}
        if since_id:
            params["since_id"] = since_id
            
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/products.json",
                headers=self.headers,
                params=params,
                timeout=30
            )
            if response.status_code == 200:
                return response.json()["products"]
            return []
    
    async def get_product(self, product_id):
        """Get single product"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/products/{product_id}.json",
                headers=self.headers,
                timeout=30
            )
            if response.status_code == 200:
                return response.json()["product"]
            return None
    
    async def update_product(self, product_id: str, seo_data: dict):
        """Update product with SEO content"""
        update_data = {
            "product": {
                "id": product_id,
                "body_html": seo_data.get("ai_description", "")
            }
        }
        
        # Update metafields separately if needed
        if seo_data.get("seo_title"):
            update_data["product"]["title"] = seo_data["seo_title"]
        
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{self.base_url}/products/{product_id}.json",
                headers=self.headers,
                json=update_data,
                timeout=30
            )
            return response.status_code == 200
    
    async def get_products_count(self):
        """Get total product count"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/products/count.json",
                headers=self.headers,
                timeout=30
            )
            if response.status_code == 200:
                return response.json()["count"]
            return 0
