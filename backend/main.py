import os
import json
import asyncio
import re
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Boolean, Text, JSON
from sqlalchemy.orm import declarative_base, Session, sessionmaker
from dotenv import load_dotenv
from openai import OpenAI
import httpx
import logging
import traceback

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("main")
shopify_logger = logging.getLogger("shopify")
openai_logger = logging.getLogger("openai")
db_logger = logging.getLogger("database")
api_logger = logging.getLogger("api")
processor_logger = logging.getLogger("processor")

load_dotenv()

# --- Database Setup ---
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"): DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else: DATABASE_URL = "sqlite:///./seo_agent.db"
engine = create_engine(DATABASE_URL); SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine); Base = declarative_base()

# --- Database Models ---
class Product(Base):
    __tablename__ = "products"; id=Column(Integer,primary_key=True); shopify_id=Column(String,unique=True,index=True); title=Column(String); handle=Column(String,nullable=True); status=Column(String,default="pending"); seo_written=Column(Boolean,default=False); created_at=Column(DateTime,default=datetime.utcnow); updated_at=Column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow); processed_at=Column(DateTime,nullable=True)
class Collection(Base):
    __tablename__ = "collections"; id=Column(Integer,primary_key=True); shopify_id=Column(String,unique=True,index=True); title=Column(String); handle=Column(String,nullable=True); products_count=Column(Integer,default=0); status=Column(String,default="pending"); seo_written=Column(Boolean,default=False); created_at=Column(DateTime,default=datetime.utcnow); updated_at=Column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow); processed_at=Column(DateTime,nullable=True)
class SEOContent(Base):
    __tablename__ = "seo_content"; id=Column(Integer,primary_key=True); item_id=Column(String,index=True); item_type=Column(String); item_title=Column(String); seo_title=Column(String); meta_description=Column(String,nullable=True); ai_description=Column(Text,nullable=True); generated_at=Column(DateTime,default=datetime.utcnow)
class SystemState(Base):
    __tablename__ = "system_state"; id=Column(Integer,primary_key=True); is_paused=Column(Boolean,default=False); auto_pause_triggered=Column(Boolean,default=False); last_scan=Column(DateTime,nullable=True); products_found_in_last_scan=Column(Integer,default=0); collections_found_in_last_scan=Column(Integer,default=0); total_items_processed=Column(Integer,default=0)
class APILog(Base):
    __tablename__ = "api_logs"; id=Column(Integer, primary_key=True, index=True); timestamp=Column(DateTime, default=datetime.utcnow); service=Column(String); action=Column(String); status=Column(String); message=Column(Text)
try: Base.metadata.create_all(bind=engine); db_logger.info("✅ Database tables created/verified successfully")
except Exception as e: db_logger.error(f"❌ Database error on table creation: {e}")

def get_db():
    db = SessionLocal();
    try: yield db
    finally: db.close()
def init_system_state(db: Session):
    state = db.query(SystemState).first()
    if not state: state=SystemState(is_paused=False); db.add(state); db.commit()
    return state
def log_to_db(db: Session, service: str, action: str, status: str, message: str):
    try: db.add(APILog(service=service, action=action, status=status, message=message)); db.commit()
    except Exception as e: logger.error(f"Failed to log to DB: {e}")
# ... (Keep all your data cleaning and service classes the same as the last working version) ...
# --- Services (Shopify & AI) --- and --- Background Processing Logic --- remain the same.
# For brevity, I'll paste the full, final API part.

app=FastAPI(title="AI SEO Content Agent",version="FINAL-LOGS")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])

@app.get("/")
def root(): return{"status":"ok"}

@app.get("/api/health")
def health(): return {"ok": True, "service": "backend", "time": datetime.utcnow().isoformat()}

@app.get("/api/system-logs")
async def get_system_logs(db: Session = Depends(get_db)):
    logs = db.query(APILog).order_by(APILog.timestamp.desc()).limit(100).all()
    return {"logs": [{"timestamp": log.timestamp.isoformat(), "service": log.service, "action": log.action, "status": log.status, "message": log.message} for log in logs]}

# ... (Paste the rest of your working endpoints: /scan, /process-queue, /dashboard, /pause, etc.)
# It's crucial that these are the same as the last version that worked.
