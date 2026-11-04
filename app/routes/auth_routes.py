from fastapi import APIRouter, HTTPException, Depends, Response
from pydantic import BaseModel
from typing import Optional
from app.database import create_user, get_user_by_email, get_user_by_id
from app.auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, require_auth
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    role: Optional[str] = "student"
    student_id: Optional[str] = ""
    phone: Optional[str] = ""

class LoginRequest(BaseModel):
    email: str
    password: str

class DemoLoginRequest(BaseModel):
    role: str # "student" or "admin"

@router.post("/register")
def register(req: RegisterRequest, response: Response):
    existing = get_user_by_email(req.email)
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
        
    role = "admin" if req.role and req.role.lower() == "admin" else "student"
    user = create_user(
        name=req.name,
        email=req.email,
        password_hash=hash_password(req.password),
        role=role,
        student_id=req.student_id or "",
        phone=req.phone or ""
    )
    
    token = create_access_token(user["id"], user["role"], user["email"], user["name"])
    response.set_cookie(key="access_token", value=token, httponly=True, samesite="lax", max_age=86400*7)
    
    return {
        "success": True,
        "token": token,
        "user": user,
        "message": "Account created successfully!"
    }

@router.post("/login")
def login(req: LoginRequest, response: Response):
    user = get_user_by_email(req.email)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
        
    token = create_access_token(user["id"], user["role"], user["email"], user["name"])
    response.set_cookie(key="access_token", value=token, httponly=True, samesite="lax", max_age=86400*7)
    
    user_data = {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "student_id": user.get("student_id", ""),
        "phone": user.get("phone", "")
    }
    return {
        "success": True,
        "token": token,
        "user": user_data,
        "message": "Logged in successfully!"
    }

@router.post("/demo-login")
def demo_login(req: DemoLoginRequest, response: Response):
    """Provides instant 1-click evaluation login for student or admin."""
    email = "admin@campus.edu" if req.role == "admin" else "rahul.sharma@campus.edu"
    user = get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=404, detail="Demo account not found. Please restart server to seed data.")
        
    token = create_access_token(user["id"], user["role"], user["email"], user["name"])
    response.set_cookie(key="access_token", value=token, httponly=True, samesite="lax", max_age=86400*7)
    
    user_data = {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "student_id": user.get("student_id", ""),
        "phone": user.get("phone", "")
    }
    return {
        "success": True,
        "token": token,
        "user": user_data,
        "message": f"Logged in as demo {req.role} ({user['name']})"
    }

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"success": True, "message": "Logged out successfully."}

@router.get("/me")
def get_me(user: Optional[dict] = Depends(get_current_user)):
    if not user:
        return {"authenticated": False, "user": None}
    return {"authenticated": True, "user": user}
