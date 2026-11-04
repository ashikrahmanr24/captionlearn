from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.auth import require_admin
from app.database import (
    get_admin_stats, list_all_users, list_items, list_matches, delete_item
)
from app.cloud_client import cloud_service

router = APIRouter(prefix="/api/admin", tags=["Administrator Operations"])

class CloudConfigRequest(BaseModel):
    supabase_url: str
    supabase_key: str
    supabase_bucket: Optional[str] = "item-photos"

@router.get("/stats")
def admin_stats(user: dict = Depends(require_admin)):
    stats = get_admin_stats()
    cloud_info = cloud_service.test_connection()
    return {
        "success": True,
        "stats": stats,
        "cloud": cloud_info
    }

@router.get("/users")
def get_users(user: dict = Depends(require_admin)):
    users = list_all_users()
    return {"success": True, "count": len(users), "users": users}

@router.get("/cloud-status")
def test_cloud(user: dict = Depends(require_admin)):
    status = cloud_service.test_connection()
    return {"success": True, "cloud": status}

@router.post("/cloud-config")
def update_cloud_config(req: CloudConfigRequest, user: dict = Depends(require_admin)):
    success = cloud_service.update_credentials(
        url=req.supabase_url,
        key=req.supabase_key,
        bucket=req.supabase_bucket or "item-photos"
    )
    status = cloud_service.test_connection()
    return {
        "success": success,
        "message": "Supabase credentials updated successfully.",
        "connection_test": status
    }

@router.post("/cloud-sync")
def sync_to_supabase(user: dict = Depends(require_admin)):
    """Pushes all local items and matches to Supabase Cloud Database."""
    if not cloud_service.is_configured():
        raise HTTPException(
            status_code=400,
            detail="Supabase credentials not configured. Please enter your Supabase URL & Key first."
        )
        
    items = list_items()
    synced_items = 0
    for item in items:
        if cloud_service.sync_item_to_cloud(item):
            synced_items += 1
            
    matches = list_matches(min_score=50.0)
    synced_matches = 0
    for match in matches:
        if cloud_service.sync_match_to_cloud(match):
            synced_matches += 1
            
    return {
        "success": True,
        "synced_items": synced_items,
        "synced_matches": synced_matches,
        "message": f"Cloud Sync Completed: {synced_items} items and {synced_matches} matches synced to Supabase!"
    }

@router.delete("/items/{item_id}")
def remove_fake_report(item_id: str, user: dict = Depends(require_admin)):
    deleted = delete_item(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Item not found.")
    return {"success": True, "message": "Spam/Fake item report removed by administrator."}
