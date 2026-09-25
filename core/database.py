import sqlite3
import os
import json
import hashlib
import hmac
from datetime import datetime, timezone
from typing import Optional, Dict, Tuple

# Optional MongoDB Client
try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None

def get_mongo_db():
    if not MongoClient:
        return None
    mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    try:
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=1500)
        client.admin.command('ping')
        return client["job_agent"]
    except Exception:
        return None

def get_db_file_path() -> str:
    if os.getenv("VERCEL") or os.getenv("AWS_EXECUTION_ENV"):
        return "/tmp/database.db"
    try:
        os.makedirs("data", exist_ok=True)
        return "data/database.db"
    except Exception:
        return "/tmp/database.db"

def get_db_connection():
    db_path = get_db_file_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

# ── PASSWORDS & HASHING ────────────────────────────────────────
# OWASP Recommended: 600,000 iterations for PBKDF2-HMAC-SHA256
DEFAULT_PBKDF2_ITERATIONS = 600000

def hash_password(password: str, salt: bytes = None) -> str:
    if salt is None:
        salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, DEFAULT_PBKDF2_ITERATIONS)
    return f"{salt.hex()}:{key.hex()}:{DEFAULT_PBKDF2_ITERATIONS}"

def verify_password(password: str, hashed_password: str) -> bool:
    try:
        parts = hashed_password.split(":")
        salt_hex = parts[0]
        key_hex = parts[1]
        iterations = int(parts[2]) if len(parts) > 2 else 100000
        salt = bytes.fromhex(salt_hex)
        key = bytes.fromhex(key_hex)
        new_key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
        return hmac.compare_digest(key, new_key)
    except Exception:
        return False

# ── DATABASE INITIALIZATION & MIGRATIONS ──────────────────────
def init_db():
    mongo_db = get_mongo_db()
    if mongo_db is not None:
        print("MongoDB connected successfully! Using MongoDB database 'job_agent'.")
        mongo_db.users.create_index("email", unique=True)
        mongo_db.users.create_index("verification_token")
        mongo_db.users.create_index("reset_token")
        mongo_db.applications.create_index("job_id", unique=True)
        return

    # Fallback to SQLite
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            resume_text TEXT DEFAULT '',
            resume_filename TEXT DEFAULT '',
            api_keys_json TEXT DEFAULT '{}',
            is_verified INTEGER DEFAULT 0,
            verification_token TEXT DEFAULT '',
            verification_token_expires TEXT DEFAULT '',
            reset_token TEXT DEFAULT '',
            reset_token_expires TEXT DEFAULT ''
        )
    """)
    
    # Auto-migration for existing SQLite tables
    existing_cols = [r[1] for r in cursor.execute("PRAGMA table_info(users)").fetchall()]
    new_cols = {
        "is_verified": "INTEGER DEFAULT 1",
        "verification_token": "TEXT DEFAULT ''",
        "verification_token_expires": "TEXT DEFAULT ''",
        "reset_token": "TEXT DEFAULT ''",
        "reset_token_expires": "TEXT DEFAULT ''"
    }
    for col_name, col_def in new_cols.items():
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            job_id TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            url TEXT DEFAULT '',
            fit_score INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Sent',
            date_applied TEXT NOT NULL,
            cover_letter TEXT DEFAULT '',
            recruiter_email_json TEXT DEFAULT '{}',
            linkedin_note TEXT DEFAULT '',
            tailored_resume TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()
    print("Database initialized successfully (SQLite)!")

# --- User operations ---
def get_next_sequence_value(mongo_db, sequence_name):
    seq = mongo_db.counters.find_one_and_update(
        {"_id": sequence_name},
        {"$inc": {"sequence_value": 1}},
        upsert=True,
        return_document=True
    )
    if not seq or "sequence_value" not in seq:
        mongo_db.counters.update_one({"_id": sequence_name}, {"$set": {"sequence_value": 1}}, upsert=True)
        return 1
    return seq["sequence_value"]

def create_user(email: str, password: str, is_verified: int = 0, verification_token: str = "", verification_token_expires: str = "") -> int:
    clean_email = email.strip().lower()
    pwd_hash = hash_password(password)
    mongo_db = get_mongo_db()

    if mongo_db is not None:
        if mongo_db.users.find_one({"email": clean_email}):
            raise ValueError("A user with this email already exists.")
        user_id = get_next_sequence_value(mongo_db, "user_id")
        user_doc = {
            "id": user_id,
            "email": clean_email,
            "password_hash": pwd_hash,
            "resume_text": "",
            "resume_filename": "",
            "api_keys_json": "{}",
            "is_verified": is_verified,
            "verification_token": verification_token,
            "verification_token_expires": verification_token_expires,
            "reset_token": "",
            "reset_token_expires": ""
        }
        mongo_db.users.insert_one(user_doc)
        return user_id

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO users (email, password_hash, is_verified, verification_token, verification_token_expires) 
               VALUES (?, ?, ?, ?, ?)""",
            (clean_email, pwd_hash, is_verified, verification_token, verification_token_expires)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        raise ValueError("A user with this email already exists.")
    finally:
        conn.close()

