import re
import os
import io
import json
from typing import Tuple, Union, List, Dict, Optional
from fastapi import HTTPException, status, UploadFile

# ── 1. TEXT SANITIZATION & SCRIPT INJECTION (XSS) PREVENTION ──
DANGEROUS_PATTERNS = [
    re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL),
    re.compile(r'javascript\s*:', re.IGNORECASE),
    re.compile(r'vbscript\s*:', re.IGNORECASE),
    re.compile(r'data\s*:\s*text/html', re.IGNORECASE),
    re.compile(r'on\w+\s*=', re.IGNORECASE),  # onload=, onerror=, etc.
    re.compile(r'<iframe[^>]*>.*?</iframe>', re.IGNORECASE | re.DOTALL),
    re.compile(r'<object[^>]*>.*?</object>', re.IGNORECASE | re.DOTALL),
    re.compile(r'<embed[^>]*>.*?</embed>', re.IGNORECASE | re.DOTALL),
]

def sanitize_text(text: Optional[str], max_length: Optional[int] = None) -> str:
    """
    Sanitizes string input to prevent script injection (XSS) and null-byte injection.
    Enforces strict string type and optional length bounds.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid input type. Expected string."
        )
    
    # Strip null bytes
    cleaned = text.replace('\x00', '')
    
    # Neutralize dangerous script tags and inline handlers
    for pattern in DANGEROUS_PATTERNS:
        cleaned = pattern.sub('', cleaned)
        
    # Strip dangerous HTML tags (<script>, <iframe>, etc.)
    cleaned = re.sub(r'</?(?:script|iframe|object|embed|style|applet|meta|link)[^>]*>', '', cleaned, flags=re.IGNORECASE)
    
    if max_length and len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
        
    return cleaned.strip()

# ── 2. EMAIL VALIDATION & SANITIZATION ──
EMAIL_REGEX = re.compile(r'^(?!.*\.\.)[a-zA-Z0-9._%+-]+@[a-zA-Z0-9]+(?:\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,63}$')

def validate_and_sanitize_email(email: str) -> str:
    """
    Strictly validates and sanitizes email input.
    Rejects invalid emails, missing emails, or oversized payload strings.
    """
    if not isinstance(email, str):
        raise HTTPException(status_code=400, detail="Email must be a valid string.")
    
    clean_email = email.strip().lower()
    clean_email = clean_email.replace('\x00', '')
    
    if len(clean_email) > 254:
        raise HTTPException(status_code=400, detail="Email exceeds maximum allowed length of 254 characters.")
        
    if not EMAIL_REGEX.match(clean_email):
        raise HTTPException(status_code=400, detail="Invalid email format. Please provide a valid email address.")
        
    return clean_email

# ── 3. PASSWORD VALIDATION ──
def validate_password(password: str, min_length: int = 6, max_length: int = 128) -> str:
    """
    Validates password length and structure.
    Enforces max length of 128 bytes to prevent Hash-DoS against PBKDF2 hashing.
    """
    if not isinstance(password, str):
        raise HTTPException(status_code=400, detail="Password must be a string.")
        
    if '\x00' in password:
        raise HTTPException(status_code=400, detail="Password contains invalid characters.")
        
    if len(password) < min_length:
        raise HTTPException(status_code=400, detail=f"Password must be at least {min_length} characters long.")
        
    if len(password) > max_length:
        raise HTTPException(status_code=400, detail=f"Password exceeds maximum allowed length of {max_length} characters.")
        
    return password

# ── 4. TOKEN VALIDATION (Verification / Reset Tokens) ──
TOKEN_REGEX = re.compile(r'^[a-fA-F0-9\-_]{16,128}$')

def validate_token(token: str) -> str:
    """
    Validates security tokens against hexadecimal/alphanumeric regex.
    Prevents NoSQL/SQL injection via token parameters.
    """
    if not isinstance(token, str):
        raise HTTPException(status_code=400, detail="Token must be a string.")
        
    clean_token = token.strip()
    if not TOKEN_REGEX.match(clean_token):
        raise HTTPException(status_code=400, detail="Invalid token format.")
        
    return clean_token

# ── 5. JOB ID VALIDATION ──
JOB_ID_REGEX = re.compile(r'^[a-zA-Z0-9_\-:]{1,128}$')

def validate_job_id(job_id: str) -> str:
    """
    Validates application job_id path/parameter to prevent path traversal and injection.
    """
    if not isinstance(job_id, str):
        raise HTTPException(status_code=400, detail="job_id must be a string.")
        
    clean_id = job_id.strip()
    if not JOB_ID_REGEX.match(clean_id) or ".." in clean_id or "/" in clean_id or "\\" in clean_id:
        raise HTTPException(status_code=400, detail="Invalid job_id parameter.")
        
    return clean_id

# ── 6. COMMAND & QUERY INJECTION SANITIZATION ──
DANGEROUS_COMMAND_CHARS = re.compile(r'[;&|`$><]')

def validate_search_query(query: str, max_length: int = 200) -> str:
    """
    Validates job search query strings, filtering command injection symbols and script tags.
    """
    if not isinstance(query, str):
        raise HTTPException(status_code=400, detail="Query must be a string.")
        
    clean_query = sanitize_text(query, max_length=max_length)
    if not clean_query:
        raise HTTPException(status_code=400, detail="Search query cannot be empty.")
        
    # Strip command injection characters
    clean_query = DANGEROUS_COMMAND_CHARS.sub('', clean_query)
    return clean_query.strip()

# ── 7. UNSAFE FILE UPLOAD VALIDATION ──
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.txt', '.md'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB Max Limit

def validate_uploaded_file(file: UploadFile, contents: bytes) -> Tuple[str, str]:
    """
    Strictly validates uploaded files to prevent unsafe file uploads:
    - Path traversal prevention via filename sanitization
    - File size limits (5MB)
    - File extension whitelist (.pdf, .docx, .txt, .md)
    - Magic byte / content verification
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a valid filename.")
        
    # 1. Prevent Directory Traversal in filename
    raw_name = os.path.basename(file.filename)
    safe_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', raw_name)
    _, ext = os.path.splitext(safe_name.lower())
    
    # 2. Extension Whitelist Check
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{ext}'. Only PDF, DOCX, TXT, and MD files are allowed."
        )
        
    # 3. File Size Check
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File size exceeds maximum limit of 5MB (Received {len(contents) / (1024*1024):.2f}MB)."
        )
        
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # 4. Content Magic Byte Verification
    if ext == '.pdf':
        if not contents.startswith(b'%PDF-'):
            raise HTTPException(status_code=400, detail="File extension is .pdf but binary signature is invalid.")
    elif ext == '.docx':
        if not contents.startswith(b'PK\x03\x04'):
            raise HTTPException(status_code=400, detail="File extension is .docx but binary signature is invalid.")
    elif ext in ('.txt', '.md'):
        try:
            # Validate valid UTF-8 encoding and reject binary files pretending to be text
            decoded = contents.decode('utf-8')
            if '\x00' in decoded:
                raise HTTPException(status_code=400, detail="Text file contains binary or null characters.")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Text file is not valid UTF-8 text.")

    return safe_name, ext

# ── 8. JSON STRUCTURE & PARSING VALIDATION ──
def validate_json_field(json_str: str, max_length: int = 50000) -> Union[dict, list]:
    """
    Safely parses JSON strings, enforcing max payload size and catch decode errors.
    """
    if not isinstance(json_str, str):
        raise HTTPException(status_code=400, detail="JSON field must be a string.")
        
    if len(json_str) > max_length:
        raise HTTPException(status_code=400, detail="JSON payload exceeds maximum allowed size.")
        
    try:
        data = json.loads(json_str)
        return data
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON format.")
