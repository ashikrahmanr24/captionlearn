import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import smtplib
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from dotenv import load_dotenv
from pathlib import Path
from typing import Any

from fastapi import Form, HTTPException, Request
from fastapi.responses import JSONResponse

LANGUAGES = {
    "en": {"code": "en", "name": "English", "native_name": "English", "rtl": False, "font": "Noto Sans"},
    "ta": {"code": "ta", "name": "Tamil", "native_name": "தமிழ்", "rtl": False, "font": "Noto Sans Tamil"},
}
RATE: dict[str, list[float]] = {}


def install(app: Any, ns: dict) -> None:
    base = ns["BASE_DIR"]
    load_dotenv(base / ".env")
    work = base / "work"
    old_db, new_db = work / "captionseal-users.db", work / "captionlearn-users.db"
    old_projects, new_projects = work / "captionseal-projects", work / "captionlearn-projects"
    if not new_projects.exists() and old_projects.exists():
        shutil.copytree(old_projects, new_projects)
    new_projects.mkdir(parents=True, exist_ok=True)
    if not new_db.exists() and old_db.exists():
        shutil.copy2(old_db, new_db)
    ns["PROJECTS_DIR"] = new_projects
    ns["DATABASE_FILE"] = new_db
    ns["PROJECTS_DIR"].mkdir(parents=True, exist_ok=True)

    def db():
        c = sqlite3.connect(new_db)
        c.row_factory = sqlite3.Row
        return c

    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, salt TEXT NOT NULL, created_at TEXT NOT NULL, verified INTEGER NOT NULL DEFAULT 0, verified_by TEXT)""")
        c.execute("CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires_at TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS email_codes (email TEXT PRIMARY KEY, code_hash TEXT NOT NULL, expires_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, resend_after TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS translation_memory (source_lang TEXT, target_lang TEXT, source_text TEXT, translated_text TEXT, PRIMARY KEY(source_lang,target_lang,source_text))")
        columns = {row[1] for row in c.execute("PRAGMA table_info(users)")}
        if "verified" not in columns: c.execute("ALTER TABLE users ADD COLUMN verified INTEGER NOT NULL DEFAULT 1")
        if "verified_by" not in columns: c.execute("ALTER TABLE users ADD COLUMN verified_by TEXT DEFAULT 'Legacy local account'")

    def current_user(request: Request):
        token = request.cookies.get("captionlearn_session")
        if not token: return None
        with db() as c:
            row = c.execute("SELECT u.id,u.name,u.email,u.verified,u.verified_by FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?", (hashlib.sha256(token.encode()).hexdigest(), datetime.now(timezone.utc).isoformat())).fetchone()
        return dict(row) if row else None

    ns["current_user"] = current_user

    def rate(request: Request, action: str):
        key = f"{request.client.host if request.client else 'local'}:{action}"
        now = time.time(); entries = [x for x in RATE.get(key, []) if now-x < 60]
        if len(entries) >= 10: raise HTTPException(429, "Too many attempts. Please wait a minute.")
        entries.append(now); RATE[key] = entries

    def hash_password(password: str, salt: bytes) -> str:
        return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310000).hex()

    def issue_code(email: str) -> None:
        code = f"{secrets.randbelow(1_000_000):06d}"; now = datetime.now(timezone.utc)
        with db() as c: c.execute("INSERT OR REPLACE INTO email_codes VALUES (?, ?, ?, 0, ?)", (email, hashlib.sha256(code.encode()).hexdigest(), (now+timedelta(minutes=10)).isoformat(), (now+timedelta(seconds=30)).isoformat()))
        user, password = os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD")
        if user and password:
            msg=EmailMessage(); msg["Subject"]="CaptionLearn verification code"; msg["From"]=user; msg["To"]=email; msg.set_content(f"Your CaptionLearn code is {code}. It expires in 10 minutes.")
            with smtplib.SMTP_SSL(os.getenv("SMTP_HOST","smtp.gmail.com"), int(os.getenv("SMTP_PORT","465"))) as s: s.login(user,password); s.send_message(msg)
        else: print(f"[CaptionLearn development verification] {email}: {code}")
    # Remove earlier simple auth and English-only auto-caption routes.
    remove = {"/api/auth/register", "/api/auth/login", "/api/auth/logout", "/api/auth/me", "/api/projects/{project_id}/auto-captions"}
    app.router.routes[:] = [r for r in app.router.routes if getattr(r,"path",None) not in remove]

    @app.get("/api/languages")
    async def languages(): return {"languages": [LANGUAGES["en"]], "default_subtitle_language":"en", "quality":{"balanced":"small"}}

    @app.get("/api/auth/me")
    async def me(request: Request):
        u=current_user(request); return {"authenticated":bool(u),"user":u}

    @app.get("/api/auth/check-email")
    async def check_email(email: str):
        email=email.strip().lower(); domain=email.rsplit("@",1)[-1] if "@" in email else ""
        provider="google" if domain in {"gmail.com","googlemail.com"} else "microsoft" if domain in {"outlook.com","hotmail.com","live.com","msn.com"} else "other"
        exists=False
        with db() as c: exists=bool(c.execute("SELECT 1 FROM users WHERE email=?",(email,)).fetchone())
        domain_ok=None
        try:
            import dns.resolver
            domain_ok=bool(dns.resolver.resolve(domain,"MX"))
        except Exception: pass
        return {"exists":exists,"provider":provider,"domain_ok":domain_ok,"method":"oauth" if provider in {"google","microsoft"} else "email_code"}

    @app.post("/api/auth/register")
    async def register(request: Request, name: str=Form(...), email: str=Form(...), password: str=Form(...)):
        rate(request,"register"); email=email.strip().lower(); name=name.strip()
        if len(name)<2 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+",email): raise HTTPException(422,"Enter a valid name and email.")
        if len(password)<8: raise HTTPException(422,"Use at least 8 characters for your password.")
        with db() as c:
            old=c.execute("SELECT verified FROM users WHERE email=?",(email,)).fetchone()
            if old and old["verified"]: raise HTTPException(409,"This email is already registered. Sign in instead.")
            salt=os.urandom(16); c.execute("INSERT OR REPLACE INTO users (id,name,email,password_hash,salt,created_at,verified,verified_by) VALUES ((SELECT id FROM users WHERE email=?),?,?,?,?,?,?,?)",(email,name,email,hash_password(password,salt),salt.hex(),datetime.now(timezone.utc).isoformat(),0,None))
        issue_code(email); return {"needs_verification":True,"message":"Verification code sent. It expires in 10 minutes."}

    @app.post("/api/auth/resend-code")
    async def resend(request: Request, email: str=Form(...)):
        rate(request,"resend"); email=email.strip().lower()
        with db() as c: row=c.execute("SELECT resend_after FROM email_codes WHERE email=?",(email,)).fetchone()
        if row and row["resend_after"]>datetime.now(timezone.utc).isoformat(): raise HTTPException(429,"Wait 30 seconds before requesting another code.")
        issue_code(email); return {"message":"A new code was sent."}

    @app.post("/api/auth/send-login-otp")
    async def send_login_otp(request: Request, email: str = Form(...)):
        rate(request, "send-otp")
        email = email.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise HTTPException(422, "Please enter a valid email address.")
        with db() as c:
            user = c.execute("SELECT id, name, email FROM users WHERE email=?", (email,)).fetchone()
            if not user:
                name = email.split("@")[0].replace(".", " ").title()
                salt = os.urandom(16)
                dummy_pwd = secrets.token_urlsafe(16)
                c.execute(
                    "INSERT INTO users (name, email, password_hash, salt, created_at, verified, verified_by) VALUES (?,?,?,?,?,?,?)",
                    (name, email, hash_password(dummy_pwd, salt), salt.hex(), datetime.now(timezone.utc).isoformat(), 0, "Email OTP")
                )
        issue_code(email)
        return {"needs_verification": True, "message": f"6-digit login OTP code sent to {email}. It expires in 10 minutes."}

    @app.post("/api/auth/verify-email")
    async def verify(request: Request, email: str=Form(...), code: str=Form(...)):
        rate(request,"verify"); email=email.strip().lower()
        with db() as c:
            row=c.execute("SELECT * FROM email_codes WHERE email=?",(email,)).fetchone()
            if not row or row["expires_at"]<datetime.now(timezone.utc).isoformat(): raise HTTPException(400,"This verification code has expired.")
            if row["attempts"]>=5: raise HTTPException(429,"Too many incorrect codes. Request a new code.")
            if not hmac.compare_digest(row["code_hash"],hashlib.sha256(code.encode()).hexdigest()): c.execute("UPDATE email_codes SET attempts=attempts+1 WHERE email=?",(email,)); raise HTTPException(422,"That code is not correct.")
            c.execute("UPDATE users SET verified=1,verified_by='Email code' WHERE email=?",(email,)); c.execute("DELETE FROM email_codes WHERE email=?",(email,))
            user = c.execute("SELECT id, name, email, verified_by FROM users WHERE email=?", (email,)).fetchone()
        
        if not user:
            raise HTTPException(404, "User record not found.")

        # Log the user in directly upon successful OTP verification!
        token = secrets.token_urlsafe(32)
        expiry = datetime.now(timezone.utc) + timedelta(hours=8)
        with db() as c:
            c.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user["id"], expiry.isoformat()))
        
        response = JSONResponse({
            "message": "Email verified! You are now logged in.",
            "user": {"id": user["id"], "name": user["name"], "email": user["email"], "verified_by": user["verified_by"]}
        })
        response.set_cookie("captionlearn_session", token, httponly=True, samesite="lax", max_age=28800)
        return response

    @app.post("/api/auth/login")
    async def login(request: Request, email: str=Form(...), password: str=Form(...)):
        rate(request,"login"); email=email.strip().lower()
        with db() as c: user=c.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
        if not user or not hmac.compare_digest(user["password_hash"],hash_password(password,bytes.fromhex(user["salt"]))): raise HTTPException(401,"Invalid email or password.")
        if not user["verified"]: raise HTTPException(403,"Please verify your email first")
        token=secrets.token_urlsafe(32); expiry=datetime.now(timezone.utc)+timedelta(hours=8)
        with db() as c: c.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?)",(hashlib.sha256(token.encode()).hexdigest(),user["id"],expiry.isoformat()))
        response=JSONResponse({"user":{"id":user["id"],"name":user["name"],"email":user["email"],"verified_by":user["verified_by"]}}); response.set_cookie("captionlearn_session",token,httponly=True,samesite="lax",max_age=28800); return response

    @app.post("/api/auth/logout")
    async def logout(request: Request):
        token=request.cookies.get("captionlearn_session")
        if token:
            with db() as c: c.execute("DELETE FROM sessions WHERE token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),))
        response=JSONResponse({"message":"Signed out."}); response.delete_cookie("captionlearn_session"); return response

    @app.get("/api/auth/oauth/{provider}/login")
    async def oauth_login(provider: str): raise HTTPException(503,f"{provider.title()} sign-in is not set up yet. Add its client ID and secret to environment variables.")

    @app.get("/api/projects")
    async def projects(request: Request):
        user=current_user(request); items=[]
        for folder in new_projects.iterdir():
            try:
                data=json.loads((folder/"project.json").read_text(encoding="utf-8"))
                if data.get("owner_email")==user["email"]: items.append({"id":folder.name,"title":data.get("title","Untitled lesson"),"date":data.get("created_at",""),"language":data.get("language","en"),"status":data.get("status","ready")})
            except Exception: continue
        return {"projects":sorted(items,key=lambda x:x["date"],reverse=True)}

    @app.post("/api/projects/{project_id}/auto-captions")
    async def captions(request: Request, project_id: str, language: str=Form("en"), quality: str=Form("fast"), explanation_language: str=Form("same"), detect_only: bool=Form(False), denoise: bool=Form(False), use_initial_prompt: bool=Form(False)):
        if language != "en": raise HTTPException(422,"CaptionLearn currently supports English videos only.")
        if quality not in {"fast","balanced","best"}: raise HTTPException(422,"Choose Fast, Balanced, or Best.")
        directory=ns["project_dir"](project_id)
        return ns["transcribe_locally"](directory, language, quality=quality, explanation_language=explanation_language, detect_only=detect_only, denoise=denoise, use_initial_prompt=use_initial_prompt)





