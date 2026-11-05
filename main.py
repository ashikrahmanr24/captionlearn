import json
import mimetypes
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import shutil
import subprocess
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
PROJECTS_DIR = BASE_DIR / "work" / "captionlearn-projects"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_FILE = BASE_DIR / "work" / "captionlearn-users.db"

app = FastAPI(title="CaptionLearn", version="2.0.0")

@app.on_event("startup")
def preload_models_and_corpora():
    """Warms up WordNet corpora, POS taggers, and Whisper models into RAM at server boot so user requests execute in < 5s."""
    try:
        import nltk
        from nltk.corpus import wordnet as wn
        wn.synsets("test")
        wn.synsets("break")
        nltk.pos_tag(["warmup", "test"])
    except Exception as e:
        print("[CaptionLearn Warmup Notice]", e)
    try:
        from faster_whisper import WhisperModel
        is_cloud = bool(os.getenv("RENDER") or os.getenv("PORT") or os.getenv("APP_ENV") == "production")
        cpu_threads = 2 if is_cloud else min(os.cpu_count() or 4, 4)
        m_name = "tiny.en" if is_cloud else "base.en"
        cache_key = f"fw:{m_name}:cpu:{cpu_threads}"
        if cache_key not in MODEL_CACHE:
            MODEL_CACHE[cache_key] = WhisperModel(m_name, device="cpu", compute_type="int8", cpu_threads=cpu_threads)
    except Exception as e:
        print("[CaptionLearn Whisper Warmup Notice]", e)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
WHISPER_MODEL = None
WORDNET_READY = False
WORD_MEANING_CACHE: dict[str, dict] = {}
SESSIONS: dict[str, dict] = {}
PUBLIC_API_PREFIXES = ("/api/auth/", "/api/health", "/api/languages", "/api/admin/")
STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "to", "of", "in", "on", "for",
    "with", "that", "this", "it", "i", "you", "we", "they", "he", "she", "my", "your", "our", "their",
    "at", "as", "be", "do", "does", "did", "have", "has", "had", "will", "would", "can", "could",
    "should", "so", "if", "by", "from", "up", "about", "into", "over", "after", "not", "no", "yes",
    "just", "now", "then", "there", "here", "what", "who", "whom", "how", "when", "where", "why",
    "all", "any", "both", "each", "few", "more", "most", "other", "some", "such", "than", "too",
    "very", "me", "him", "her", "us", "them", "its", "mine", "yours", "his", "hers", "ours", "theirs",
    "don't", "dont", "gonna", "wanna", "gotta", "yeah", "ok", "okay", "hey", "uh", "um", "oh"
}
BASE_BAD_WORDS = {"shit", "fuck", "fucking", "bitch", "bastard", "asshole", "damn", "crap", "dick", "piss"}

LOCAL_PHRASE_GLOSSARY = {
    "break the ice": {
        "term": "Idiom — Break the ice",
        "meaning": "1. Start a friendly conversation in a new or awkward situation.\n2. Similar idea: help people feel comfortable.\n3. Example: A joke can break the ice before a meeting.\n4. It does not mean breaking real ice.",
        "explanation": "",
    },
    "piece of cake": {
        "term": "Idiom — Piece of cake",
        "meaning": "1. Something very easy to do.\n2. Similar idea: simple or effortless.\n3. Example: The final question was a piece of cake.\n4. It does not refer to food.",
        "explanation": "",
    },
    "hit the books": {
        "term": "Idiom — Hit the books",
        "meaning": "1. Begin studying seriously.\n2. Similar idea: focus on schoolwork.\n3. Example: I need to hit the books before the exam.\n4. It does not mean hitting physical books.",
        "explanation": "",
    },
    "holy shit": {
        "term": "Meaning — Holy shit",
        "meaning": "1. A strong, informal expression of surprise or shock.\n2. Softer alternatives: “Wow!”, “Oh my goodness!”, or “That is unbelievable!”\n3. It may be rude or offensive, so use it only in casual adult contexts.\n4. It is not a literal religious statement.",
        "explanation": "",
    },
    "holy crap": {
        "term": "Meaning — Holy crap",
        "meaning": "1. An informal expression of surprise.\n2. It is a softer alternative to “holy shit.”\n3. It is usually used in casual conversation, not formal writing.\n4. It does not have a literal meaning.",
        "explanation": "",
    },
}

def load_safety_words() -> set[str]:
    words = set(BASE_BAD_WORDS)
    safety_file = BASE_DIR / "safety" / "en.json"
    if safety_file.exists():
        try:
            data = json.loads(safety_file.read_text(encoding="utf-8"))
            words.update(w.lower() for w in data.get("words", []))
        except Exception:
            pass
    return words

def load_phrase_glossary() -> dict[str, dict]:
    glossary = dict(LOCAL_PHRASE_GLOSSARY)
    glossary_file = BASE_DIR / "glossary" / "en.json"
    if glossary_file.exists():
        try:
            data = json.loads(glossary_file.read_text(encoding="utf-8"))
            for phrase, val in data.items():
                if isinstance(val, dict):
                    glossary[phrase.casefold()] = {
                        "term": val.get("term", f"Idiom — {phrase.title()}"),
                        "meaning": val.get("meaning", ""),
                        "explanation": val.get("explanation", ""),
                    }
        except Exception:
            pass
    return glossary

BAD_WORDS = load_safety_words()


def database() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    return connection


