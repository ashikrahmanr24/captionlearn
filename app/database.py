import sqlite3
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import settings

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(settings.SQLITE_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'student',
        student_id TEXT,
        phone TEXT,
        created_at TEXT NOT NULL
    )
    """)
    
    # Items table (Lost & Found)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS items (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        user_name TEXT NOT NULL,
        user_email TEXT NOT NULL,
        type TEXT NOT NULL, -- 'lost' or 'found'
        category TEXT NOT NULL DEFAULT 'other',
        title TEXT NOT NULL,
        brand TEXT,
        color TEXT,
        location TEXT NOT NULL,
        item_date TEXT NOT NULL,
        description TEXT NOT NULL,
        image_url TEXT,
        image_hash TEXT,
        image_features TEXT, -- JSON string
        safekeeping_location TEXT,
        status TEXT NOT NULL DEFAULT 'open', -- 'open', 'matched', 'claimed', 'resolved'
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """)
    
    # Matches table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS matches (
        id TEXT PRIMARY KEY,
        lost_item_id TEXT NOT NULL,
        found_item_id TEXT NOT NULL,
        overall_score REAL NOT NULL,
        text_score REAL NOT NULL,
        location_score REAL NOT NULL,
        date_score REAL NOT NULL,
        brand_color_score REAL NOT NULL,
        image_score REAL,
        status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'approved', 'rejected', 'claimed', 'resolved'
        explanation TEXT, -- JSON breakdown
        created_at TEXT NOT NULL,
        FOREIGN KEY (lost_item_id) REFERENCES items (id) ON DELETE CASCADE,
        FOREIGN KEY (found_item_id) REFERENCES items (id) ON DELETE CASCADE,
        UNIQUE(lost_item_id, found_item_id)
    )
    """)
    
    # Notifications table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        item_id TEXT,
        match_id TEXT,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        score REAL,
        read_status INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """)
    
    # Claims table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS claims (
        id TEXT PRIMARY KEY,
        match_id TEXT NOT NULL,
        lost_item_id TEXT NOT NULL,
        found_item_id TEXT NOT NULL,
        claimant_id TEXT NOT NULL,
        claimant_name TEXT NOT NULL,
        finder_id TEXT NOT NULL,
        finder_name TEXT NOT NULL,
        proof_details TEXT NOT NULL,
        contact_info TEXT,
        status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
        created_at TEXT NOT NULL,
        FOREIGN KEY (match_id) REFERENCES matches (id),
        FOREIGN KEY (claimant_id) REFERENCES users (id)
    )
    """)
    
    # Audit sync logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cloud_sync_logs (
        id TEXT PRIMARY KEY,
        event TEXT NOT NULL,
        details TEXT,
        created_at TEXT NOT NULL
    )
    """)
    
    conn.commit()
    conn.close()

# User helpers
def create_user(name: str, email: str, password_hash: str, role: str = "student",
                student_id: str = "", phone: str = "") -> Dict[str, Any]:
    user_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (id, name, email, password_hash, role, student_id, phone, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, name, email.lower().strip(), password_hash, role, student_id, phone, created_at))
    conn.commit()
    conn.close()
    return get_user_by_id(user_id)

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE lower(email) = lower(?)", (email.strip(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, role, student_id, phone, created_at FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def list_all_users() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, role, student_id, phone, created_at FROM users ORDER BY created_at DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

