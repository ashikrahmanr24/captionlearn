import os
import time
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from app.config import settings

try:
    from supabase import create_client, Client
    SUPABASE_LIB_AVAILABLE = True
except ImportError:
    SUPABASE_LIB_AVAILABLE = False
    Client = Any

class SupabaseCloudService:
    def __init__(self):
        self.url = settings.SUPABASE_URL.strip()
        self.key = settings.SUPABASE_KEY.strip()
        self.bucket = settings.SUPABASE_BUCKET.strip() or "item-photos"
        self.client: Optional[Client] = None
        self._init_client()

    def _init_client(self):
        if SUPABASE_LIB_AVAILABLE and self.url and self.key:
            try:
                self.client = create_client(self.url, self.key)
            except Exception as e:
                print(f"[SupabaseCloudService] Warning: Failed to init client: {e}")
                self.client = None
        else:
            self.client = None

    def update_credentials(self, url: str, key: str, bucket: str = "item-photos") -> bool:
        """Updates Supabase credentials at runtime."""
        self.url = url.strip()
        self.key = key.strip()
        self.bucket = bucket.strip() or "item-photos"
        settings.SUPABASE_URL = self.url
        settings.SUPABASE_KEY = self.key
        settings.SUPABASE_BUCKET = self.bucket
        self._init_client()
        return self.is_configured()

    def is_configured(self) -> bool:
        return bool(self.client is not None and self.url and self.key)

    def test_connection(self) -> Dict[str, Any]:
        """Tests connection to Supabase cloud database & storage."""
        if not self.is_configured():
            return {
                "connected": False,
                "status": "not_configured",
                "message": "Supabase credentials not configured in .env or settings.",
                "database": "offline",
                "storage": "offline",
                "latency_ms": None
            }
            
        start = time.time()
        try:
            # Test database query
            res = self.client.table("items").select("id").limit(1).execute()
            latency = round((time.time() - start) * 1000, 1)
            
            # Test storage bucket
            storage_status = "active"
            try:
                buckets = self.client.storage.list_buckets()
                bucket_names = [b.name for b in buckets] if hasattr(buckets, '__iter__') else []
                if self.bucket not in bucket_names:
                    storage_status = f"bucket '{self.bucket}' not created yet"
            except Exception as se:
                storage_status = f"storage check: {str(se)[:50]}"

            return {
                "connected": True,
                "status": "online",
                "message": "Connected successfully to Supabase Cloud Database & Storage!",
                "database": "online",
                "storage": storage_status,
                "latency_ms": latency,
                "project_url": self.url
            }
        except Exception as e:
            latency = round((time.time() - start) * 1000, 1)
            return {
                "connected": False,
                "status": "error",
                "message": f"Connection failed: {str(e)}",
                "database": "error",
                "storage": "unknown",
                "latency_ms": latency
            }

    def upload_image(self, file_bytes: bytes, file_name: str, content_type: str = "image/jpeg") -> Optional[str]:
        """
        Uploads image file to Supabase Cloud Storage bucket.
        Returns public URL if successful, otherwise None.
        """
        if not self.is_configured():
            return None
            
        try:
            # Ensure bucket exists or upload directly
            file_path = f"items/{int(time.time())}_{file_name}"
            res = self.client.storage.from_(self.bucket).upload(
                path=file_path,
                file=file_bytes,
                file_options={"content-type": content_type, "upsert": "true"}
            )
            # Retrieve public URL
            public_url = self.client.storage.from_(self.bucket).get_public_url(file_path)
            return public_url
        except Exception as e:
            print(f"[Supabase Storage] Upload error: {e}")
            return None

    def sync_item_to_cloud(self, item_dict: Dict[str, Any]) -> bool:
        """Pushes an item record to Supabase table."""
        if not self.is_configured():
            return False
        try:
            # Format payload
            data = {
                "id": str(item_dict["id"]),
                "user_id": str(item_dict.get("user_id", "")),
                "user_name": item_dict.get("user_name", ""),
                "user_email": item_dict.get("user_email", ""),
                "type": item_dict["type"],
                "category": item_dict.get("category", "other"),
                "title": item_dict["title"],
                "brand": item_dict.get("brand", ""),
                "color": item_dict.get("color", ""),
                "location": item_dict.get("location", ""),
                "item_date": item_dict.get("item_date", ""),
                "description": item_dict.get("description", ""),
                "image_url": item_dict.get("image_url", ""),
                "image_hash": item_dict.get("image_hash", ""),
                "image_features": json.dumps(item_dict.get("image_features", {})) if isinstance(item_dict.get("image_features"), dict) else str(item_dict.get("image_features") or "{}"),
                "status": item_dict.get("status", "open"),
                "created_at": item_dict.get("created_at", "")
            }
            self.client.table("items").upsert(data).execute()
            return True
        except Exception as e:
            print(f"[Supabase Database] Item sync error: {e}")
            return False

    def sync_match_to_cloud(self, match_dict: Dict[str, Any]) -> bool:
        """Pushes a match record to Supabase matches table."""
        if not self.is_configured():
            return False
        try:
            data = {
                "id": str(match_dict["id"]),
                "lost_item_id": str(match_dict["lost_item_id"]),
                "found_item_id": str(match_dict["found_item_id"]),
                "overall_score": float(match_dict["overall_score"]),
                "text_score": float(match_dict.get("text_score", 0)),
                "location_score": float(match_dict.get("location_score", 0)),
                "date_score": float(match_dict.get("date_score", 0)),
                "brand_color_score": float(match_dict.get("brand_color_score", 0)),
                "image_score": float(match_dict["image_score"]) if match_dict.get("image_score") is not None else None,
                "status": match_dict.get("status", "pending"),
                "explanation": json.dumps(match_dict.get("breakdown", {})) if isinstance(match_dict.get("breakdown"), dict) else str(match_dict.get("explanation") or "{}"),
                "created_at": match_dict.get("created_at", "")
            }
            self.client.table("matches").upsert(data).execute()
            return True
        except Exception as e:
            print(f"[Supabase Database] Match sync error: {e}")
            return False

cloud_service = SupabaseCloudService()
