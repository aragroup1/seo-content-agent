# backend/integrations.py - Integration management endpoints
from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, JSON
from datetime import datetime
from typing import Optional, List, Dict
import os
import secrets

from main import Base, SessionLocal, get_db, engine

# --- Database Model for Integrations ---
class Integration(Base):
    __tablename__ = "integrations"

    id = Column(Integer, primary_key=True, index=True)
    website_id = Column(Integer, ForeignKey("websites.id"), nullable=False)
    integration_type = Column(String, nullable=False)  # google_search_console, google_analytics, shopify, wordpress
    status = Column(String, default="pending")  # active, error, expired, pending
    connected_at = Column(DateTime, nullable=True)
    last_synced = Column(DateTime, nullable=True)
    access_token = Column(String, nullable=True)
    refresh_token = Column(String, nullable=True)
    token_expiry = Column(DateTime, nullable=True)
    account_name = Column(String, nullable=True)
    account_id = Column(String, nullable=True)
    scopes = Column(JSON, default=lambda: [])
    config = Column(JSON, default=lambda: {})  # Extra config per integration type
    created_at = Column(DateTime, default=datetime.utcnow)

# Create the table
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"Integration table creation: {e}")

# --- Router ---
router = APIRouter(prefix="/api/integrations", tags=["integrations"])


INTEGRATION_DEFINITIONS = {
    "google_search_console": {
        "name": "Google Search Console",
        "description": "Track keyword rankings, impressions, and indexing status",
        "required": True,
        "relevantFor": ["custom", "shopify", "wordpress"],
        "dataProvided": "Keyword rankings, click data, indexing errors",
        "scopes": ["https://www.googleapis.com/auth/webmasters.readonly"]
    },
    "google_analytics": {
        "name": "Google Analytics 4",
        "description": "Monitor traffic, user behavior, and conversions",
        "required": True,
        "relevantFor": ["custom", "shopify", "wordpress"],
        "dataProvided": "Traffic sources, user engagement, conversion tracking",
        "scopes": ["https://www.googleapis.com/auth/analytics.readonly"]
    },
    "shopify": {
        "name": "Shopify",
        "description": "Sync products, manage meta tags, and optimize listings",
        "required": True,
        "relevantFor": ["shopify"],
        "dataProvided": "Product data, collection structure, meta fields",
        "scopes": ["read_products", "read_content", "read_themes"]
    },
    "wordpress": {
        "name": "WordPress",
        "description": "Sync posts, manage SEO plugin settings, and optimize content",
        "required": True,
        "relevantFor": ["wordpress"],
        "dataProvided": "Posts, pages, plugin settings, sitemap data",
        "scopes": []
    }
}


@router.get("/{website_id}/status")
async def get_integration_status(website_id: int, db: Session = Depends(get_db)):
    """Get the status of all integrations for a website, including which are connected."""
    # Get connected integrations from DB
    connected = db.query(Integration).filter(
        Integration.website_id == website_id
    ).all()

    connected_map = {i.integration_type: i for i in connected}

    integrations = []
    for int_id, definition in INTEGRATION_DEFINITIONS.items():
        db_record = connected_map.get(int_id)
        integrations.append({
            "id": int_id,
            "name": definition["name"],
            "description": definition["description"],
            "connected": db_record is not None and db_record.status == "active",
            "status": db_record.status if db_record else "not_connected",
            "required": definition["required"],
            "relevantFor": definition["relevantFor"],
            "dataProvided": definition["dataProvided"],
            "connected_at": db_record.connected_at.isoformat() if db_record and db_record.connected_at else None,
            "last_synced": db_record.last_synced.isoformat() if db_record and db_record.last_synced else None,
            "account_name": db_record.account_name if db_record else None,
        })

    return {"integrations": integrations}


@router.get("/{website_id}/connected")
async def get_connected_integrations(website_id: int, db: Session = Depends(get_db)):
    """Get only the connected integrations for settings view."""
    connected = db.query(Integration).filter(
        Integration.website_id == website_id,
        Integration.status.in_(["active", "error", "expired"])
    ).all()

    integrations = []
    for record in connected:
        definition = INTEGRATION_DEFINITIONS.get(record.integration_type, {})
        integrations.append({
            "id": record.integration_type,
            "name": definition.get("name", record.integration_type),
            "connected": record.status == "active",
            "status": record.status,
            "connected_at": record.connected_at.isoformat() if record.connected_at else None,
            "last_synced": record.last_synced.isoformat() if record.last_synced else None,
            "account_name": record.account_name,
            "scopes": record.scopes or [],
        })

    return {"integrations": integrations}


