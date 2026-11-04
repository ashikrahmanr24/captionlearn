import json
from typing import List, Dict, Any
from app.config import settings
from app.database import (
    list_items, save_or_update_match, create_notification,
    get_item_by_id, list_matches
)
from app.matcher import match_items
from app.cloud_client import cloud_service

def scan_matches_for_item(item_id: str) -> List[Dict[str, Any]]:
    """
    Compares a single item (lost or found) against the complementary pool of items.
    Saves candidate matches and triggers notifications.
    """
    target = get_item_by_id(item_id)
    if not target or target.get("status") in ("resolved", "closed"):
        return []
        
    is_lost = target["type"] == "lost"
    opposite_type = "found" if is_lost else "lost"
    candidates = list_items(item_type=opposite_type)
    
    generated_matches = []
    
    for cand in candidates:
        if cand.get("status") in ("resolved", "closed"):
            continue
            
        lost = target if is_lost else cand
        found = cand if is_lost else target
        
        result = match_items(lost, found)
        score = result["overall_score"]
        
        if score >= settings.MATCH_MIN_THRESHOLD:
            # Save or update match record
            match_id = save_or_update_match(
                lost_item_id=lost["id"],
                found_item_id=found["id"],
                overall_score=score,
                text_score=result["text_score"],
                location_score=result["location_score"],
                date_score=result["date_score"],
                brand_color_score=result["brand_color_score"],
                image_score=result["image_score"],
                explanation=result["breakdown"]
            )
            
            # Sync to cloud if configured
            cloud_service.sync_match_to_cloud({
                "id": match_id,
                "lost_item_id": lost["id"],
                "found_item_id": found["id"],
                "overall_score": score,
                "text_score": result["text_score"],
                "location_score": result["location_score"],
                "date_score": result["date_score"],
                "brand_color_score": result["brand_color_score"],
                "image_score": result["image_score"],
                "breakdown": result["breakdown"]
            })
            
            # Send notification if score meets notify threshold
            if score >= settings.MATCH_NOTIFY_THRESHOLD:
                # Notify Lost item owner
                create_notification(
                    user_id=lost["user_id"],
                    item_id=lost["id"],
                    match_id=match_id,
                    title="Potential Match Found! 🔍",
                    message=f"Your lost '{lost['title']}' has a {score}% match with an item found near {found['location']}.",
                    score=score
                )
                
                # Notify Found item reporter (if different user)
                if found["user_id"] != lost["user_id"]:
                    create_notification(
                        user_id=found["user_id"],
                        item_id=found["id"],
                        match_id=match_id,
                        title="Match Found For Item You Reported 🎯",
                        message=f"A student reported losing '{lost['title']}' which matches your found item report with {score}% similarity.",
                        score=score
                    )
                    
            generated_matches.append({
                "match_id": match_id,
                "lost_title": lost["title"],
                "found_title": found["title"],
                "score": score,
                "breakdown": result["breakdown"]
            })
            
    return generated_matches

def rerun_all_matches() -> int:
    """Reruns the matching engine across all active lost & found items."""
    lost_items = list_items(item_type="lost")
    found_items = list_items(item_type="found")
    
    total_matches = 0
    for lost in lost_items:
        if lost.get("status") in ("resolved", "closed"):
            continue
        for found in found_items:
            if found.get("status") in ("resolved", "closed"):
                continue
                
            res = match_items(lost, found)
            score = res["overall_score"]
            if score >= settings.MATCH_MIN_THRESHOLD:
                save_or_update_match(
                    lost_item_id=lost["id"],
                    found_item_id=found["id"],
                    overall_score=score,
                    text_score=res["text_score"],
                    location_score=res["location_score"],
                    date_score=res["date_score"],
                    brand_color_score=res["brand_color_score"],
                    image_score=res["image_score"],
                    explanation=res["breakdown"]
                )
                total_matches += 1
    return total_matches
