from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from app.auth import require_auth, get_current_user
from app.database import (
    create_claim, list_claims, resolve_claim, get_match_by_id
)

router = APIRouter(prefix="/api/claims", tags=["Claims"])

class CreateClaimRequest(BaseModel):
    match_id: str
    proof_details: str
    contact_info: Optional[str] = ""

class ResolveClaimRequest(BaseModel):
    approve: bool

@router.post("/create")
def submit_claim(req: CreateClaimRequest, user: dict = Depends(require_auth)):
    match = get_match_by_id(req.match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found.")
        
    claim = create_claim(
        match_id=req.match_id,
        lost_item_id=match["lost_item_id"],
        found_item_id=match["found_item_id"],
        claimant_id=user["id"],
        claimant_name=user["name"],
        finder_id=match["found_user_id"],
        finder_name=match["found_user_name"],
        proof_details=req.proof_details,
        contact_info=req.contact_info or user.get("phone") or user.get("email")
    )
    return {"success": True, "claim": claim, "message": "Claim verification submitted! The finder and administrator have been notified."}

@router.get("")
def get_user_claims(user: dict = Depends(require_auth)):
    # Admin sees all, student sees their claims
    target_uid = None if user.get("role") == "admin" else user["id"]
    claims = list_claims(user_id=target_uid)
    return {"success": True, "count": len(claims), "claims": claims}

@router.post("/{claim_id}/resolve")
def resolve_user_claim(claim_id: str, req: ResolveClaimRequest, user: dict = Depends(require_auth)):
    resolve_claim(claim_id, approve=req.approve)
    action = "approved" if req.approve else "rejected"
    return {"success": True, "message": f"Claim has been {action}."}