def initialise_database() -> None:
    with database() as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL, salt TEXT NOT NULL, created_at TEXT NOT NULL)""")


def password_hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000).hex()


def current_user(request: Request) -> dict | None:
    token = request.cookies.get("captionlearn_session")
    return SESSIONS.get(token) if token else None


initialise_database()


@app.middleware("http")
async def require_login_for_studio(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and not path.startswith(PUBLIC_API_PREFIXES) and not current_user(request):
        return JSONResponse({"detail": "Please sign in to access the CaptionLearn studio."}, status_code=401)
    if path.startswith("/api/projects/"):
        project_id = path.split("/")[3] if len(path.split("/")) > 3 else ""
        metadata_file = PROJECTS_DIR / project_id / "project.json"
        try:
            owner = json.loads(metadata_file.read_text(encoding="utf-8")).get("owner_email")
        except (OSError, json.JSONDecodeError):
            owner = None
        if owner != current_user(request)["email"]:
            return JSONResponse({"detail": "You do not have access to this project."}, status_code=403)
    return await call_next(request)


@app.get("/")
async def home():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/health")
async def health_check():
    return {"status": "ready", "service": "CaptionLearn"}


@app.get("/api/auth/me")
async def auth_me(request: Request):
    user = current_user(request)
    return {"authenticated": bool(user), "user": user}


@app.post("/api/auth/register")
async def register_user(name: str = Form(...), email: str = Form(...), password: str = Form(...)):
    clean_name, clean_email = name.strip(), email.strip().lower()
    if len(clean_name) < 2 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", clean_email):
        raise HTTPException(422, "Enter a valid name and email address.")
    if len(password) < 8:
        raise HTTPException(422, "Use a password with at least 8 characters.")
    salt = os.urandom(16)
    try:
        with database() as connection:
            connection.execute("INSERT INTO users (name, email, password_hash, salt, created_at) VALUES (?, ?, ?, ?, ?)", (clean_name, clean_email, password_hash(password, salt), salt.hex(), datetime.now(timezone.utc).isoformat()))
    except sqlite3.IntegrityError as error:
        raise HTTPException(409, "An account with this email already exists. Please sign in.") from error
    return {"message": "Account created. Please sign in."}


@app.post("/api/auth/login")
async def login_user(email: str = Form(...), password: str = Form(...)):
    with database() as connection:
        user = connection.execute("SELECT id, name, email, password_hash, salt FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    if not user or not hmac.compare_digest(user["password_hash"], password_hash(password, bytes.fromhex(user["salt"]))):
        raise HTTPException(401, "Invalid email or password.")
    token = secrets.token_urlsafe(32)
    payload = {"id": user["id"], "name": user["name"], "email": user["email"]}
    SESSIONS[token] = payload
    response = JSONResponse({"user": payload})
    response.set_cookie("captionlearn_session", token, httponly=True, samesite="lax", secure=False, max_age=60 * 60 * 8)
    return response


@app.post("/api/auth/logout")
async def logout_user(request: Request):
    token = request.cookies.get("captionlearn_session")
    if token:
        SESSIONS.pop(token, None)
    response = JSONResponse({"message": "Signed out."})
    response.delete_cookie("captionlearn_session")
    return response


def project_dir(project_id: str) -> Path:
    directory = PROJECTS_DIR / project_id
    if not directory.is_dir():
        raise HTTPException(404, "Project not found.")
    return directory


def find_source(directory: Path) -> Path:
    source = next(directory.glob("source.*"), None)
    if not source:
        raise HTTPException(404, "Source video is missing.")
    return source


def ffmpeg_path() -> str | None:
    known_windows_path = Path("C:/Users/Admin/AppData/Local/Microsoft/WinGet/Links/ffmpeg.exe")
    return str(known_windows_path) if known_windows_path.exists() else shutil.which("ffmpeg")


def timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds_part, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds_part:02},{milliseconds:03}"


def make_srt(captions: list[dict]) -> str:
    blocks = []
    for index, caption in enumerate(captions, start=1):
        text = str(caption.get("text", "")).strip()
        try:
            start = float(caption.get("start", 0))
            end = float(caption.get("end", 0))
        except (TypeError, ValueError):
            continue
        if text and end > start >= 0:
            blocks.append(f"{index}\n{timestamp(start)} --> {timestamp(end)}\n{text}\n")
    if not blocks:
        raise HTTPException(422, "Add at least one subtitle with valid start and end times.")
    return "\n".join(blocks)


def valid_captions(captions: list[dict]) -> list[dict]:
    cleaned = []
    for caption in captions:
        try:
            start, end = float(caption.get("start", 0)), float(caption.get("end", 0))
        except (TypeError, ValueError):
            continue
        text = str(caption.get("text", "")).strip()
        if text and end > start >= 0:
            kws = caption.get("keywords")
            if not kws:
                try:
                    kws = explanation_for_text(text).get("keywords", [])
                except Exception:
                    kws = []
            cleaned.append({
                "start": start, "end": end, "text": text,
                "term": str(caption.get("term", "")).strip() or "Meaning",
                "meaning": str(caption.get("meaning", "")).strip(),
                "explanation": str(caption.get("explanation", "")).strip(),
                "keywords": kws,
                "inappropriate": bool(caption.get("inappropriate", False)) or has_inappropriate_language(text),
            })
    if not cleaned:
        raise HTTPException(422, "Add at least one subtitle with valid start and end times.")
    return sorted(cleaned, key=lambda item: item["start"])


def parse_captions(captions_json: str) -> list[dict]:
    try:
        captions = json.loads(captions_json)
    except json.JSONDecodeError as error:
        raise HTTPException(422, "Subtitle data is invalid.") from error
    if not isinstance(captions, list):
        raise HTTPException(422, "Subtitle data must be a list.")
    return valid_captions(captions)


def write_captions(directory: Path, captions: list[dict]) -> None:
    (directory / "subtitles.srt").write_text(make_srt(captions), encoding="utf-8-sig")
    (directory / "captions.json").write_text(json.dumps(captions, ensure_ascii=False, indent=2), encoding="utf-8")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while data := file.read(1024 * 1024):
            digest.update(data)
    return digest.hexdigest()


def quality_check(captions: list[dict]) -> dict:
    warnings = []
    for index, caption in enumerate(captions, start=1):
        duration = caption["end"] - caption["start"]
        characters = len(caption["text"])
        rate = characters / duration
        if duration < 1:
            warnings.append({"line": index, "type": "Very short timing", "detail": "Show this subtitle for at least 1 second."})
        if rate > 17:
            warnings.append({"line": index, "type": "Fast reading speed", "detail": f"{rate:.1f} characters/second. Shorten the text or increase the duration."})
        if characters > 84:
            warnings.append({"line": index, "type": "Long subtitle", "detail": "Use shorter text or split it into two subtitle lines."})
        if index > 1 and caption["start"] < captions[index - 2]["end"]:
            warnings.append({"line": index, "type": "Timing overlap", "detail": "This subtitle begins before the previous subtitle ends."})
        flagged = sorted({word for word in re.findall(r"[a-z']+", caption["text"].casefold()) if word in BAD_WORDS})
        if flagged:
            warnings.append({"line": index, "type": "Inappropriate language", "detail": f"Flagged word(s): {', '.join(flagged)}. Review before sharing with a general audience."})
    return {"total_subtitles": len(captions), "warnings": warnings, "status": "pass" if not warnings else "review"}


def ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    seconds_part, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02}:{seconds_part:02}.{centiseconds:02}"


def ass_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


async def save_upload(upload: UploadFile, destination: Path) -> None:
    from starlette.concurrency import run_in_threadpool
    def _write():
        with destination.open("wb") as file:
            while True:
                chunk = upload.file.read(1024 * 512)
                if not chunk:
                    break
                file.write(chunk)
    await run_in_threadpool(_write)
    await upload.close()


ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".flv", ".wmv", ".ts", ".mpg", ".mpeg", ".3gp", ".ogv"}


@app.post("/api/projects")
async def create_project(request: Request, video: UploadFile = File(...), title: str = Form("Untitled video")):
    extension = Path(video.filename or "video.mp4").suffix.lower() or ".mp4"
    is_video_mime = bool(video.content_type and video.content_type.startswith("video/"))
    is_video_ext = extension in ALLOWED_VIDEO_EXTENSIONS
    if not is_video_mime and not is_video_ext:
        raise HTTPException(415, "Please upload a supported video file (.mp4, .mov, .mkv, .webm, etc.).")
    project_id = uuid4().hex[:10]
    directory = PROJECTS_DIR / project_id
    directory.mkdir(parents=True, exist_ok=True)
    await save_upload(video, directory / f"source{extension}")
    user = current_user(request)
    owner = user["email"] if user else "demo@captionlearn.com"
    (directory / "project.json").write_text(json.dumps({"title": title.strip() or "Untitled video", "owner_email": owner}), encoding="utf-8")
    return {"id": project_id, "video_url": f"/api/projects/{project_id}/video", "message": "Video uploaded. Add timed subtitles below, then export."}


@app.get("/api/projects")
async def list_projects(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(401, "Please sign in to view project history.")
    email = user["email"].strip().lower()
    projects = []
    if PROJECTS_DIR.is_dir():
        for item in PROJECTS_DIR.iterdir():
            if not item.is_dir():
                continue
            meta_file = item / "project.json"
            if not meta_file.exists():
                continue
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            if meta.get("owner_email", "").strip().lower() != email:
                continue

            source = next(item.glob("source.*"), None)
            has_source = source is not None
            auto_captions_file = item / "auto-captions.json"
            captions_count = 0
            has_subtitles = False
            if auto_captions_file.exists():
                try:
                    c_data = json.loads(auto_captions_file.read_text(encoding="utf-8"))
                    captions_count = len(c_data)
                    has_subtitles = True
                except Exception:
                    pass
            elif (item / "subtitles.srt").exists():
                has_subtitles = True

            has_learning_video = (item / "learning-mode-video.mp4").exists()
            mtime = item.stat().st_mtime
            created_at = datetime.fromtimestamp(mtime, timezone.utc).isoformat()

            projects.append({
                "id": item.name,
                "title": meta.get("title") or "Untitled video",
                "created_at": created_at,
                "has_source": has_source,
                "has_subtitles": has_subtitles,
                "caption_count": captions_count,
                "has_learning_video": has_learning_video,
                "video_url": f"/api/projects/{item.name}/video" if has_source else None,
            })
    projects.sort(key=lambda p: p["created_at"], reverse=True)
    return {"projects": projects}


@app.get("/api/projects/{project_id}/details")
async def project_details(project_id: str, request: Request):
    directory = project_dir(project_id)
    meta_file = directory / "project.json"
    title = "Untitled video"
    if meta_file.exists():
        try:
            title = json.loads(meta_file.read_text(encoding="utf-8")).get("title", title)
        except Exception:
            pass

    captions = []
    auto_file = directory / "auto-captions.json"
    if auto_file.exists():
        try:
            captions = json.loads(auto_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    return {
        "id": project_id,
        "title": title,
        "video_url": f"/api/projects/{project_id}/video",
        "captions": captions,
        "has_learning_video": (directory / "learning-mode-video.mp4").exists(),
    }


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str, request: Request):
    directory = project_dir(project_id)
    shutil.rmtree(directory, ignore_errors=True)
    return {"message": "Project deleted successfully."}


@app.get("/api/admin/stats")
async def get_admin_stats(request: Request):
    """Returns real-time metrics on logged-in users, registrations, and active projects."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with database() as connection:
        total_users = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        verified_users = connection.execute("SELECT COUNT(*) FROM users WHERE verified = 1").fetchone()[0]
        
        # Check active unexpired sessions in database
        active_sessions = connection.execute(
            "SELECT COUNT(DISTINCT user_id) FROM sessions WHERE expires_at > ?", (now_iso,)
        ).fetchone()[0]
        
        # Also include any memory sessions
        memory_logged_in_ids = {u["id"] for u in SESSIONS.values() if "id" in u}

        rows = connection.execute(
            """
            SELECT u.id, u.name, u.email, u.verified, u.verified_by, u.created_at,
                   CASE WHEN s.user_id IS NOT NULL THEN 1 ELSE 0 END AS is_db_logged_in
            FROM users u
            LEFT JOIN (SELECT DISTINCT user_id FROM sessions WHERE expires_at > ?) s ON u.id = s.user_id
            ORDER BY u.created_at DESC
            """,
            (now_iso,)
        ).fetchall()

        users_list = []
        for r in rows:
            is_active = bool(r["is_db_logged_in"]) or (r["id"] in memory_logged_in_ids)
            users_list.append({
                "id": r["id"],
                "name": r["name"],
                "email": r["email"],
                "verified": bool(r["verified"]),
                "verified_by": r["verified_by"] or "Email code",
                "created_at": r["created_at"],
                "is_logged_in": is_active,
                "status": "Online (Logged In)" if is_active else "Offline"
            })

    total_projects = len([p for p in PROJECTS_DIR.iterdir() if p.is_dir()]) if PROJECTS_DIR.is_dir() else 0

    # Total active online count
    online_count = sum(1 for u in users_list if u["is_logged_in"])

    return {
        "active_users_logged_in": online_count,
        "total_registered_users": total_users,
        "verified_users": verified_users,
        "total_projects": total_projects,
        "users": users_list
    }


