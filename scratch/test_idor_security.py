import sys
import os
import time

sys.path.insert(0, os.path.abspath("."))

from core.database import (
    init_db, create_user, add_application, get_applications,
    delete_application, update_user_resume, update_user_api_keys, get_user_by_id
)

def run_idor_tests():
    print("==================================================")
    print("RUNNING IDOR & RESOURCE OWNERSHIP AUDIT TESTS")
    print("==================================================")
    
    init_db()
    
    # ── Setup 2 Distinct Users ─────────────────────────────────
    ts = int(time.time())
    user_a_email = f"alice_idor_{ts}@example.com"
    user_b_email = f"bob_idor_{ts}@example.com"
    
    user_a_id = create_user(user_a_email, "AlicePassword123!", is_verified=1)
    user_b_id = create_user(user_b_email, "BobPassword123!", is_verified=1)
    
    print(f"[Setup] Created User A (ID={user_a_id}) and User B (ID={user_b_id})")
    
    # ── Test 1: Cross-User Application Isolation ───────────────
    print("\n[Test 1] Testing Data Isolation for Application Records...")
    add_application(
        user_id=user_a_id,
        job_id="job_alice_001",
        title="Backend Engineer",
        company="Stripe",
        url="https://example.com/stripe",
        fit_score=92,
        status="Sent",
        cover_letter="Alice's Cover Letter",
        recruiter_email={},
        linkedin_note="",
        tailored_resume="Alice's Tailored Resume"
    )
    
    apps_a = get_applications(user_a_id)
    apps_b = get_applications(user_b_id)
    
    assert any(a["job_id"] == "job_alice_001" for a in apps_a), "User A should see their own application"
    assert not any(b["job_id"] == "job_alice_001" for b in apps_b), "User B must NOT see User A's application"
    print("[SUCCESS] Application records are strictly isolated by user_id!")
    
    # ── Test 2: Unauthorized Cross-User Deletion Lockout ────────
    print("\n[Test 2] Testing IDOR Deletion Prevention...")
    # User B attempts to delete User A's application ('job_alice_001')
    deleted_by_b = delete_application(user_b_id, "job_alice_001")
    assert deleted_by_b is False, "User B should NOT be able to delete User A's application!"
    
    # Verify User A's application is still intact
    apps_a_after = get_applications(user_a_id)
    assert any(a["job_id"] == "job_alice_001" for a in apps_a_after), "User A's application was deleted by User B!"
    print("[SUCCESS] IDOR Deletion Lockout Verified! Unauthorized deletion returned False.")
    
    # Authorized deletion by User A
    deleted_by_a = delete_application(user_a_id, "job_alice_001")
    assert deleted_by_a is True, "User A should be able to delete their own application"
    print("[SUCCESS] Authorized deletion by owner succeeded.")
    
    # ── Test 3: Multi-User Coexistence for Same Job ID ──────────
    print("\n[Test 3] Testing Composite Unique Constraint (user_id, job_id)...")
    common_job_id = "job_shared_999"
    
    add_application(user_a_id, common_job_id, "AI Developer", "OpenAI", "https://example.com/openai", 88, "Sent", "", {}, "", "")
    add_application(user_b_id, common_job_id, "AI Developer", "OpenAI", "https://example.com/openai", 95, "Draft", "", {}, "", "")
    
    apps_a_shared = get_applications(user_a_id)
    apps_b_shared = get_applications(user_b_id)
    
    item_a = next(a for a in apps_a_shared if a["job_id"] == common_job_id)
    item_b = next(b for b in apps_b_shared if b["job_id"] == common_job_id)
    
    assert item_a["fit_score"] == 88, "User A's data was overwritten!"
    assert item_b["fit_score"] == 95, "User B's data was overwritten!"
    print("[SUCCESS] Composite unique constraint allows multi-user coexistence without data collision!")
    
    # ── Test 4: Profile & Resume Data Isolation ───────────────
    print("\n[Test 4] Testing User Profile & Resume Data Isolation...")
    update_user_resume(user_a_id, "Alice's Secret Resume Content", "alice_resume.pdf")
    update_user_resume(user_b_id, "Bob's Resume Content", "bob_resume.pdf")
    
    profile_a = get_user_by_id(user_a_id)
    profile_b = get_user_by_id(user_b_id)
    
    assert profile_a["resume_text"] == "Alice's Secret Resume Content"
    assert profile_b["resume_text"] == "Bob's Resume Content"
    assert profile_a["resume_text"] != profile_b["resume_text"]
    print("[SUCCESS] Resume and profile data strictly isolated by user_id!")
    
    print("\n==================================================")
    print("ALL IDOR & OWNERSHIP VERIFICATION TESTS PASSED!")
    print("==================================================")

if __name__ == "__main__":
    run_idor_tests()
