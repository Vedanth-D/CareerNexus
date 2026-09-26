import time
import secrets
from typing import Dict, Optional, Tuple
from collections import defaultdict

# ── 1. SESSION MANAGEMENT ─────────────────────────────────────
# Session TTL: 24 Hours (86400 seconds)
SESSION_TTL_SECONDS = 86400

# SESSIONS store: session_id -> {"user_id": int, "created_at": float, "expires_at": float}
_SESSIONS: Dict[str, dict] = {}

def create_session(user_id: int) -> str:
    """Generates a cryptographically secure 256-bit session ID and registers session with 24h TTL."""
    session_id = secrets.token_hex(32)
    now = time.time()
    _SESSIONS[session_id] = {
        "user_id": user_id,
        "created_at": now,
        "expires_at": now + SESSION_TTL_SECONDS
    }
    return session_id

def get_session(session_id: str) -> Optional[dict]:
    """Retrieves session if valid and unexpired; applies sliding expiration window."""
    if not session_id or session_id not in _SESSIONS:
        return None
    
    session = _SESSIONS[session_id]
    now = time.time()
    
    if now > session["expires_at"]:
        # Session expired - remove and invalidate
        del _SESSIONS[session_id]
        return None
    
    # Sliding expiration: extend TTL if more than half elapsed
    if (session["expires_at"] - now) < (SESSION_TTL_SECONDS / 2):
        session["expires_at"] = now + SESSION_TTL_SECONDS
        
    return session

def destroy_session(session_id: str) -> bool:
    """Invalidates and deletes session token."""
    if session_id in _SESSIONS:
        del _SESSIONS[session_id]
        return True
    return False

def cleanup_expired_sessions():
    """Purges all stale or expired sessions from memory."""
    now = time.time()
    expired = [sid for sid, sess in _SESSIONS.items() if now > sess["expires_at"]]
    for sid in expired:
        del _SESSIONS[sid]


# ── 2. SLIDING WINDOW RATE LIMITER ────────────────────────────
# Default: Max 5 failed attempts per 15 minutes (900 seconds)
_RATE_LIMIT_STORE: Dict[str, list] = defaultdict(list)

def is_rate_limited(key: str, max_requests: int = 5, window_seconds: int = 900) -> Tuple[bool, int]:
    """
    Checks if a key (e.g. 'login:127.0.0.1' or 'login:user@example.com') exceeds rate limit.
    Returns (is_limited: bool, retry_after_seconds: int).
    """
    now = time.time()
    cutoff = now - window_seconds
    
    # Prune old timestamps outside time window
    timestamps = [t for t in _RATE_LIMIT_STORE[key] if t > cutoff]
    _RATE_LIMIT_STORE[key] = timestamps
    
    if len(timestamps) >= max_requests:
        oldest_attempt = timestamps[0]
        retry_after = int(oldest_attempt + window_seconds - now)
        return True, max(1, retry_after)
    
    return False, 0

def record_attempt(key: str):
    """Records an attempt timestamp for rate limiting."""
    _RATE_LIMIT_STORE[key].append(time.time())

def clear_rate_limit(key: str):
    """Clears recorded attempts upon successful authentication."""
    if key in _RATE_LIMIT_STORE:
        del _RATE_LIMIT_STORE[key]


# ── 3. CRYPTOGRAPHIC TOKEN & BOT PROTECTION ───────────────────
SUSPICIOUS_BOT_USER_AGENTS = [
    "curl", "python-requests", "python-urllib", "httpx", "aiohttp",
    "guzzle", "scrapy", "wget", "go-http-client", "headlesschrome",
    "phantomjs", "selenium"
]

def is_suspicious_bot(user_agent: str) -> bool:
    """Detects raw script user-agents or headless automated scraper tools."""
    if not user_agent or len(user_agent.strip()) < 5:
        return True
    ua_lower = user_agent.lower()
    return any(bot in ua_lower for bot in SUSPICIOUS_BOT_USER_AGENTS)

def generate_token(prefix: str = "") -> str:
    """Generates a secure random 64-char hex token for email verification or password reset."""
    raw_token = secrets.token_hex(32)
    return f"{prefix}_{raw_token}" if prefix else raw_token