def verify_user(email: str, password: str) -> Optional[dict]:
    clean_email = email.strip().lower()
    mongo_db = get_mongo_db()

    if mongo_db is not None:
        user = mongo_db.users.find_one({"email": clean_email})
        if user and verify_password(password, user["password_hash"]):
            return {
                "id": user["id"],
                "email": user["email"],
                "is_verified": user.get("is_verified", 1)
            }
        return None

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (clean_email,))
    user = cursor.fetchone()
    conn.close()
    if user and verify_password(password, user["password_hash"]):
        u_dict = dict(user)
        return {
            "id": u_dict["id"],
            "email": u_dict["email"],
            "is_verified": u_dict.get("is_verified", 1)
        }
    return None

def get_user_by_id(user_id: int) -> Optional[dict]:
    mongo_db = get_mongo_db()
    if mongo_db is not None:
        user = mongo_db.users.find_one({"id": user_id})
        if user:
            return {
                "id": user["id"],
                "email": user["email"],
                "resume_text": user.get("resume_text", ""),
                "resume_filename": user.get("resume_filename", ""),
                "api_keys_json": user.get("api_keys_json", "{}"),
                "is_verified": user.get("is_verified", 1)
            }
        return None

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, resume_text, resume_filename, api_keys_json, is_verified FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def set_verification_token(user_id: int, token: str, expires_iso: str):
    mongo_db = get_mongo_db()
    if mongo_db is not None:
        mongo_db.users.update_one(
            {"id": user_id},
            {"$set": {"verification_token": token, "verification_token_expires": expires_iso}}
        )
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET verification_token = ?, verification_token_expires = ? WHERE id = ?",
        (token, expires_iso, user_id)
    )
    conn.commit()
    conn.close()

def verify_email_token(token: str) -> Tuple[bool, str]:
    """Validates email verification token and sets is_verified=1."""
    if not token:
        return False, "Verification token is required."
        
    now_iso = datetime.now(timezone.utc).isoformat()
    mongo_db = get_mongo_db()
    
    if mongo_db is not None:
        user = mongo_db.users.find_one({"verification_token": token})
        if not user:
            return False, "Invalid or expired verification token."
        expires = user.get("verification_token_expires", "")
        if expires and expires < now_iso:
            return False, "Verification token has expired. Please request a new one."
            
        mongo_db.users.update_one(
            {"id": user["id"]},
            {"$set": {"is_verified": 1, "verification_token": "", "verification_token_expires": ""}}
        )
        return True, "Email verified successfully!"

    # SQLite fallback
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE verification_token = ?", (token,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return False, "Invalid or expired verification token."
    
    u_dict = dict(user)
    expires = u_dict.get("verification_token_expires", "")
    if expires and expires < now_iso:
        conn.close()
        return False, "Verification token has expired. Please request a new one."
        
    cursor.execute(
        "UPDATE users SET is_verified = 1, verification_token = '', verification_token_expires = '' WHERE id = ?",
        (u_dict["id"],)
    )
    conn.commit()
    conn.close()
    return True, "Email verified successfully!"

def set_password_reset_token(email: str, token: str, expires_iso: str) -> bool:
    clean_email = email.strip().lower()
    mongo_db = get_mongo_db()
    if mongo_db is not None:
        res = mongo_db.users.update_one(
            {"email": clean_email},
            {"$set": {"reset_token": token, "reset_token_expires": expires_iso}}
        )
        return res.matched_count > 0

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET reset_token = ?, reset_token_expires = ? WHERE email = ?",
        (token, expires_iso, clean_email)
    )
    conn.commit()
    count = cursor.rowcount
    conn.close()
    return count > 0

def verify_reset_token_and_update_password(token: str, new_password: str) -> Tuple[bool, str]:
    if not token:
        return False, "Reset token is required."
    now_iso = datetime.now(timezone.utc).isoformat()
    new_pwd_hash = hash_password(new_password)
    mongo_db = get_mongo_db()

    if mongo_db is not None:
        user = mongo_db.users.find_one({"reset_token": token})
        if not user:
            return False, "Invalid or expired password reset token."
        expires = user.get("reset_token_expires", "")
        if expires and expires < now_iso:
            return False, "Password reset token has expired."
            
        mongo_db.users.update_one(
            {"id": user["id"]},
            {"$set": {"password_hash": new_pwd_hash, "reset_token": "", "reset_token_expires": ""}}
        )
        return True, "Password reset successfully! You can now log in."

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE reset_token = ?", (token,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return False, "Invalid or expired password reset token."
    u_dict = dict(user)
    expires = u_dict.get("reset_token_expires", "")
    if expires and expires < now_iso:
        conn.close()
        return False, "Password reset token has expired."

    cursor.execute(
        "UPDATE users SET password_hash = ?, reset_token = '', reset_token_expires = '' WHERE id = ?",
        (new_pwd_hash, u_dict["id"])
    )
    conn.commit()
    conn.close()
    return True, "Password reset successfully! You can now log in."

