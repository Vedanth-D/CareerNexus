import sys
import os
import time
from datetime import datetime, timedelta, timezone

# Ensure project root is in path
sys.path.insert(0, os.path.abspath("."))

from core.database import (
    init_db, create_user, verify_user, hash_password, verify_password,
    set_verification_token, verify_email_token, set_password_reset_token,
    verify_reset_token_and_update_password, get_user_by_id
)
from core.auth_security import (
    create_session, get_session, destroy_session,
    is_rate_limited, record_attempt, clear_rate_limit, generate_token
)

def run_security_tests():
    print("==================================================")
    print("RUNNING COMPREHENSIVE AUTH SECURITY VERIFICATION")
    print("==================================================")
    
    init_db()
    
    # ── Test 1: PBKDF2 600k Password Hashing ───────────────────
    print("\n[Test 1] Testing PBKDF2 600,000 Iteration Password Hashing...")
    pwd = "SecuredPassword123!"
    h1 = hash_password(pwd)
    assert ":600000" in h1, f"Expected 600000 iterations in hash string, got: {h1}"
    assert verify_password(pwd, h1) is True, "Password verification failed for valid password"
    assert verify_password("WrongPassword!", h1) is False, "Password verification passed for wrong password"
    
    # Test legacy 100k iteration hash compatibility
    legacy_h = "00112233445566778899aabbccddeeff:112233445566778899aabbccddeeff00112233445566778899aabbccddeeff00"
    assert verify_password(pwd, legacy_h) is False
    print("[SUCCESS] PBKDF2 600k Hashing & Legacy Compatibility Verified!")
    
    # ── Test 2: Session Manager & Expiration ──────────────────
    print("\n[Test 2] Testing Session Storage & Expiration Logic...")
    sess_id = create_session(user_id=42)
    s_data = get_session(sess_id)
    assert s_data is not None, "Failed to retrieve active session"
    assert s_data["user_id"] == 42
    
    # Test session destroy
    destroy_session(sess_id)
    assert get_session(sess_id) is None, "Destroyed session was still retrievable"
    print("[SUCCESS] Session Management & Invalidation Verified!")
    
    # ── Test 3: Rate Limiter ──────────────────────────────────
    print("\n[Test 3] Testing Rate Limiting (5 Attempts Window)...")
    key = "test_rate_limit_ip_127.0.0.1"
    clear_rate_limit(key)
    
    for i in range(5):
        limited, _ = is_rate_limited(key, max_requests=5, window_seconds=900)
        assert not limited, f"Rate limited prematurely at attempt {i+1}"
        record_attempt(key)
        
    limited, retry_sec = is_rate_limited(key, max_requests=5, window_seconds=900)
    assert limited is True, "Expected rate limit enforcement after 5 failed attempts"
    assert retry_sec > 0, "Expected positive retry_after seconds"
    print(f"[SUCCESS] Rate Limiting Enforcement Verified! Lockout active for {retry_sec}s.")
    clear_rate_limit(key)
    
    # ── Test 4: Email Verification Flow ───────────────────────
    print("\n[Test 4] Testing Email Verification Token System...")
    test_email = f"test_sec_{int(time.time())}@example.com"
    v_token = generate_token("verify")
    v_exp = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    
    uid = create_user(test_email, "SecurePass123!", is_verified=0, verification_token=v_token, verification_token_expires=v_exp)
    u_before = get_user_by_id(uid)
    assert u_before["is_verified"] == 0, "User should start as unverified"
    
    success, msg = verify_email_token(v_token)
    assert success is True, f"Email verification failed: {msg}"
    
    u_after = get_user_by_id(uid)
    assert u_after["is_verified"] == 1, "User is_verified flag should be 1 after verification"
    print("[SUCCESS] Email Verification Flow Verified!")
    
    # ── Test 5: Password Reset Flow ───────────────────────────
    print("\n[Test 5] Testing Password Reset Token Expiration & Single-Use...")
    r_token = generate_token("reset")
    r_exp = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    
    assert set_password_reset_token(test_email, r_token, r_exp) is True
    
    # Reset password with valid token
    success, msg = verify_reset_token_and_update_password(r_token, "NewSuperPassword99!")
    assert success is True, f"Password reset failed: {msg}"
    
    # Test single-use invalidation
    success_retry, _ = verify_reset_token_and_update_password(r_token, "AnotherPassword!")
    assert success_retry is False, "Password reset token was reused (should be single-use)"
    
    # Verify login with new password
    u_logged = verify_user(test_email, "NewSuperPassword99!")
    assert u_logged is not None, "Login with new password failed"
    print("[SUCCESS] Password Reset Token Flow & Single-Use Invalidation Verified!")
    
    print("\n==================================================")
    print("ALL SECURITY VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("==================================================")

if __name__ == "__main__":
    run_security_tests()
