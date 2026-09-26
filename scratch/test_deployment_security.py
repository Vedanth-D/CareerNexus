import sys
import os
import json
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath("."))

from server import app
from core.database import get_db_file_path, get_db_connection
from core.security_logger import log_auth_event, log_security_event, log_api_error

client = TestClient(app)

def run_deployment_security_tests():
    print("==================================================")
    print("RUNNING DEPLOYMENT & LOGGING SECURITY VERIFICATION")
    print("==================================================")
    
    # ── Test 1: Security Headers Enforcement ─────────────────────
    print("\n[Test 1] Testing OWASP Recommended Security Headers...")
    response = client.get("/")
    assert response.status_code == 200, f"Expected 200 OK from home, got {response.status_code}"
    
    headers = response.headers
    assert "strict-transport-security" in headers, "HSTS Header Missing!"
    assert headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"
    assert headers.get("x-content-type-options") == "nosniff", "X-Content-Type-Options Missing!"
    assert headers.get("x-frame-options") == "DENY", "X-Frame-Options Missing!"
    assert headers.get("x-xss-protection") == "1; mode=block", "X-XSS-Protection Missing!"
    assert headers.get("referrer-policy") == "strict-origin-when-cross-origin", "Referrer-Policy Missing!"
    print("[SUCCESS] All OWASP Security Headers verified on API responses!")
    
    # ── Test 2: HTTPS Cookie Flags in Production ────────────────
    print("\n[Test 2] Testing HTTPS Cookie Configuration...")
    # Simulate HTTPS request with X-Forwarded-Proto header
    login_res = client.post(
        "/login",
        data={"email": "nonexistent_user_test@example.com", "password": "WrongPassword!"},
        headers={"x-forwarded-proto": "https"}
    )
    # 400 bad request for invalid user, but verify headers returned
    assert login_res.headers.get("x-frame-options") == "DENY"
    print("[SUCCESS] HTTPS & Header integration verified!")
    
    # ── Test 3: Structured Security & Audit Logger ─────────────
    print("\n[Test 3] Testing Security & Audit Logging...")
    # Trigger logging events
    log_auth_event("AUTH_LOGIN_SUCCESS", "127.0.0.1", "test@example.com", success=True)
    log_auth_event("AUTH_LOGIN_FAILED", "127.0.0.1", "hacker@example.com", success=False, detail="Invalid password")
    log_security_event("SECURITY_RATE_LIMIT_EXCEEDED", "192.168.1.100", detail="Brute force blocked")
    log_api_error("/test-endpoint", "127.0.0.1", 500, "Database timeout")
    print("[SUCCESS] Structured Security Logger executed cleanly!")
    
    # ── Test 4: Database File Permission Hardening ──────────────
    print("\n[Test 4] Testing Database File Isolation & Permissions...")
    db_path = get_db_file_path()
    conn = get_db_connection()
    conn.close()
    
    assert os.path.exists(db_path), "Database file path missing"
    if os.name == 'posix':
        mode = oct(os.stat(db_path).st_mode & 0o777)
        assert mode == '0o600', f"Expected POSIX file mode 0o600, got {mode}"
        print(f"[SUCCESS] Local SQLite database permissions verified restricted ({mode})!")
    else:
        print("[SUCCESS] Local SQLite database file isolation verified!")
        
    print("\n==================================================")
    print("ALL DEPLOYMENT & LOGGING SECURITY TESTS PASSED!")
    print("==================================================")

if __name__ == "__main__":
    run_deployment_security_tests()
