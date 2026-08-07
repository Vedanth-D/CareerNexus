import sqlite3
import os
import json
import hashlib
import hmac
from datetime import datetime

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

def hash_password(password: str, salt: bytes = None) -> str:
    if salt is None:
        salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return salt.hex() + ":" + key.hex()

def verify_password(password: str, hashed_password: str) -> bool:
    try:
        salt_hex, key_hex = hashed_password.split(":")
        salt = bytes.fromhex(salt_hex)
        key = bytes.fromhex(key_hex)
        new_key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        return hmac.compare_digest(key, new_key)
    except Exception:
        return False

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create Users Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            resume_text TEXT DEFAULT '',
            resume_filename TEXT DEFAULT '',
            api_keys_json TEXT DEFAULT '{}'
        )
    """)
    
    # Create Applications Table
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
    print("Database initialized successfully!")

# --- User operations ---
def create_user(email: str, password: str) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    pwd_hash = hash_password(password)
    try:
        cursor.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email.strip().lower(), pwd_hash)
        )
        conn.commit()
        user_id = cursor.lastrowid
        return user_id
    except sqlite3.IntegrityError:
        raise ValueError("A user with this email already exists.")
    finally:
        conn.close()

def verify_user(email: str, password: str) -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
    user = cursor.fetchone()
    conn.close()
    
    if user and verify_password(password, user["password_hash"]):
        return dict(user)
    return None

def get_user_by_id(user_id: int) -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, resume_text, resume_filename, api_keys_json FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def update_user_resume(user_id: int, resume_text: str, filename: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET resume_text = ?, resume_filename = ? WHERE id = ?",
        (resume_text, filename, user_id)
    )
    conn.commit()
    conn.close()

def update_user_api_keys(user_id: int, api_keys: dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET api_keys_json = ? WHERE id = ?",
        (json.dumps(api_keys), user_id)
    )
    conn.commit()
    conn.close()

def update_user_password(user_id: int, new_password: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    pwd_hash = hash_password(new_password)
    cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pwd_hash, user_id))
    conn.commit()
    conn.close()

# --- Applications operations ---
def add_application(user_id: int, job_id: str, title: str, company: str, url: str, fit_score: int, status: str, cover_letter: str, recruiter_email: dict, linkedin_note: str, tailored_resume: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    date_str = datetime.now().isoformat()
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
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM applications WHERE user_id = ? AND job_id = ?", (user_id, job_id))
    conn.commit()
    conn.close()

def delete_all_applications(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM applications WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
