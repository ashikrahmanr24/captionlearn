import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.seed_data import seed_database_if_empty
from app.match_engine import rerun_all_matches
from app.routes.auth_routes import router as auth_router
from app.routes.item_routes import router as item_router
from app.routes.match_routes import router as match_router
from app.routes.claim_routes import router as claim_router
from app.routes.admin_routes import router as admin_router
from app.routes.notification_routes import router as notification_router
from app.cloud_client import cloud_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database and seed demo data
    print("[Startup] Initializing database...")
    init_db()
    print("[Startup] Checking sample seed data...")
    seed_database_if_empty()
    rerun_all_matches()
    print("[Startup] Testing cloud status...")
    status = cloud_service.test_connection()
    print(f"[Startup] Cloud connection status: {status['status']} ({status['message']})")
    yield
    print("[Shutdown] Cleaning up resources...")

app = FastAPI(
    title="Cloud-Based Lost & Found Matcher Using Image and Text Similarity",
    version=settings.PROJECT_VERSION,
    description="Intelligent campus lost-and-found cloud platform with weighted multi-factor similarity matching (TF-IDF, location, date, brand/color, and perceptual image hashing).",
    lifespan=lifespan
)

# Enable CORS for cloud deployment and frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static and Uploads directories
STATIC_DIR = settings.BASE_DIR / "static"
UPLOADS_DIR = settings.UPLOAD_DIR
TEMPLATES_DIR = settings.BASE_DIR / "templates"

STATIC_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

# Include Routers
app.include_router(auth_router)
app.include_router(item_router)
app.include_router(match_router)
app.include_router(claim_router)
app.include_router(admin_router)
app.include_router(notification_router)

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = TEMPLATES_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse("<h1>Cloud Lost & Found Matcher is running!</h1>")

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
        "cloud_storage": "supabase" if cloud_service.is_configured() else "local_fallback"
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print(f"🚀 Starting Cloud Lost & Found Matcher on http://127.0.0.1:{port}")
    uvicorn.run("run:app", host="0.0.0.0", port=port, reload=True)
