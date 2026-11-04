from fastapi import APIRouter, Depends
from app.auth import require_auth
from app.database import (
    list_user_notifications, mark_notifications_read
)

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])

@router.get("")
def get_notifications(user: dict = Depends(require_auth)):
    notifications = list_user_notifications(user["id"])
    unread_count = sum(1 for n in notifications if not n.get("read_status"))
    return {
        "success": True,
        "unread_count": unread_count,
        "notifications": notifications
    }

@router.post("/mark-read")
def mark_read(user: dict = Depends(require_auth)):
    mark_notifications_read(user["id"])
    return {"success": True, "message": "All notifications marked as read."}