@app.get("/api/projects/{project_id}/video")
async def source_video(project_id: str):
    source = find_source(project_dir(project_id))
    media_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    return FileResponse(source, media_type=media_type)


@app.post("/api/projects/{project_id}/auto-captions")
async def auto_captions(project_id: str, language: str = Form("auto")):
    if language not in {"en", "auto"}:
        raise HTTPException(422, "CaptionLearn currently supports English videos only.")
    directory = project_dir(project_id)
    res = transcribe_locally(directory, language)
    captions = res.get("captions", []) if isinstance(res, dict) else (res if isinstance(res, list) else [])
    (directory / "auto-captions.json").write_text(json.dumps(captions, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"captions": captions, "message": "Automatic captions are ready for review."}


@app.post("/api/projects/{project_id}/subtitles")
async def save_subtitles(project_id: str, captions_json: str = Form(...)):
    directory = project_dir(project_id)
    write_captions(directory, parse_captions(captions_json))
    return {"download_url": f"/api/projects/{project_id}/download-srt"}


@app.post("/api/projects/{project_id}/quality-check")
async def run_quality_check(project_id: str, captions_json: str = Form(...)):
    directory = project_dir(project_id)
    captions = parse_captions(captions_json)
    report = quality_check(captions)
    report["created_at"] = datetime.now(timezone.utc).isoformat()
    (directory / "quality-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


@app.post("/api/projects/{project_id}/seal")
async def seal_project(project_id: str, captions_json: str = Form(...), secret: str = Form(...)):
    if len(secret) < 6:
        raise HTTPException(422, "Use a verification secret of at least 6 characters.")
    directory = project_dir(project_id)
    captions = parse_captions(captions_json)
    write_captions(directory, captions)
    payload = {
        "project_id": project_id,
        "sealed_at": datetime.now(timezone.utc).isoformat(),
        "source_video_sha256": file_hash(find_source(directory)),
        "subtitles_sha256": file_hash(directory / "subtitles.srt"),
        "meaning_track_sha256": file_hash(directory / "captions.json"),
        "quality": quality_check(captions),
    }
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, 200_000)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest = {"payload": payload, "salt": salt.hex(), "iterations": 200_000, "signature": hmac.new(key, canonical, hashlib.sha256).hexdigest()}
    (directory / "integrity-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"message": "Project sealed locally.", "fingerprint": payload["source_video_sha256"], "download_url": f"/api/projects/{project_id}/download-manifest"}


@app.post("/api/projects/{project_id}/verify")
async def verify_project(project_id: str, secret: str = Form(...)):
    directory = project_dir(project_id)
    manifest_file = directory / "integrity-manifest.json"
    if not manifest_file.exists():
        raise HTTPException(404, "Seal this project before verifying it.")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    payload = manifest["payload"]
    current = {
        "source_video_sha256": file_hash(find_source(directory)),
        "subtitles_sha256": file_hash(directory / "subtitles.srt"),
        "meaning_track_sha256": file_hash(directory / "captions.json"),
    }
    key = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), bytes.fromhex(manifest["salt"]), manifest["iterations"])
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    verified_secret = hmac.compare_digest(manifest["signature"], hmac.new(key, canonical, hashlib.sha256).hexdigest())
    files_unchanged = all(payload[name] == value for name, value in current.items())
    return {"verified": verified_secret and files_unchanged, "secret_valid": verified_secret, "files_unchanged": files_unchanged, "message": "Files and seal are valid." if verified_secret and files_unchanged else "Verification failed: the secret is wrong or project files changed."}


@app.get("/api/projects/{project_id}/download-manifest")
async def download_manifest(project_id: str):
    output = project_dir(project_id) / "integrity-manifest.json"
    if not output.exists():
        raise HTTPException(404, "Seal the project before downloading its integrity manifest.")
    return FileResponse(output, media_type="application/json", filename=f"captionlearn-{project_id}-integrity.json")


@app.get("/api/projects/{project_id}/download-srt")
async def download_srt(project_id: str):
    output = project_dir(project_id) / "subtitles.srt"
    if not output.exists():
        raise HTTPException(404, "Save subtitles before downloading.")
    return FileResponse(output, media_type="application/x-subrip", filename=f"captionlearn-{project_id}.srt")