@router.post("/{website_id}/connect")
async def connect_integration(
    website_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Initiate connection to an integration platform."""
    data = await request.json()
    integration_id = data.get("integration_id")

    if integration_id not in INTEGRATION_DEFINITIONS:
        raise HTTPException(status_code=400, detail=f"Unknown integration: {integration_id}")

    definition = INTEGRATION_DEFINITIONS[integration_id]

    # Handle Google OAuth integrations
    if integration_id in ["google_search_console", "google_analytics"]:
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/integrations/oauth/google/callback")

        if not client_id:
            # For development: simulate a successful connection
            existing = db.query(Integration).filter(
                Integration.website_id == website_id,
                Integration.integration_type == integration_id
            ).first()

            if existing:
                existing.status = "active"
                existing.connected_at = datetime.utcnow()
                existing.last_synced = datetime.utcnow()
                existing.account_name = "Demo Account"
            else:
                new_integration = Integration(
                    website_id=website_id,
                    integration_type=integration_id,
                    status="active",
                    connected_at=datetime.utcnow(),
                    last_synced=datetime.utcnow(),
                    account_name="Demo Account",
                    scopes=definition.get("scopes", [])
                )
                db.add(new_integration)

            db.commit()
            return {"connected": True, "message": f"{definition['name']} connected (demo mode)"}

        # Real OAuth flow
        state = secrets.token_urlsafe(32)
        scopes = " ".join(definition.get("scopes", []))
        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth"
            f"?client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&response_type=code"
            f"&scope={scopes}"
            f"&state={state}_{website_id}_{integration_id}"
            f"&access_type=offline"
            f"&prompt=consent"
        )
        return {"authorization_url": auth_url}

    # Handle Shopify integration
    elif integration_id == "shopify":
        shopify_store_url = data.get("shopify_store_url")
        shopify_access_token = data.get("shopify_access_token")

        existing = db.query(Integration).filter(
            Integration.website_id == website_id,
            Integration.integration_type == "shopify"
        ).first()

        if existing:
            existing.status = "active"
            existing.connected_at = datetime.utcnow()
            existing.last_synced = datetime.utcnow()
            existing.access_token = shopify_access_token
            existing.account_name = shopify_store_url
            existing.config = {"store_url": shopify_store_url}
        else:
            new_integration = Integration(
                website_id=website_id,
                integration_type="shopify",
                status="active",
                connected_at=datetime.utcnow(),
                last_synced=datetime.utcnow(),
                access_token=shopify_access_token,
                account_name=shopify_store_url,
                config={"store_url": shopify_store_url},
                scopes=definition.get("scopes", [])
            )
            db.add(new_integration)

        db.commit()
        return {"connected": True, "message": "Shopify connected"}

    # Handle WordPress integration
    elif integration_id == "wordpress":
        wp_url = data.get("wordpress_url")
        wp_api_key = data.get("api_key")

        existing = db.query(Integration).filter(
            Integration.website_id == website_id,
            Integration.integration_type == "wordpress"
        ).first()

        if existing:
            existing.status = "active"
            existing.connected_at = datetime.utcnow()
            existing.account_name = wp_url
            existing.config = {"wp_url": wp_url}
        else:
            new_integration = Integration(
                website_id=website_id,
                integration_type="wordpress",
                status="active",
                connected_at=datetime.utcnow(),
                account_name=wp_url,
                access_token=wp_api_key,
                config={"wp_url": wp_url},
                scopes=[]
            )
            db.add(new_integration)

        db.commit()
        return {"connected": True, "message": "WordPress connected"}

    return {"connected": False, "message": "Integration type not handled"}


@router.post("/{website_id}/disconnect")
async def disconnect_integration(
    website_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Disconnect an integration. Preserves historical data."""
    data = await request.json()
    integration_id = data.get("integration_id")

    record = db.query(Integration).filter(
        Integration.website_id == website_id,
        Integration.integration_type == integration_id
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail="Integration not found")

    # Remove the record (historical audit data from this integration is preserved)
    db.delete(record)
    db.commit()

    return {"disconnected": True, "message": f"{integration_id} disconnected"}


@router.post("/{website_id}/sync")
async def sync_integration(
    website_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Trigger a manual sync for an integration."""
    data = await request.json()
    integration_id = data.get("integration_id")

    record = db.query(Integration).filter(
        Integration.website_id == website_id,
        Integration.integration_type == integration_id
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail="Integration not found")

    if record.status != "active":
        raise HTTPException(status_code=400, detail="Integration is not active. Please reconnect.")

    # TODO: Trigger actual sync logic based on integration type
    # For now, just update last_synced
    record.last_synced = datetime.utcnow()
    db.commit()

    return {"synced": True, "message": f"{integration_id} sync initiated"}


# --- Google OAuth Callback ---
@router.get("/oauth/google/callback")
async def google_oauth_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db)
):
    """Handle Google OAuth callback after user authorizes."""
    import httpx

    # Parse state to get website_id and integration_type
    try:
        parts = state.split("_")
        # state format: {random}_{website_id}_{integration_type}
        website_id = int(parts[-2])
        integration_type = parts[-1]
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/integrations/oauth/google/callback")

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code"
            }
        )

    if token_response.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to exchange authorization code")

    tokens = token_response.json()
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in", 3600)

    # Get user info for account_name
    account_name = "Google Account"
    try:
        async with httpx.AsyncClient() as client:
            user_response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            if user_response.status_code == 200:
                user_info = user_response.json()
                account_name = user_info.get("email", "Google Account")
    except Exception:
        pass

    # Save to database
    definition = INTEGRATION_DEFINITIONS.get(integration_type, {})
    existing = db.query(Integration).filter(
        Integration.website_id == website_id,
        Integration.integration_type == integration_type
    ).first()

    if existing:
        existing.status = "active"
        existing.access_token = access_token
        existing.refresh_token = refresh_token
        existing.token_expiry = datetime.utcnow()
        existing.connected_at = datetime.utcnow()
        existing.last_synced = datetime.utcnow()
        existing.account_name = account_name
        existing.scopes = definition.get("scopes", [])
    else:
        new_integration = Integration(
            website_id=website_id,
            integration_type=integration_type,
            status="active",
            access_token=access_token,
            refresh_token=refresh_token,
            token_expiry=datetime.utcnow(),
            connected_at=datetime.utcnow(),
            last_synced=datetime.utcnow(),
            account_name=account_name,
            scopes=definition.get("scopes", [])
        )
        db.add(new_integration)

    db.commit()

    # Return HTML that closes the popup and notifies the parent window
    return HTMLResponse(content="""
    <html>
    <body>
        <script>
            window.opener && window.opener.postMessage('integration_connected', '*');
            window.close();
        </script>
        <p>Connected successfully! This window will close automatically.</p>
    </body>
    </html>
    """)
