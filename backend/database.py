from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, JSON, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

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
    priority = Column(Integer, default=5)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    
class SEOContent(Base):
    __tablename__ = "seo_content"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(String, index=True)
    seo_title = Column(String)
    meta_description = Column(String)
    ai_description = Column(Text)
    keywords = Column(JSON)
    focus_keyword = Column(String)
    alt_text = Column(Text)
    seo_score = Column(Integer)
    generated_at = Column(DateTime, default=datetime.utcnow)
    published = Column(Boolean, default=False)
    
class QueueItem(Base):
    __tablename__ = "queue"
    
    id = Column(Integer, primary_key=True, index=True)
    shopify_id = Column(String, index=True)
    priority = Column(Integer, default=5)
    status = Column(String, default="pending")
    attempts = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