def run_ffmpeg(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
        raise HTTPException(500, error.stderr[-700:] or "FFmpeg could not process this video.") from error


def ffprobe_path() -> str | None:
    known_windows_path = Path("C:/Users/Admin/AppData/Local/Microsoft/WinGet/Links/ffprobe.exe")
    return str(known_windows_path) if known_windows_path.exists() else shutil.which("ffprobe")


def transcribe_locally(directory: Path, language: str | None) -> list[dict]:
    """Generate editable caption timings locally. Whisper is loaded only when requested."""
    global WHISPER_MODEL
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        raise HTTPException(503, "FFmpeg is required for automatic subtitles.")
    try:
        import whisper
    except ImportError as error:
        raise HTTPException(503, "Automatic subtitles need openai-whisper. Install the updated requirements in voicefit-ai.") from error
    audio = directory / "auto-caption-audio.wav"
    run_ffmpeg([ffmpeg, "-y", "-i", str(find_source(directory)), "-vn", "-ac", "1", "-ar", "16000", str(audio)])
    if WHISPER_MODEL is None:
        WHISPER_MODEL = whisper.load_model("base")
    options = {"fp16": False, "verbose": False}
    if language and language.lower() not in {"auto", "auto-detect"}:
        options["language"] = language
    # Word timings produce much closer subtitle/audio alignment than whole sentence segments.
    options["word_timestamps"] = True
    result = WHISPER_MODEL.transcribe(str(audio), **options)
    captions = []
    for segment in result.get("segments", []):
        words = segment.get("words") or []
        if not words:
            text = str(segment.get("text", "")).strip()
            if text:
                captions.append(make_auto_caption(float(segment["start"]), float(segment["end"]), text))
            continue
        group, group_start = [], None
        for word in words:
            word_text = str(word.get("word", "")).strip()
            word_start, word_end = word.get("start"), word.get("end")
            if not word_text or word_start is None or word_end is None:
                continue
            if group_start is None:
                group_start = float(word_start)
            proposed = " ".join(group + [word_text]).strip()
            duration = float(word_end) - group_start
            if group and (len(proposed) > 44 or duration > 3.8):
                captions.append(make_auto_caption(group_start, previous_end, " ".join(group)))
                group, group_start = [word_text], float(word_start)
            else:
                group.append(word_text)
            previous_end = float(word_end)
            if group and word_text.endswith((".", "?", "!", ",")) and len(group) >= 3:
                captions.append(make_auto_caption(group_start, previous_end, " ".join(group)))
                group, group_start = [], None
        if group and group_start is not None:
            captions.append(make_auto_caption(group_start, previous_end, " ".join(group)))
    if not captions:
        raise HTTPException(422, "No speech was detected. Use a video with clear spoken audio.")
    return captions


def make_auto_caption(start: float, end: float, text: str) -> dict:
    """A truthful automatic study card; users can replace it with a subject-specific synonym."""
    cleaned = text.strip()
    explanation = explanation_for_text(cleaned)
    return {
        "start": round(start, 1), "end": round(max(end, start + 0.7), 1), "text": cleaned,
        "term": explanation["term"], "meaning": explanation["meaning"], "explanation": explanation["explanation"],
        "inappropriate": has_inappropriate_language(cleaned),
    }


COMMON_NAMES = {
    "mike", "michael", "eric", "bakker", "holly", "john", "mary", "david", "sarah", "james",
    "robert", "william", "joseph", "charles", "thomas", "daniel", "matthew", "anthony", "mark",
    "steven", "paul", "andrew", "joshua", "kevin", "brian", "george", "edward", "ronald", "timothy",
    "jason", "jeffrey", "ryan", "jacob", "gary", "nicholas", "jonathan", "stephen", "larry",
    "justin", "scott", "brandon", "benjamin", "samuel", "gregory", "alexander", "frank", "patrick",
    "jack", "dennis", "jerry", "tyler", "aaron", "jose", "adam", "henry", "nathan", "douglas",
    "zachary", "peter", "kyle", "walter", "ethan", "jeremy", "harold", "keith", "christian", "roger",
    "noah", "gerald", "carl", "terry", "sean", "austin", "arthur", "lawrence", "jesse", "dylan",
    "bryan", "joe", "jordan", "billy", "albert", "bruce", "willie", "gabriel", "logan", "alan",
    "juan", "wayne", "roy", "ralph", "randy", "eugene", "vincent", "russell", "louis", "philip",
    "bobby", "johnny", "bradley", "troy", "emma", "olivia", "ava", "isabella", "sophia", "mia", "charlotte",
    "amelia", "harper", "evelyn", "abigail", "emily", "elizabeth", "mila", "ella", "avery", "sofia",
    "camila", "aria", "scarlett", "victoria", "madison", "luna", "grace", "chloe", "penelope", "layla"
}

INTRODUCTORY_WORDS = {
    "seriously", "actually", "honestly", "suddenly", "finally", "please", "well", "now",
    "hey", "look", "listen", "no", "yes", "oh", "wait", "maybe", "probably", "surely",
    "clearly", "obviously", "meanwhile", "anyway", "besides", "furthermore"
}

PHRASAL_VERBS_AND_IDIOMS = {
    "let go of": ("Phrasal Verb", "Release hold of; stop restraining, gripping, or holding someone or something.", ["release", "unhand", "drop"]),
    "let go": ("Phrasal Verb", "Release grip or stop holding; dismiss from custody or employment.", ["release", "relinquish"]),
    "look for": ("Phrasal Verb", "Search for, seek, or scan in order to discover or locate something.", ["search for", "seek", "hunt for"]),
    "looks for": ("Phrasal Verb", "Searches for, seeks, or scans in order to discover or locate something.", ["searches for", "seeks", "scans for"]),
    "looked for": ("Phrasal Verb", "Searched for or tried to locate something.", ["searched for", "sought"]),
    "looking for": ("Phrasal Verb", "Searching for, seeking, or scanning to discover something.", ["searching for", "seeking"]),
    "on hand": ("Idiom", "Available immediately in inventory, stock, or possession.", ["in stock", "available", "ready"]),
    "break the ice": ("Idiom", "Initiate friendly conversation to relieve tension or awkwardness in a group.", ["warm up", "start talking"]),
    "piece of cake": ("Idiom", "Something very simple, straightforward, or easy to accomplish.", ["easy", "effortless", "breeze"]),
    "bite the bullet": ("Idiom", "Face a difficult or unavoidable situation with courage and endurance.", ["face it", "endure"]),
    "under the weather": ("Idiom", "Feeling slightly ill, tired, or unwell.", ["sick", "unwell", "indisposed"]),
    "hit the nail on the head": ("Idiom", "Describe exactly what is causing a situation or problem.", ["be accurate", "spot on"]),
    "spill the beans": ("Idiom", "Reveal a secret prematurely or indiscreetly.", ["let secret out", "disclose"]),
    "call it a day": ("Idiom", "Decide or agree to stop working on something for the remainder of the day.", ["finish up", "conclude"]),
    "see eye to eye": ("Idiom", "Be in full agreement with someone on a subject.", ["agree", "concur"]),
    "search engine": ("Technical Term", "A software program (such as Google or Bing) that searches a database of web pages for specific queries.", ["web search", "crawler"]),
    "search engines": ("Technical Term", "Software systems that index and search the World Wide Web for information.", ["web search tools"]),
    "seo": ("Acronym", "Search Engine Optimization — the process of improving a website to increase its visibility in search results.", ["search optimization", "web positioning"]),
    "break an arm": ("Expression", "Cause a bone in the arm to fracture or snap from physical trauma or injury.", ["fracture arm"]),
    "broke my arm": ("Expression", "Fractured or snapped the arm bone through physical impact or force.", ["fractured arm", "injured limb"]),
    "broke an arm": ("Expression", "Fractured or snapped the arm bone through physical impact or force.", ["fractured arm", "injured limb"]),
    "break a leg": ("Idiom", "A colloquial theatrical wish of good luck before a performance.", ["good luck", "do well"]),
    "do it": ("Collocation", "Proceed with an action or task.", ["go through with it", "proceed"])
}


def wn_has_common_synset(word: str) -> bool:
    try:
        from nltk.corpus import wordnet as wn
        return bool(wn.synsets(word.casefold()))
    except Exception:
        return False


def contextual_word_meaning(word: str, full_sentence: str = "", pos_tags: dict | None = None) -> dict:
    """Disambiguates words, idioms, names, and technical terms in the context of the spoken sentence."""
    global WORDNET_READY
    clean_w = re.sub(r"[^\w']", "", word).strip()
    clean_w_lower = clean_w.casefold()
    sent = (full_sentence or clean_w).strip()
    sent_lower = sent.casefold()

    # 1. Multi-word phrasal verbs, idioms, technical terms check
    for phrase, (kind, defn, syns) in sorted(PHRASAL_VERBS_AND_IDIOMS.items(), key=lambda x: -len(x[0])):
        if phrase in sent_lower:
            phrase_parts = phrase.split()
            if clean_w_lower in phrase_parts or clean_w_lower == phrase:
                return {
                    "word": phrase.capitalize(),
                    "term": f"{kind} — {phrase.title()}",
                    "meaning": (
                        f"1. In this context: {defn}\n"
                        f"2. Grammatical type: {kind.lower()}.\n"
                        f"3. In the dialogue: \"{sent}\"\n"
                        f"4. Related expressions: {', '.join(syns)}."
                    ),
                    "label": kind
                }

    # 2. Proper Person Name check
    is_name = (
        clean_w_lower in COMMON_NAMES
        or (
            clean_w.istitle()
            and clean_w_lower not in INTRODUCTORY_WORDS
            and not clean_w_lower.endswith("ly")
            and (
                ("i'm " + clean_w_lower) in sent_lower
                or ("mr. " + clean_w_lower) in sent_lower
                or ("name is " + clean_w_lower) in sent_lower
                or ("," in sent and sent.lstrip().startswith(clean_w + ",") and not wn_has_common_synset(clean_w_lower))
            )
        )
    )
    if is_name:
        return {
            "word": clean_w.capitalize(),
            "term": f"Proper Name — {clean_w.capitalize()}",
            "meaning": (
                f"1. In this context: A person's given name used to address or identify an individual in the video.\n"
                f"2. Grammatical type: Proper noun (person's name).\n"
                f"3. In the dialogue: \"{sent}\"\n"
                f"4. Note: Spoken identifier in dialogue, not a dictionary object."
            ),
            "label": "Proper Name"
        }

    # 3. Handle domain specific acronyms
    if clean_w.isupper() and len(clean_w) <= 5 and clean_w_lower in PHRASAL_VERBS_AND_IDIOMS:
        kind, defn, syns = PHRASAL_VERBS_AND_IDIOMS[clean_w_lower]
        return {
            "word": clean_w,
            "term": f"{kind} — {clean_w}",
            "meaning": f"1. In this context: {defn}\n2. Grammatical type: {kind.lower()}.\n3. In the dialogue: \"{sent}\"\n4. Related expressions: {', '.join(syns)}.",
            "label": kind
        }

    # 4. WordNet contextual semantic disambiguation
    try:
        import nltk
        from nltk.corpus import wordnet as wn
        from nltk.stem import PorterStemmer

        global WORDNET_READY
        if not WORDNET_READY:
            try:
                wn.synsets("test")
            except LookupError:
                nltk.download("wordnet", quiet=True)
                nltk.download("omw-1.4", quiet=True)
                nltk.download("averaged_perceptron_tagger_eng", quiet=True)
                nltk.download("averaged_perceptron_tagger", quiet=True)
                nltk.download("punkt", quiet=True)
                nltk.download("punkt_tab", quiet=True)
            WORDNET_READY = True

        stemmer = PorterStemmer()

        # POS Tagging (use pre-computed sentence tags if provided for speed)
        if pos_tags is None:
            try:
                tokens = nltk.word_tokenize(sent)
                pos_tags = dict(nltk.pos_tag(tokens))
            except Exception:
                pos_tags = {}

        tag = pos_tags.get(clean_w, pos_tags.get(clean_w.capitalize(), ""))
        wn_pos = None
        if tag.startswith("V"):
            wn_pos = wn.VERB
        elif tag.startswith("N"):
            wn_pos = wn.NOUN
        elif tag.startswith("J"):
            wn_pos = wn.ADJ
        elif tag.startswith("R"):
            wn_pos = wn.ADV

        all_synsets = wn.synsets(clean_w_lower, pos=wn_pos) if wn_pos else []
        if not all_synsets:
            all_synsets = wn.synsets(clean_w_lower)

        if not all_synsets:
            if clean_w.isupper() and len(clean_w) <= 6:
                return {
                    "word": clean_w,
                    "term": f"Acronym — {clean_w}",
                    "meaning": (
                        f"1. In this context: Specialized term or abbreviation used in this video topic.\n"
                        f"2. Used in sentence: \"{sent}\"\n"
                        f"3. Category: Acronym / Domain terminology."
                    ),
                    "label": "Acronym"
                }
            return {
                "word": clean_w.capitalize(),
                "term": f"Meaning — {clean_w.capitalize()}",
                "meaning": (
                    f"1. In this context: Spoken in video dialogue expressing: \"{sent}\".\n"
                    f"2. Grammatical category: {tag or 'vocabulary word'}.\n"
                    f"3. Spoken dialogue vocabulary."
                ),
                "label": "Meaning"
            }

        sent_words = [re.sub(r"[^\w']", "", w).casefold() for w in sent.split() if w]
        sent_stems = {stemmer.stem(w) for w in sent_words if len(w) > 2 and w != clean_w_lower}

        best_score = -1.0
        best_synset = all_synsets[0]

        for syn in all_synsets:
            score = 0.0
            if wn_pos and syn.pos() == wn_pos:
                score += 2.5

            def_words = [re.sub(r"[^\w']", "", w).casefold() for w in (syn.definition() + " " + " ".join(syn.examples())).split() if w]
            def_stems = {stemmer.stem(w) for w in def_words if len(w) > 2}

            overlap = sent_stems.intersection(def_stems)
            score += len(overlap) * 3.0

            # Domain contextual boosters
            if any(b in sent_lower for b in ["arm", "leg", "bone", "hurt", "fracture", "body"]):
                if any(b in syn.definition().casefold() for b in ["fracture", "bone", "limb", "separate into pieces", "body"]):
                    score += 5.0

            if any(b in sent_lower for b in ["seo", "engine", "website", "site", "page", "rank", "online", "search"]):
                if any(b in syn.definition().casefold() for b in ["computer", "web", "document", "internet", "information", "order"]):
                    score += 4.0

            if score > best_score:
                best_score = score
                best_synset = syn

        pos_names = {"n": "noun", "v": "verb", "a": "adjective", "r": "adverb", "s": "adjective"}
        pos_desc = pos_names.get(best_synset.pos(), "word")
        synonyms = [item.replace("_", " ") for item in best_synset.lemma_names() if item.casefold() != clean_w_lower][:3]

        lines = [
            f"1. In this sentence: {best_synset.definition().capitalize()}.",
            f"2. Part of speech: {pos_desc}."
        ]
        if synonyms:
            lines.append(f"3. Synonyms: {', '.join(synonyms)}.")
        lines.append(f"4. Spoken context: \"{sent}\"")

        return {
            "word": clean_w.capitalize(),
            "term": f"Meaning — {clean_w.capitalize()}",
            "meaning": "\n".join(lines),
            "label": "Meaning"
        }

    except Exception:
        return {
            "word": clean_w.capitalize(),
            "term": f"Meaning — {clean_w.capitalize()}",
            "meaning": f"1. Word: {clean_w.capitalize()}.\n2. Context: Spoken in video dialogue: \"{sent}\".",
            "label": "Meaning"
        }


def word_meaning(word: str, full_sentence: str = "") -> dict | None:
    """Backward-compatible lookup for word meaning with optional sentence context."""
    return contextual_word_meaning(word, full_sentence)


def explanation_for_text(text: str) -> dict:
    """Extracts contextual meanings, phrasal verbs, idioms, and vocabulary keywords for a subtitle sentence."""
    glossary = load_phrase_glossary()
    text_lower = text.casefold()
    for phrase, item in glossary.items():
        if phrase in text_lower:
            item_copy = dict(item)
            item_copy["keywords"] = [{"word": phrase.title(), "term": item["term"], "meaning": item["meaning"]}]
            return item_copy

    stripped = text.strip().rstrip(".?!")
    sent_lower = stripped.casefold()

    keyword_items = []
    seen = set()

    # 1. First, check if any phrasal verbs or idioms are present in this sentence
    for phrase, (kind, defn, syns) in sorted(PHRASAL_VERBS_AND_IDIOMS.items(), key=lambda x: -len(x[0])):
        if phrase in sent_lower:
            p_display = phrase.title()
            if p_display.casefold() not in seen:
                seen.add(p_display.casefold())
                for pw in phrase.split():
                    seen.add(pw.casefold())
                keyword_items.append({
                    "word": p_display,
                    "term": f"{kind} — {p_display}",
                    "meaning": (
                        f"1. In this context: {defn}\n"
                        f"2. Grammatical type: {kind.lower()}.\n"
                        f"3. In the dialogue: \"{stripped}\"\n"
                        f"4. Related expressions: {', '.join(syns)}."
                    )
                })

    # 2. Extract key individual words from dialogue
    words = re.findall(r"[A-Za-z']+", stripped)
    key_words = [word for word in words if word.casefold() not in STOP_WORDS and len(word) > 1]
    if not key_words and words:
        key_words = [words[-1]]

    # Tokenize and POS-tag sentence once for all candidate words
    sentence_tags = {}
    try:
        import nltk
        s_tokens = nltk.word_tokenize(stripped)
        sentence_tags = dict(nltk.pos_tag(s_tokens))
    except Exception:
        pass

    for w in key_words:
        clean = re.sub(r"'s$", "", w, flags=re.IGNORECASE).strip("'")
        if not clean or clean.casefold() in seen:
            continue
        seen.add(clean.casefold())

        info = contextual_word_meaning(clean, stripped, pos_tags=sentence_tags)
        keyword_items.append({
            "word": info["word"],
            "term": info["term"],
            "meaning": info["meaning"]
        })
        if len(keyword_items) >= 6:
            break

    primary = keyword_items[0] if keyword_items else {
        "word": stripped,
        "term": "Meaning",
        "meaning": f"1. Word: {stripped}.\n2. Context: Video dialogue.\n3. Edit in timeline if needed.\n4. Everyday English.",
    }

    return {
        "term": primary["term"],
        "meaning": primary["meaning"],
        "explanation": "",
        "keywords": keyword_items,
    }


def has_inappropriate_language(text: str) -> bool:
    safety_words = load_safety_words()
    return any(word in safety_words for word in re.findall(r"[a-z']+", text.casefold()))




def video_dimensions(source: Path) -> tuple[int, int]:
    probe = ffprobe_path()
    if not probe:
        raise HTTPException(503, "FFprobe is not installed. It is included with FFmpeg.")
    result = subprocess.run([probe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", str(source)], check=True, capture_output=True, text=True)
    stream = json.loads(result.stdout)["streams"][0]
    return int(stream["width"]), int(stream["height"])


def wrap_ass_lines(text: str, max_chars: int = 34) -> str:
    """Wraps text so it fits comfortably within the learning sidebar without clipping."""
    out_lines = []
    for raw_line in text.split("\n"):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        while len(raw_line) > max_chars:
            idx = raw_line.rfind(" ", 0, max_chars)
            if idx <= 0:
                idx = max_chars
            out_lines.append(raw_line[:idx].strip())
            raw_line = raw_line[idx:].strip()
        if raw_line:
            out_lines.append(raw_line)
    return "\\N".join(out_lines)


def make_learning_ass(captions: list[dict], video_width: int, video_height: int, sidebar_width: int) -> str:
    output_width = video_width + sidebar_width
    h = video_height

    # Proportional font sizes and spacing scaled to video resolution
    caption_font = max(16, int(h * 0.040))
    title_font = max(11, int(h * 0.022))
    badge_font = max(9, int(h * 0.018))
    word_font = max(18, int(h * 0.045))
    body_font = max(11, int(h * 0.022))

    # Proportional sidebar coordinates
    pad_left = max(16, int(sidebar_width * 0.06))
    x = video_width + pad_left
    max_sidebar_chars = max(24, int(sidebar_width / (body_font * 0.65)))

    y_title = max(16, int(h * 0.05))
    y_badge = y_title + max(20, int(h * 0.04))
    y_word = y_badge + max(22, int(h * 0.048))
    y_body = y_word + max(30, int(h * 0.065))
    y_caption = h - max(28, int(h * 0.06))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {output_width}
PlayResY: {h}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Caption,Arial,{caption_font},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,2,1,2,20,20,32,1
Style: SidebarTitle,Arial,{title_font},&H00A0F500,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,1,0,1,0,0,7,20,20,20,1
Style: SidebarBadge,Arial,{badge_font},&H00C0FE5F,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,1,0,1,0,0,7,20,20,20,1
Style: SidebarWord,Arial,{word_font},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,1,0,0,100,100,0,0,1,0,0,7,20,20,20,1
Style: SidebarBody,Arial,{body_font},&H00ECF2E0,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,20,20,20,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    events = []
    for caption in captions:
        start, end = ass_time(caption["start"]), ass_time(caption["end"])
        
        # Bottom subtitle on video (clean text, no keyword highlighting, multi-speaker dialogue turn formatting)
        sub_display = str(caption.get("text", "")).strip()
        if " - " in sub_display:
            sub_display = sub_display.replace(" - ", "\\N- ")
        events.append(f"Dialogue: 0,{start},{end},Caption,,0,0,0,,{{\\pos({video_width // 2},{y_caption})}}{ass_text(sub_display)}")
        
        # Right sidebar
        keywords = caption.get("keywords") or []
        if len(keywords) > 1:
            # Multi-keyword mode: explain ALL keywords in the downloaded video sidebar!
            blocks = []
            for kw in keywords[:3]:
                kw_word = kw.get("word", "").capitalize()
                raw_m = kw.get("meaning", "").strip()
                lines = [l.strip() for l in raw_m.split("\n") if l.strip()]
                pos = ""
                def_lines = []
                for l in lines:
                    m_pos = re.search(r"Type:\s*([a-z]+)", l, re.I)
                    if m_pos:
                        pos = f" ({m_pos.group(1).lower()})"
                    elif l.startswith("1. "):
                        def_lines.append(l[3:])
                    elif l.startswith("2. ") and not pos:
                        def_lines.append(l[3:])
                    elif l.startswith(("3. ", "4. ")) and len(def_lines) < 2:
                        def_lines.append(l[3:])
                if not def_lines and lines:
                    def_lines = lines[:2]
                
                kw_head = f"{{\\b1\\c&HA0F500&}}* {kw_word}{{\\b0\\c&HC0FE5F&}}{pos}:"
                kw_body = wrap_ass_lines(" ".join(def_lines), max_chars=max_sidebar_chars)
                blocks.append(f"{kw_head}\\N{{\\c&HECF2E0&}}{kw_body}")
            
            if len(keywords) > 3:
                more_names = ", ".join(k.get("word", "") for k in keywords[3:] if k.get("word"))
                if more_names:
                    blocks.append(f"{{\\b1\\c&HC0FE5F&}}More words: {{\\b0\\c&HECF2E0&}}{wrap_ass_lines(more_names, max_chars=max_sidebar_chars)}")

            multi_body = "\\N\\N".join(blocks)
            events.append(f"Dialogue: 1,{start},{end},SidebarTitle,,0,0,0,,{{\\pos({x},{y_title})}}PAUSE & LEARN")
            events.append(f"Dialogue: 1,{start},{end},SidebarBadge,,0,0,0,,{{\\pos({x},{y_badge})}}KEYWORDS & MEANINGS ({len(keywords)})")
            events.append(f"Dialogue: 1,{start},{end},SidebarBody,,0,0,0,,{{\\pos({x},{y_word})}}{multi_body}")
        else:
            term = str(caption.get("term", "Meaning")).strip()
            type_str = "IDIOM" if re.search(r"^Idiom", term, re.I) else "MEANING"
            word_str = re.sub(r"^(Meaning|Idiom)\s*[—–-]\s*", "", term, flags=re.I).strip()
            if not word_str or word_str == "Meaning":
                word_str = caption.get("text", "")[:24]

            raw_meaning = caption.get("meaning", "")
            meaning_formatted = wrap_ass_lines(raw_meaning, max_chars=max_sidebar_chars)

            events.append(f"Dialogue: 1,{start},{end},SidebarTitle,,0,0,0,,{{\\pos({x},{y_title})}}PAUSE & LEARN")
            events.append(f"Dialogue: 1,{start},{end},SidebarBadge,,0,0,0,,{{\\pos({x},{y_badge})}}{type_str}")
            events.append(f"Dialogue: 1,{start},{end},SidebarWord,,0,0,0,,{{\\pos({x},{y_word})}}{ass_text(word_str)}")
            events.append(f"Dialogue: 1,{start},{end},SidebarBody,,0,0,0,,{{\\pos({x},{y_body})}}{meaning_formatted}")
    return header + "\n".join(events) + "\n"


@app.post("/api/projects/{project_id}/extract-audio")
async def extract_audio(project_id: str):
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        raise HTTPException(503, "FFmpeg is not installed. Install it to extract audio.")
    directory = project_dir(project_id)
    output = directory / "source-audio.mp3"
    run_ffmpeg([ffmpeg, "-y", "-i", str(find_source(directory)), "-vn", "-q:a", "2", str(output)])
    return {"download_url": f"/api/projects/{project_id}/download-audio"}


@app.get("/api/projects/{project_id}/download-audio")
async def download_audio(project_id: str):
    output = project_dir(project_id) / "source-audio.mp3"
    if not output.exists():
        raise HTTPException(404, "Extract audio before downloading.")
    return FileResponse(output, media_type="audio/mpeg", filename=f"captionlearn-{project_id}-audio.mp3")


def background_render_learning_video(directory: Path, captions_json: str) -> None:
    try:
        ffmpeg = ffmpeg_path()
        if not ffmpeg:
            return
        captions = parse_captions(captions_json)
        output = directory / "learning-mode-video.mp4"
        captions_hash = hashlib.sha256(captions_json.encode("utf-8")).hexdigest()
        hash_file = directory / "learning-mode.hash"
        if output.exists() and hash_file.exists() and hash_file.read_text(encoding="utf-8").strip() == captions_hash:
            return
        source = find_source(directory)
        width, height = video_dimensions(source)
        sidebar_width = max(320, min(640, int(width * 0.45)))
        if (width + sidebar_width) % 2 != 0:
            sidebar_width += 1
        ass = directory / "learning-mode.ass"
        ass.write_text(make_learning_ass(captions, width, height, sidebar_width), encoding="utf-8")
        ass_path = str(ass.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        filter_graph = f"pad=width=ceil((iw+{sidebar_width})/2)*2:height=ceil(ih/2)*2:x=0:y=0:color=0x061510,subtitles='{ass_path}'"
        run_ffmpeg([
            ffmpeg, "-y", "-i", str(source),
            "-vf", filter_graph,
            "-map", "0:v:0", "-map", "0:a?",
            "-c:v", "libx264", "-crf", "24", "-preset", "ultrafast", "-tune", "fastdecode", "-threads", "0",
            "-c:a", "copy",
            str(output)
        ])
        hash_file.write_text(captions_hash, encoding="utf-8")
    except Exception as e:
        pass


@app.post("/api/projects/{project_id}/burn-subtitles")
async def burn_subtitles(project_id: str):
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        raise HTTPException(503, "FFmpeg is not installed. Install it to export a subtitled video.")
    directory = project_dir(project_id)
    srt = directory / "subtitles.srt"
    if not srt.exists():
        raise HTTPException(422, "Save subtitles before exporting the video.")
    output = directory / "subtitled-video.mp4"
    srt_hash = hashlib.sha256(srt.read_bytes()).hexdigest()
    hash_file = directory / "subtitled-video.hash"
    if output.exists() and hash_file.exists() and hash_file.read_text(encoding="utf-8").strip() == srt_hash:
        return {"download_url": f"/api/projects/{project_id}/download-video"}
    subtitle_path = str(srt.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    filter_graph = f"pad=width=ceil(iw/2)*2:height=ceil(ih/2)*2:x=0:y=0,subtitles='{subtitle_path}'"
    run_ffmpeg([
        ffmpeg, "-y", "-i", str(find_source(directory)),
        "-vf", filter_graph,
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-crf", "24", "-preset", "ultrafast", "-tune", "fastdecode", "-threads", "0",
        "-c:a", "copy",
        str(output)
    ])
    try:
        hash_file.write_text(srt_hash, encoding="utf-8")
    except Exception:
        pass
    return {"download_url": f"/api/projects/{project_id}/download-video"}


@app.get("/api/projects/{project_id}/download-video")
async def download_video(project_id: str):
    output = project_dir(project_id) / "subtitled-video.mp4"
    if not output.exists():
        raise HTTPException(404, "Export the subtitled video before downloading.")
    return FileResponse(output, media_type="video/mp4", filename=f"captionlearn-{project_id}-subtitled.mp4")


@app.post("/api/projects/{project_id}/export-learning-video")
async def export_learning_video(project_id: str, captions_json: str = Form(...)):
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        raise HTTPException(503, "FFmpeg is not installed. Install it to export a learning video.")
    directory = project_dir(project_id)
    captions = parse_captions(captions_json)
    write_captions(directory, captions)

    output = directory / "learning-mode-video.mp4"
    captions_hash = hashlib.sha256(captions_json.encode("utf-8")).hexdigest()
    hash_file = directory / "learning-mode.hash"

    # Instant response if already rendered for these captions!
    if output.exists() and hash_file.exists() and hash_file.read_text(encoding="utf-8").strip() == captions_hash:
        return {"download_url": f"/api/projects/{project_id}/download-learning-video", "cached": True}

    source = find_source(directory)
    width, height = video_dimensions(source)
    sidebar_width = max(320, min(640, int(width * 0.45)))
    if (width + sidebar_width) % 2 != 0:
        sidebar_width += 1
    ass = directory / "learning-mode.ass"
    ass.write_text(make_learning_ass(captions, width, height, sidebar_width), encoding="utf-8")
    ass_path = str(ass.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    output = directory / "learning-mode-video.mp4"
    filter_graph = f"pad=width=ceil((iw+{sidebar_width})/2)*2:height=ceil(ih/2)*2:x=0:y=0:color=0x061510,subtitles='{ass_path}'"
    run_ffmpeg([
        ffmpeg, "-y", "-i", str(source),
        "-vf", filter_graph,
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-crf", "24", "-preset", "ultrafast", "-tune", "fastdecode", "-threads", "0",
        "-c:a", "copy",
        str(output)
    ])
    try:
        hash_file.write_text(captions_hash, encoding="utf-8")
    except Exception:
        pass
    return {"download_url": f"/api/projects/{project_id}/download-learning-video"}


@app.get("/api/projects/{project_id}/download-learning-video")
async def download_learning_video(project_id: str):
    output = project_dir(project_id) / "learning-mode-video.mp4"
    if not output.exists():
        raise HTTPException(404, "Export the learning-mode video before downloading.")
    return FileResponse(output, media_type="video/mp4", filename=f"captionlearn-{project_id}-learning-mode.mp4")


from captionlearn_addons import install as install_captionlearn
install_captionlearn(app, globals())


MODEL_CACHE = {}
LANGUAGE_PROMPTS = {
    "ta": "தமிழில் தெளிவாக பேசப்படுகிறது.",
    "en": None
}

def grapheme_len(value: str) -> int:
    try:
        import regex
        return len(regex.findall(r"\\X", value))
    except Exception:
        return len(value)

def captionlearn_audio(directory: Path, denoise: bool = False) -> Path:
    audio = directory / "captionlearn-clean.wav"
    if audio.exists() and audio.stat().st_size > 1000:
        return audio
    source = find_source(directory)
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        raise HTTPException(503, "FFmpeg is required for audio extraction.")
    # Direct high-speed audio extraction (16kHz mono WAV)
    run_ffmpeg([ffmpeg, "-y", "-nostdin", "-threads", "2", "-i", str(source), "-vn", "-sn", "-dn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-nostats", "-loglevel", "error", str(audio)])
    return audio

def detect_captionlearn_language(audio: Path) -> dict:
    try:
        import whisper
        model = MODEL_CACHE.setdefault("detect", whisper.load_model("base"))
        import whisper.audio
        sample = whisper.audio.load_audio(str(audio))[: 30 * whisper.audio.SAMPLE_RATE]
        mel = whisper.log_mel_spectrogram(whisper.pad_or_trim(sample)).to(model.device)
        _, probs = model.detect_language(mel)
        choice = max((code for code in ("ta", "en")), key=lambda c: probs.get(c, 0.0))
        return {"language": choice, "confidence": round(float(probs.get(choice, 0))*100, 1)}
    except Exception:
        return {"language":"en", "confidence":0.0, "warning":"Language detection failed; choose a language manually."}

def normalize_caption_timings(captions: list[dict]) -> list[dict]:
    """Ensures subtitles are accurately aligned, readable without flickering, and bridge small speech pauses."""
    if not captions:
        return captions
    for i in range(len(captions)):
        c = captions[i]
        start = float(c["start"])
        end = float(c["end"])
        next_start = float(captions[i + 1]["start"]) if i + 1 < len(captions) else (end + 2.5)

        # Bridge small pauses/gaps between consecutive speech bursts (< 0.65s) to eliminate flickering
        if i + 1 < len(captions):
            gap = next_start - end
            if 0.0 < gap <= 0.65:
                end = round(next_start - 0.04, 2)

        # Ensure a minimum readability duration of 1.4s (capped so it never collides with next caption)
        if end - start < 1.4:
            max_end = next_start - 0.05 if i + 1 < len(captions) else (start + 1.8)
            if max_end > start:
                end = round(min(start + 1.4, max_end), 2)

        c["start"] = round(start, 2)
        c["end"] = round(max(end, start + 0.35), 2)
    return captions


def transcribe_captionlearn(directory: Path, language: str="en", quality: str="fast", explanation_language: str="same", detect_only: bool=False, denoise: bool=False, use_initial_prompt: bool=False):
    auto_captions_file = directory / "auto-captions.json"
    if not detect_only and auto_captions_file.exists():
        try:
            cached_data = json.loads(auto_captions_file.read_text(encoding="utf-8"))
            cached_list = cached_data if isinstance(cached_data, list) else cached_data.get("captions", [])
            if cached_list:
                return {
                    "captions": cached_list,
                    "language_used": "en",
                    "explanation_language": "en",
                    "model_used": "cached",
                    "warnings": [],
                    "progress": ["Loaded cached captions"]
                }
        except Exception:
            pass

    audio = captionlearn_audio(directory, denoise)
    warnings=[]
    detected = detect_captionlearn_language(audio) if language == "auto" or detect_only else None
    if detect_only:
        return {"detected_language":detected["language"], "confidence":detected["confidence"], "captions":[], "warnings":[detected.get("warning")] if detected.get("warning") else []}
    used_language = detected["language"] if language == "auto" else language
    is_cloud = bool(os.getenv("RENDER") or os.getenv("PORT") or os.getenv("APP_ENV") == "production")
    if used_language == "en":
        # On localhost: base.en runs in 2.8s with gold-standard accuracy.
        # On Render: tiny.en runs in 5s; base.en for balanced.
        if is_cloud:
            model_name = {"fast": "tiny.en", "balanced": "base.en", "best": "small.en"}.get(quality, "tiny.en")
        else:
            model_name = {"fast": "base.en", "balanced": "base.en", "best": "small.en"}.get(quality, "base.en")
    else:
        model_name = {"fast": "tiny", "balanced": "base", "best": "small"}.get(quality, "tiny")
    device="cpu"; warnings = []
    try:
        import torch
        if torch.cuda.is_available(): device="cuda"
    except Exception: pass
    if quality == "best" and device == "cpu": warnings.append("Best quality uses the small model on CPU.")
    try:
        from faster_whisper import WhisperModel
        cpu_threads = 2 if is_cloud else min(os.cpu_count() or 4, 4)
        cache_key = f"fw:{model_name}:{device}:{cpu_threads}"
        model = MODEL_CACHE.get(cache_key)
        if model is None:
            model = WhisperModel(model_name, device=device, compute_type="float16" if device=="cuda" else "int8", cpu_threads=cpu_threads)
            MODEL_CACHE[cache_key] = model
        
        accurate_prompt = (
            "Accurate English subtitles with standard capitalization, punctuation, contractions, and idioms."
            if used_language == "en" else LANGUAGE_PROMPTS.get(used_language)
        )
        try:
            segments, info = model.transcribe(
                str(audio),
                language=used_language,
                beam_size=2 if not is_cloud else 1,
                best_of=1,
                temperature=0.0,
                condition_on_previous_text=False,
                compression_ratio_threshold=2.4,
                no_speech_threshold=0.6,
                word_timestamps=True,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=400, speech_pad_ms=250),
                initial_prompt=accurate_prompt
            )
        except Exception:
            segments, info = model.transcribe(
                str(audio),
                language=used_language,
                beam_size=1,
                best_of=1,
                temperature=0.0,
                condition_on_previous_text=False,
                compression_ratio_threshold=2.4,
                word_timestamps=True,
                vad_filter=False,
                initial_prompt=accurate_prompt
            )
        raw=[]
        for segment in segments:
            words=[]
            for w in (segment.words or []):
                w_str = w.word.strip()
                if w_str:
                    words.append({"word": w_str, "start": round(float(w.start), 2), "end": round(float(w.end), 2), "probability": float(getattr(w, "probability", 1.0) or 0.0)})
            if not words and segment.text and segment.text.strip():
                seg_words = segment.text.strip().split()
                if seg_words:
                    dur = max(0.1, (float(segment.end) - float(segment.start)) / len(seg_words))
                    s_t = float(segment.start)
                    for sw in seg_words:
                        words.append({"word": sw, "start": round(s_t, 2), "end": round(s_t + dur, 2), "probability": 0.8})
                        s_t += dur
            if words: raw.append(words)
    except Exception as error:
        warnings.append(f"faster-whisper unavailable ({error}); using standard Whisper fallback.")
        import whisper
        key=f"ow:{model_name}"; model=MODEL_CACHE.get(key)
        if model is None: model=whisper.load_model(model_name); MODEL_CACHE[key]=model
        result=model.transcribe(
            str(audio),
            language=used_language,
            fp16=False,
            verbose=False,
            word_timestamps=True,
            beam_size=1,
            best_of=1,
            temperature=0.0,
            condition_on_previous_text=False,
            compression_ratio_threshold=2.4,
            logprob_threshold=None,
            no_speech_threshold=None,
            initial_prompt=LANGUAGE_PROMPTS.get(used_language) if use_initial_prompt else None
        )
        raw=[]
        for s in result.get("segments",[]):
            words=[{"word":str(w.get("word","")).strip(),"start":round(float(w.get("start",s["start"])), 2),"end":round(float(w.get("end",s["end"])), 2),"probability":float(w.get("probability",1.0) or 0.0)} for w in s.get("words",[]) if str(w.get("word","")).strip()]
            if not words and s.get("text", "").strip():
                seg_words = s["text"].strip().split()
                if seg_words:
                    dur = max(0.1, (float(s["end"]) - float(s["start"])) / len(seg_words))
                    s_t = float(s["start"])
                    for sw in seg_words:
                        words.append({"word": sw, "start": round(s_t, 2), "end": round(s_t + dur, 2), "probability": 0.8})
                        s_t += dur
            if words: raw.append(words)
    limit, seconds = (32, 4.2) if used_language == "ta" else (42, 3.6)
    captions=[]
    for words in raw:
        group=[]; start=None
        for word in words:
            if start is None: start=word["start"]
            trial=" ".join(x["word"] for x in group+[word])

            gap = (word["start"] - group[-1]["end"]) if group else 0.0
            prev_ended = bool(group and group[-1]["word"].rstrip().endswith((".", "!", "?")))
            is_new_turn = word["word"].startswith(("-", "—", ">", ":"))

            split_now = False
            if group:
                if grapheme_len(trial) > limit or (word["end"] - start > seconds):
                    split_now = True
                elif gap >= 0.45 and len(group) >= 2:
                    split_now = True
                elif prev_ended and (gap >= 0.18 or len(group) >= 3):
                    split_now = True
                elif is_new_turn and len(group) >= 1:
                    split_now = True

            if split_now:
                text=unicodedata.normalize("NFC"," ".join(x["word"] for x in group)).strip()
                if text:
                    captions.append(captionlearn_study_caption(start, group[-1]["end"], text, used_language, group))
                group=[word]; start=word["start"]
            else: group.append(word)
        if group and start is not None:
            text=unicodedata.normalize("NFC"," ".join(x["word"] for x in group)).strip()
            if text:
                captions.append(captionlearn_study_caption(start, group[-1]["end"], text, used_language, group))
    if not captions: raise HTTPException(422,"No clear speech was detected. Try a cleaner clip or another language.")
    
    # Normalize timings so words remain visible smoothly without abrupt flickering
    captions = normalize_caption_timings(captions)

    try:
        (directory / "auto-captions.json").write_text(json.dumps(captions, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    return {"captions":captions,"language_used":used_language,"explanation_language":used_language if explanation_language=="same" else explanation_language,"model_used":model_name,"warnings":[w for w in warnings if w],"progress":["Extracting audio","Transcribing","Building cards"]}

transcribe_locally = transcribe_captionlearn
def captionlearn_study_caption(start: float, end: float, text: str, language: str, words: list[dict]) -> dict:
    """Safety flags annotate captions; they never stop subtitle generation."""
    try:
        card = explanation_for_text(text) if language == "en" else {"term": "Meaning", "meaning": text, "explanation": "", "keywords": []}
    except Exception:
        card = {"term": "Meaning", "meaning": "Meaning is unavailable for this caption. You can edit it in the timeline.", "explanation": "", "keywords": []}
    return {
        "start": round(float(start), 2), "end": round(max(float(end), float(start) + .8), 2), "text": text,
        "term": card.get("term", "Meaning"), "meaning": card.get("meaning", ""), "explanation": card.get("explanation", ""),
        "keywords": card.get("keywords", []),
        "language": language, "words": words, "low_confidence": any(x.get("probability", 1) < .55 for x in words),
        "inappropriate": has_inappropriate_language(text),
    }


def warmup_models():
    try:
        from nltk.corpus import wordnet
        wordnet.synsets("test")
    except Exception:
        pass
    try:
        from faster_whisper import WhisperModel
        cpu_threads = min(os.cpu_count() or 4, 8)
        cache_key = f"fw:base.en:cpu:{cpu_threads}"
        if cache_key not in MODEL_CACHE:
            MODEL_CACHE[cache_key] = WhisperModel("base.en", device="cpu", compute_type="int8", cpu_threads=cpu_threads)
    except Exception:
        pass

import threading
threading.Thread(target=warmup_models, daemon=True).start()