# Items helpers
def create_item(user_id: str, user_name: str, user_email: str, item_type: str,
                title: str, category: str, location: str, item_date: str,
                description: str, brand: str = "", color: str = "",
                image_url: str = "", image_hash: str = "", image_features: Any = None,
                safekeeping_location: str = "") -> Dict[str, Any]:
    item_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    features_str = json.dumps(image_features) if isinstance(image_features, dict) else str(image_features or "{}")
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO items (
            id, user_id, user_name, user_email, type, category, title, brand, color,
            location, item_date, description, image_url, image_hash, image_features,
            safekeeping_location, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
    """, (
        item_id, user_id, user_name, user_email, item_type.lower(), category.lower(),
        title.strip(), brand.strip(), color.strip(), location.strip(), item_date.strip(),
        description.strip(), image_url, image_hash, features_str, safekeeping_location.strip(), created_at
    ))
    conn.commit()
    conn.close()
    return get_item_by_id(item_id)

def get_item_by_id(item_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM items WHERE id = ?", (item_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    try:
        d["image_features"] = json.loads(d.get("image_features") or "{}")
    except Exception:
        d["image_features"] = {}
    return d

def list_items(item_type: Optional[str] = None, user_id: Optional[str] = None,
               category: Optional[str] = None, query: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    sql = "SELECT * FROM items WHERE 1=1"
    params = []
    
    if item_type:
        sql += " AND type = ?"
        params.append(item_type.lower())
    if user_id:
        sql += " AND user_id = ?"
        params.append(user_id)
    if category and category.lower() != "all":
        sql += " AND category = ?"
        params.append(category.lower())
    if query:
        q = f"%{query.strip().lower()}%"
        sql += " AND (lower(title) LIKE ? OR lower(description) LIKE ? OR lower(location) LIKE ? OR lower(brand) LIKE ?)"
        params.extend([q, q, q, q])
        
    sql += " ORDER BY created_at DESC"
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["image_features"] = json.loads(d.get("image_features") or "{}")
        except Exception:
            d["image_features"] = {}
        result.append(d)
    return result

def delete_item(item_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM matches WHERE lost_item_id = ? OR found_item_id = ?", (item_id, item_id))
    cursor.execute("DELETE FROM items WHERE id = ?", (item_id,))
    rows = cursor.rowcount
    conn.commit()
    conn.close()
    return rows > 0

# Matches helpers
def save_or_update_match(lost_item_id: str, found_item_id: str, overall_score: float,
                         text_score: float, location_score: float, date_score: float,
                         brand_color_score: float, image_score: Optional[float],
                         explanation: Dict[str, Any]) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check if match already exists
    cursor.execute("SELECT id, status FROM matches WHERE lost_item_id = ? AND found_item_id = ?", (lost_item_id, found_item_id))
    existing = cursor.fetchone()
    
    now_str = datetime.now(timezone.utc).isoformat()
    exp_str = json.dumps(explanation)
    
    if existing:
        match_id = existing["id"]
        cursor.execute("""
            UPDATE matches SET
                overall_score = ?, text_score = ?, location_score = ?,
                date_score = ?, brand_color_score = ?, image_score = ?,
                explanation = ?, created_at = ?
            WHERE id = ?
        """, (overall_score, text_score, location_score, date_score, brand_color_score, image_score, exp_str, now_str, match_id))
    else:
        match_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO matches (
                id, lost_item_id, found_item_id, overall_score, text_score, location_score,
                date_score, brand_color_score, image_score, status, explanation, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
        """, (match_id, lost_item_id, found_item_id, overall_score, text_score, location_score, date_score, brand_color_score, image_score, exp_str, now_str))
        
    conn.commit()
    conn.close()
    return match_id

