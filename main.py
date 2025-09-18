import os
import sys

# Add backend to Python path
sys.path.insert(0, 'backend')

# Import the app from backend
from backend.main import app

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
