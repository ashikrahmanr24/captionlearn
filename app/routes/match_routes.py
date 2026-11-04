from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.auth import get_current_user, require_auth, require_admin
from app.database import (
    list_matches, get_match_by_id, update_match_status
)
from app.matcher import match_items
from app.match_engine import rerun_all_matches

router = APIRouter(prefix="/api/matches", tags=["Matching Engine"])

class StatusUpdateRequest(BaseModel):
    status: str # 'pending', 'approved', 'rejected', 'claimed', 'resolved'

class LiveComparisonRequest(BaseModel):
    lost_title: str
    lost_description: str
    lost_location: str
    lost_date: str
    lost_brand: Optional[str] = ""
    lost_color: Optional[str] = ""
    found_title: str
    found_description: str
    found_location: str
    found_date: str
    found_brand: Optional[str] = ""
    found_color: Optional[str] = ""

@router.get("")
def get_matches(
    min_score: Optional[float] = 50.0,
    status: Optional[str] = None,
    my_matches: Optional[bool] = False,
    user: Optional[dict] = Depends(get_current_user)
):
    target_uid = None
    if my_matches:
        if not user:
            raise HTTPException(status_code=401, detail="Must be logged in to view my matches.")
        target_uid = user["id"]
        
    matches = list_matches(user_id=target_uid, min_score=min_score or 50.0, status=status)
    return {"success": True, "count": len(matches), "matches": matches}

@router.get("/{match_id}")
def get_match(match_id: str):
    m = get_match_by_id(match_id)
    if not m:
        raise HTTPException(status_code=404, detail="Match not found.")
    return {"success": True, "match": m}

@router.post("/rerun")
def rerun_engine(user: dict = Depends(require_auth)):
    count = rerun_all_matches()
    return {"success": True, "matches_calculated": count, "message": f"Matching engine recalculated successfully ({count} matches updated)."}

@router.post("/{match_id}/status")
def update_status(match_id: str, req: StatusUpdateRequest, user: dict = Depends(require_auth)):
    m = get_match_by_id(match_id)
    if not m:
        raise HTTPException(status_code=404, detail="Match not found.")
        
    # Check permissions: item owners or admin
    is_owner = (user["id"] in (m["lost_user_id"], m["found_user_id"]))
    if not is_owner and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to update this match status.")
        
    update_match_status(match_id, req.status)
    return {"success": True, "message": f"Match status updated to '{req.status}'"}

@router.post("/test-simulator")
def test_matching_simulator(req: LiveComparisonRequest):
    """
    Live simulator for demonstration and viva:
    Tests the algorithm with arbitrary lost & found inputs and shows step-by-step scoring.
    """
    lost_dummy = {
        "title": req.lost_title,
        "description": req.lost_description,
        "location": req.lost_location,
        "item_date": req.lost_date,
        "brand": req.lost_brand or "",
        "color": req.lost_color or "",
        "category": "demo",
        "image_features": None
    }
    found_dummy = {
        "title": req.found_title,
        "description": req.found_description,
        "location": req.found_location,
        "item_date": req.found_date,
        "brand": req.found_brand or "",
        "color": req.found_color or "",
        "category": "demo",
        "image_features": None
    }
    
    result = match_items(lost_dummy, found_dummy)
    return {
        "success": True,
        "calculation": result,
        "weights": {
            "Item Description": "35%",
            "Location Proximity": "25%",
            "Date Proximity": "20%",
            "Brand & Color": "20%"
        }
    }