def list_matches(user_id: Optional[str] = None, min_score: float = 50.0,
                 status: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    
    sql = """
        SELECT 
            m.*,
            li.title as lost_title, li.category as lost_category, li.brand as lost_brand,
            li.color as lost_color, li.location as lost_location, li.item_date as lost_date,
            li.description as lost_description, li.image_url as lost_image, li.user_id as lost_user_id,
            li.user_name as lost_user_name, li.user_email as lost_user_email,
            
            fi.title as found_title, fi.category as found_category, fi.brand as found_brand,
            fi.color as found_color, fi.location as found_location, fi.item_date as found_date,
            fi.description as found_description, fi.image_url as found_image, fi.user_id as found_user_id,
            fi.user_name as found_user_name, fi.user_email as found_user_email,
            fi.safekeeping_location as found_safekeeping
        FROM matches m
        JOIN items li ON m.lost_item_id = li.id
        JOIN items fi ON m.found_item_id = fi.id
        WHERE m.overall_score >= ?
    """
    params = [min_score]
    
    if user_id:
        sql += " AND (li.user_id = ? OR fi.user_id = ?)"
        params.extend([user_id, user_id])
    if status and status != "all":
        sql += " AND m.status = ?"
        params.append(status)
        
    sql += " ORDER BY m.overall_score DESC, m.created_at DESC"
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["explanation"] = json.loads(d.get("explanation") or "{}")
        except Exception:
            d["explanation"] = {}
        result.append(d)
    return result

def get_match_by_id(match_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            m.*,
            li.title as lost_title, li.category as lost_category, li.brand as lost_brand,
            li.color as lost_color, li.location as lost_location, li.item_date as lost_date,
            li.description as lost_description, li.image_url as lost_image, li.user_id as lost_user_id,
            li.user_name as lost_user_name, li.user_email as lost_user_email,
            
            fi.title as found_title, fi.category as found_category, fi.brand as found_brand,
            fi.color as found_color, fi.location as found_location, fi.item_date as found_date,
            fi.description as found_description, fi.image_url as found_image, fi.user_id as found_user_id,
            fi.user_name as found_user_name, fi.user_email as found_user_email,
            fi.safekeeping_location as found_safekeeping
        FROM matches m
        JOIN items li ON m.lost_item_id = li.id
        JOIN items fi ON m.found_item_id = fi.id
        WHERE m.id = ?
    """, (match_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    try:
        d["explanation"] = json.loads(d.get("explanation") or "{}")
    except Exception:
        d["explanation"] = {}
    return d

def update_match_status(match_id: str, new_status: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE matches SET status = ? WHERE id = ?", (new_status, match_id))
    
    if new_status in ("claimed", "resolved"):
        # Also mark items as matched/resolved
        cursor.execute("""
            UPDATE items SET status = 'resolved'
            WHERE id IN (SELECT lost_item_id FROM matches WHERE id = ?)
               OR id IN (SELECT found_item_id FROM matches WHERE id = ?)
        """, (match_id, match_id))
        
    conn.commit()
    conn.close()
    return True

# Notification helpers
def create_notification(user_id: str, title: str, message: str,
                        item_id: Optional[str] = None, match_id: Optional[str] = None,
                        score: Optional[float] = None) -> str:
    nid = str(uuid.uuid4())
    now_str = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO notifications (id, user_id, item_id, match_id, title, message, score, read_status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
    """, (nid, user_id, item_id, match_id, title, message, score, now_str))
    conn.commit()
    conn.close()
    return nid

def list_user_notifications(user_id: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 30", (user_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def mark_notifications_read(user_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE notifications SET read_status = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return True

# Claims helpers
def create_claim(match_id: str, lost_item_id: str, found_item_id: str,
                 claimant_id: str, claimant_name: str, finder_id: str,
                 finder_name: str, proof_details: str, contact_info: str) -> Dict[str, Any]:
    cid = str(uuid.uuid4())
    now_str = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO claims (
            id, match_id, lost_item_id, found_item_id, claimant_id, claimant_name,
            finder_id, finder_name, proof_details, contact_info, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
    """, (cid, match_id, lost_item_id, found_item_id, claimant_id, claimant_name, finder_id, finder_name, proof_details, contact_info, now_str))
    
    # Update match status to 'claimed'
    cursor.execute("UPDATE matches SET status = 'claimed' WHERE id = ?", (match_id,))
    conn.commit()
    conn.close()
    
    # Notify finder
    create_notification(
        user_id=finder_id,
        title="Claim Request Received!",
        message=f"{claimant_name} submitted a claim verification for your found item report.",
        match_id=match_id
    )
    return {"id": cid, "status": "pending"}

def list_claims(user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    sql = "SELECT * FROM claims WHERE 1=1"
    params = []
    if user_id:
        sql += " AND (claimant_id = ? OR finder_id = ?)"
        params.extend([user_id, user_id])
    sql += " ORDER BY created_at DESC"
    cursor.execute(sql, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def resolve_claim(claim_id: str, approve: bool) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    new_status = "approved" if approve else "rejected"
    cursor.execute("UPDATE claims SET status = ? WHERE id = ?", (new_status, claim_id))
    
    cursor.execute("SELECT match_id, claimant_id, finder_id FROM claims WHERE id = ?", (claim_id,))
    c_row = cursor.fetchone()
    if c_row:
        m_id = c_row["match_id"]
        c_id = c_row["claimant_id"]
        if approve:
            update_match_status(m_id, "resolved")
            create_notification(
                user_id=c_id,
                title="Claim Approved! 🎉",
                message="Your claim has been verified and accepted! Please coordinate collection with the finder or campus authority.",
                match_id=m_id
            )
        else:
            update_match_status(m_id, "pending")
            create_notification(
                user_id=c_id,
                title="Claim Rejected",
                message="Your claim proof could not be verified by the reporter or admin.",
                match_id=m_id
            )
    conn.commit()
    conn.close()
    return True

# Admin analytics
def get_admin_stats() -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT count(*) FROM items WHERE type = 'lost'")
    total_lost = cursor.fetchone()[0]
    
    cursor.execute("SELECT count(*) FROM items WHERE type = 'found'")
    total_found = cursor.fetchone()[0]
    
    cursor.execute("SELECT count(*) FROM matches WHERE overall_score >= ?", (settings.MATCH_MIN_THRESHOLD,))
    total_matches = cursor.fetchone()[0]
    
    cursor.execute("SELECT count(*) FROM matches WHERE overall_score >= ?", (settings.HIGH_CONFIDENCE_THRESHOLD,))
    high_matches = cursor.fetchone()[0]
    
    cursor.execute("SELECT count(*) FROM items WHERE status = 'resolved'")
    resolved_items = cursor.fetchone()[0]
    
    cursor.execute("SELECT count(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT count(*) FROM claims")
    total_claims = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        "total_lost": total_lost,
        "total_found": total_found,
        "total_matches": total_matches,
        "high_confidence_matches": high_matches,
        "resolved_items": resolved_items,
        "total_users": total_users,
        "total_claims": total_claims
    }
