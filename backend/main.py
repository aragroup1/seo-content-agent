import os
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

app = FastAPI(title="AI SEO Content Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ProductInput(BaseModel):
    product_title: str
    category: str
    features: list[str]
    keywords: list[str]

class SEOOutput(BaseModel):
    seo_title: str
    meta_description: str
    ai_description: str

@app.get("/", tags=["Status"])
async def health_check():
    return {"status": "ok"}

@app.post("/generate-seo", tags=["SEO"], response_model=SEOOutput)
async def generate_seo_content(product: ProductInput):
    try:
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        system_prompt = "You are an expert e-commerce SEO copywriter. Your task is to generate compelling, SEO-optimized content. Generate the output strictly in a single, valid JSON object with the keys \"seo_title\", \"meta_description\", and \"ai_description\". Do not add any text before or after the JSON object."
        user_prompt = f"""
        Product Information:
        - Title: "{product.product_title}"
        - Category: "{product.category}"
        - Key Features: {', '.join(product.features)}
        - Target Keywords: {', '.join(product.keywords)}

        Content Requirements:
        1.  seo_title: Max 60 characters.
        2.  meta_description: Max 155 characters.
        3.  ai_description: 200-250 words.

        Generate the JSON response now.
        """
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
        )
        content = chat_completion.choices[0].message.content
        seo_content = json.loads(content)
        return SEOOutput(**seo_content)
    except Exception as e:
        print(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=str(e))
