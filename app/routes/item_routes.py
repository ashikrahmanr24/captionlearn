import os
import shutil
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from app.config import settings
from app.auth import get_current_user, require_auth
from app.database import (
    create_item, get_item_by_id, list_items, delete_item
)
from app.image_utils import extract_image_features
from app.cloud_client import cloud_service
from app.match_engine import scan_matches_for_item

router = APIRouter(prefix="/api/items", tags=["Items"])

async def handle_photo_upload(photo: Optional[UploadFile]) -> tuple[str, str, dict]:
    """Helper to process uploaded item photo, extract features, and upload to cloud/local."""
    if not photo or not photo.filename:
        return "", "", {}
        
    ext = Path(photo.filename).suffix.lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        ext = ".jpg"
        
    filename = f"{os.urandom(8).hex()}{ext}"
    local_path = settings.UPLOAD_DIR / filename
    
    content = await photo.read()
    with open(local_path, "wb") as f:
        f.write(content)
        
    # Extract perceptual dHash and color histogram
    features = extract_image_features(local_path)
    dhash = features.get("dhash", "")
    
    # Try uploading to Supabase Cloud Storage
    cloud_url = None
    if cloud_service.is_configured():
        cloud_url = cloud_service.upload_image(
            file_bytes=content,
            file_name=filename,
            content_type=photo.content_type or "image/jpeg"
        )
        
    # If cloud upload succeeded, use cloud URL; else use local serving URL
    image_url = cloud_url if cloud_url else f"/uploads/{filename}"
    return image_url, dhash, features

@router.post("/report-lost")
async def report_lost(
    title: str = Form(...),
    category: str = Form(...),
    location: str = Form(...),
    item_date: str = Form(...),
    description: str = Form(...),
    brand: Optional[str] = Form(""),
    color: Optional[str] = Form(""),
    photo: Optional[UploadFile] = File(None),
    user: dict = Depends(require_auth)
):
    image_url, image_hash, features = await handle_photo_upload(photo)
    
    item = create_item(
        user_id=user["id"],
        user_name=user["name"],
        user_email=user["email"],
        item_type="lost",
        category=category,
        title=title,
        brand=brand or "",
        color=color or "",
        location=location,
        item_date=item_date,
        description=description,
        image_url=image_url,
        image_hash=image_hash,
        image_features=features
    )
    
    # Cloud sync
    cloud_service.sync_item_to_cloud(item)
    
    # Trigger cloud matching engine
    matches = scan_matches_for_item(item["id"])
    
    return {
        "success": True,
        "item": item,
        "matched_count": len(matches),
        "matches": matches,
        "message": f"Lost item reported successfully! Found {len(matches)} potential match(es)."
    }

@router.post("/report-found")
async def report_found(
    title: str = Form(...),
    category: str = Form(...),
    location: str = Form(...),
    item_date: str = Form(...),
    description: str = Form(...),
    brand: Optional[str] = Form(""),
    color: Optional[str] = Form(""),
    safekeeping_location: Optional[str] = Form(""),
    photo: Optional[UploadFile] = File(None),
    user: dict = Depends(require_auth)
):
    image_url, image_hash, features = await handle_photo_upload(photo)
    
    item = create_item(
        user_id=user["id"],
        user_name=user["name"],
        user_email=user["email"],
        item_type="found",
        category=category,
        title=title,
        brand=brand or "",
        color=color or "",
        location=location,
        item_date=item_date,
        description=description,
        image_url=image_url,
        image_hash=image_hash,
        image_features=features,
        safekeeping_location=safekeeping_location or ""
    )
    
    # Cloud sync
    cloud_service.sync_item_to_cloud(item)
    
    # Trigger matching engine
    matches = scan_matches_for_item(item["id"])
    
    return {
        "success": True,
        "item": item,
        "matched_count": len(matches),
        "matches": matches,
        "message": f"Found item reported successfully! Matched with {len(matches)} lost report(s)."
    }

@router.get("")
def get_items(
    type: Optional[str] = None,
    category: Optional[str] = None,
    query: Optional[str] = None,
    user_id: Optional[str] = None,
    my_items: Optional[bool] = False,
    user: Optional[dict] = Depends(get_current_user)
):
    target_uid = None
    if my_items:
        if not user:
            raise HTTPException(status_code=401, detail="Must be logged in to view my items.")
        target_uid = user["id"]
    elif user_id:
        target_uid = user_id
        
    items = list_items(item_type=type, user_id=target_uid, category=category, query=query)
    return {"success": True, "count": len(items), "items": items}

@router.get("/{item_id}")
def get_item(item_id: str):
    item = get_item_by_id(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found.")
    return {"success": True, "item": item}

@router.delete("/{item_id}")
def remove_item(item_id: str, user: dict = Depends(require_auth)):
    item = get_item_by_id(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found.")
        
    # Only owner or admin can delete
    if item["user_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to delete this report.")
        
    delete_item(item_id)
    return {"success": True, "message": "Item report removed successfully."}
