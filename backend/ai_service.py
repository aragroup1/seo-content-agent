from groq import Groq
import os
import json
from typing import Dict, List
import re

class AIContentGenerator:
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if api_key:
            self.client = Groq(api_key=api_key)
            self.model = "llama-3.1-70b-versatile"
        else:
            self.client = None
            print("Warning: GROQ_API_KEY not set")
        
    async def generate_seo_content(self, product: dict, keywords: List[str] = None) -> dict:
        """Generate all SEO content for a product"""
        
        if not self.client:
            return self._generate_fallback_content(product)
        
        prompt = self._build_prompt(product, keywords)
        
        try:
            completion = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert SEO content writer. Generate compelling, keyword-rich content."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                model=self.model,
                temperature=0.7,
                max_tokens=1000
            )
            
            response_text = completion.choices[0].message.content
            return self._parse_response(response_text, product)
            
        except Exception as e:
            print(f"AI Generation Error: {e}")
            return self._generate_fallback_content(product)
    
    def _build_prompt(self, product: dict, keywords: List[str]) -> str:
        """Build the prompt for AI"""
        keywords_str = ", ".join(keywords) if keywords else product.get("title", "")
        
        return f"""
Product: {product.get('title', '')}
Type: {product.get('product_type', '')}
Brand: {product.get('vendor', '')}

Create SEO content:

1. SEO Title (max 60 chars)
2. Meta Description (max 155 chars) 
3. Product Description (200-300 words, HTML format with <p> tags)
4. Image Alt Text (one sentence)

Use these keywords naturally: {keywords_str}

Format as JSON:
{{
    "seo_title": "",
    "meta_description": "",
    "ai_description": "",
    "alt_text": ""
}}
"""
    
    def _parse_response(self, response: str, product: dict) -> dict:
        """Parse AI response into structured data"""
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                # Ensure all fields exist
                return {
                    "seo_title": result.get("seo_title", product.get("title", ""))[:60],
                    "meta_description": result.get("meta_description", "")[:155],
                    "ai_description": result.get("ai_description", ""),
                    "alt_text": result.get("alt_text", product.get("title", ""))
                }
        except:
            pass
        
        return self._generate_fallback_content(product)
    
    def _generate_fallback_content(self, product: dict) -> dict:
        """Generate basic content if AI fails"""
        title = product.get('title', 'Product')
        vendor = product.get('vendor', 'our store')
        
        return {
            "seo_title": title[:60],
            "meta_description": f"Shop {title} from {vendor}. High quality, fast shipping, great prices.",
            "ai_description": f"<p>{title} from {vendor}.</p><p>Premium quality product available now.</p>",
            "alt_text": title
        }
    
    async def generate_keywords(self, product: dict) -> List[str]:
        """Generate keyword suggestions"""
        if not self.client:
            return self._generate_fallback_keywords(product)
            
        prompt = f"Generate 5 SEO keywords for: {product.get('title')}. Return only comma-separated keywords."
        
        try:
            completion = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.5,
                max_tokens=50
            )
            
            keywords = completion.choices[0].message.content
            return [k.strip() for k in keywords.split(',')][:5]
        except:
            return self._generate_fallback_keywords(product)
    
    def _generate_fallback_keywords(self, product: dict) -> List[str]:
        """Fallback keywords from product data"""
        keywords = []
        if product.get('title'):
            keywords.extend(product['title'].lower().split()[:3])
        if product.get('product_type'):
            keywords.append(product['product_type'].lower())
        return keywords[:5]
