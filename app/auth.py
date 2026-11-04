import hashlib
import hmac
import secrets
import json
import base64
import time
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import settings
from app.database import get_user_by_id, get_user_by_email, create_user

security = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    """Secure salted hash of password."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return f"{salt}${dk.hex()}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        salt, expected_hex = hashed_password.split("$", 1)
        dk = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt.encode("utf-8"), 100000)
        return hmac.compare_digest(dk.hex(), expected_hex)
    except Exception:
        return False

def create_access_token(user_id: str, role: str, email: str, name: str) -> str:
    """Creates a signed lightweight token with expiration."""
    payload = {
        "uid": user_id,
        "role": role,
        "email": email,
        "name": name,
        "exp": int(time.time()) + (settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    }
    raw = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    encoded_payload = base64.urlsafe_b64encode(raw).decode('utf-8').rstrip('=')
    sig = hmac.new(settings.SECRET_KEY.encode('utf-8'), encoded_payload.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"{encoded_payload}.{sig}"

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Verifies token signature and checks expiry."""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, signature = parts
        expected_sig = hmac.new(settings.SECRET_KEY.encode('utf-8'), payload_b64.encode('utf-8'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None
            
        # Add padding back if necessary
        padded = payload_b64 + "=" * ((4 - len(payload_b64) % 4) % 4)
        raw = base64.urlsafe_b64decode(padded.encode('utf-8')).decode('utf-8')
        payload = json.loads(raw)
        
        if payload.get("exp", 0) < int(time.time()):
            return None # Expired
            
        return payload
    except Exception:
        return None

def get_current_user(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Optional[Dict[str, Any]]:
    """Extracts authenticated user from Authorization header or session cookie."""
    token = None
    if credentials:
        token = credentials.credentials
    elif "access_token" in request.cookies:
        token = request.cookies.get("access_token")
    elif "authorization" in request.headers:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
            
    if not token:
        return None
        
    payload = decode_access_token(token)
    if not payload:
        return None
        
    user = get_user_by_id(payload.get("uid"))
    return user

def require_auth(user: Optional[Dict[str, Any]] = Depends(get_current_user)) -> Dict[str, Any]:
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required. Please log in.")
    return user

def require_admin(user: Dict[str, Any] = Depends(require_auth)) -> Dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Administrator privileges required.")
    return user