def update_user_resume(user_id: int, resume_text: str, filename: str):
    mongo_db = get_mongo_db()
    if mongo_db is not None:
        mongo_db.users.update_one(
            {"id": user_id},
            {"$set": {"resume_text": resume_text, "resume_filename": filename}}
        )
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET resume_text = ?, resume_filename = ? WHERE id = ?",
        (resume_text, filename, user_id)
    )
    conn.commit()
    conn.close()

def update_user_api_keys(user_id: int, api_keys: dict):
    json_str = json.dumps(api_keys)
    mongo_db = get_mongo_db()
    if mongo_db is not None:
        mongo_db.users.update_one(
            {"id": user_id},
            {"$set": {"api_keys_json": json_str}}
        )
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET api_keys_json = ? WHERE id = ?",
        (json_str, user_id)
    )
    conn.commit()
    conn.close()

def update_user_password(user_id: int, new_password: str):
    pwd_hash = hash_password(new_password)
    mongo_db = get_mongo_db()
    if mongo_db is not None:
        mongo_db.users.update_one(
            {"id": user_id},
            {"$set": {"password_hash": pwd_hash}}
        )
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pwd_hash, user_id))
    conn.commit()
    conn.close()

# --- Applications operations ---
def add_application(user_id: int, job_id: str, title: str, company: str, url: str, fit_score: int, status: str, cover_letter: str, recruiter_email: dict, linkedin_note: str, tailored_resume: str):
    date_str = datetime.now().isoformat()
    mongo_db = get_mongo_db()

    if mongo_db is not None:
        app_doc = {
            "user_id": user_id,
            "job_id": job_id,
            "title": title,
            "company": company,
            "url": url,
            "fit_score": fit_score,
            "status": status,
            "date_applied": date_str,
            "cover_letter": cover_letter,
            "recruiter_email_json": json.dumps(recruiter_email),
            "linkedin_note": linkedin_note,
            "tailored_resume": tailored_resume
        }
        mongo_db.applications.update_one({"job_id": job_id}, {"$set": app_doc}, upsert=True)
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO applications 
               (user_id, job_id, title, company, url, fit_score, status, date_applied, cover_letter, recruiter_email_json, linkedin_note, tailored_resume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(job_id) DO UPDATE SET
               title=excluded.title, company=excluded.company, url=excluded.url, fit_score=excluded.fit_score,
               status=excluded.status, cover_letter=excluded.cover_letter, recruiter_email_json=excluded.recruiter_email_json,
               linkedin_note=excluded.linkedin_note, tailored_resume=excluded.tailored_resume""",
            (user_id, job_id, title, company, url, fit_score, status, date_str, cover_letter, json.dumps(recruiter_email), linkedin_note, tailored_resume)
        )
        conn.commit()
    finally:
        conn.close()

def get_applications(user_id: int) -> list:
    mongo_db = get_mongo_db()
    if mongo_db is not None:
        apps = list(mongo_db.applications.find({"user_id": user_id}).sort("_id", -1))
        result = []
        for doc in apps:
            item = {
                "id": str(doc.get("_id")),
                "user_id": doc.get("user_id"),
                "job_id": doc.get("job_id"),
                "title": doc.get("title"),
                "company": doc.get("company"),
                "url": doc.get("url", ""),
                "fit_score": doc.get("fit_score", 0),
                "status": doc.get("status", "Sent"),
                "date_applied": doc.get("date_applied", ""),
                "cover_letter": doc.get("cover_letter", ""),
                "linkedin_note": doc.get("linkedin_note", ""),
                "tailored_resume": doc.get("tailored_resume", "")
            }
            try:
                item["recruiter_email"] = json.loads(doc.get("recruiter_email_json", "{}"))
            except Exception:
                item["recruiter_email"] = {}
            result.append(item)
        return result

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM applications WHERE user_id = ? ORDER BY id DESC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for r in rows:
        item = dict(r)
        try:
            item["recruiter_email"] = json.loads(item["recruiter_email_json"])
        except Exception:
            item["recruiter_email"] = {}
        result.append(item)
    return result

def delete_application(user_id: int, job_id: str):
    mongo_db = get_mongo_db()
    if mongo_db is not None:
        mongo_db.applications.delete_one({"user_id": user_id, "job_id": job_id})
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM applications WHERE user_id = ? AND job_id = ?", (user_id, job_id))
    conn.commit()
    conn.close()

def delete_all_applications(user_id: int):
    mongo_db = get_mongo_db()
    if mongo_db is not None:
        mongo_db.applications.delete_many({"user_id": user_id})
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM applications WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
