import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
    PROJECT_NAME: str = "Cloud-Based Lost & Found Matcher"
    PROJECT_VERSION: str = "1.0.0"
    BASE_DIR: Path = BASE_DIR
    SECRET_KEY: str = os.getenv("SECRET_KEY", "cloud-lost-found-secret-token-key-2026")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # Cloud Supabase Settings
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")  # anon or service_role key
    SUPABASE_BUCKET: str = os.getenv("SUPABASE_BUCKET", "item-photos")
    
    # Local fallback storage
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    DATA_DIR: Path = BASE_DIR / "data"
    SQLITE_DB_PATH: Path = BASE_DIR / "data" / "lost_and_found.db"
    
    # Matching thresholds
    MATCH_MIN_THRESHOLD: float = 50.0  # Show in match explorer
    MATCH_NOTIFY_THRESHOLD: float = 65.0  # Trigger notification
    HIGH_CONFIDENCE_THRESHOLD: float = 80.0  # High confidence badge

settings = Settings()
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
