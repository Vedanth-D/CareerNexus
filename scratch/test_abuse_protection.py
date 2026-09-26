import sys
import os
from unittest.mock import patch
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath("."))
import agents.ats_agent
import agents.writer
import agents.chat_agent
from server import app
from core.auth_security import create_session, clear_rate_limit

client = TestClient(app)

def run_abuse_protection_tests():
    print("==================================================")
    print("RUNNING ABUSE PROTECTION & BOT THROTTLING TESTS")
    print("==================================================")
    
    # Setup test session
    user_id = 999
    session_id = create_session(user_id)
    headers = {"Cookie": f"session_id={session_id}", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Browser"}
    
    # Mock LLM heavy functions for instant rate limit testing
    with patch("agents.ats_agent.ats_agent", return_value={"score": 85}), \
         patch("agents.writer.writer_agent", return_value={"tailored_resume": "Mock"}), \
         patch("agents.chat_agent.chat_agent", return_value="Mock response"):

        # ── Test 1: Heavy AI Endpoint Rate Limiting ────────────────
        print("\n[Test 1] Testing Heavy AI Rate Limiting (10 requests window)...")
        rate_key = f"ai_ats:{user_id}"
        clear_rate_limit(rate_key)
        
        for i in range(10):
            res = client.post(
                "/analyze-ats",
                data={"resume": "Software engineer with python experience.", "jd": "Looking for python developer."},
                headers=headers
            )
            assert res.status_code == 200, f"Request {i+1} failed with status {res.status_code}"
            
        # 11th Request must be blocked with HTTP 429
        blocked_res = client.post(
            "/analyze-ats",
            data={"resume": "Software engineer with python experience.", "jd": "Looking for python developer."},
            headers=headers
        )
        assert blocked_res.status_code == 429, f"Expected HTTP 429 Too Many Requests, got {blocked_res.status_code}"
        print("[SUCCESS] Heavy AI generation endpoint rate limiting enforced! (HTTP 429)")
        clear_rate_limit(rate_key)
        
        # ── Test 2: Interactive AI Chat Rate Limiting ──────────────
        print("\n[Test 2] Testing Interactive AI Rate Limiting (20 requests window)...")
        chat_key = f"ai_chat:{user_id}"
        clear_rate_limit(chat_key)
        
        for i in range(20):
            res = client.post(
                "/chat",
                data={"message": "Hello AI", "history": "[]"},
                headers=headers
            )
            assert res.status_code == 200
            
        # 21st Request must be blocked with HTTP 429
        blocked_chat = client.post(
            "/chat",
            data={"message": "Hello AI", "history": "[]"},
            headers=headers
        )
        assert blocked_chat.status_code == 429, f"Expected HTTP 429 for chat, got {blocked_chat.status_code}"
        print("[SUCCESS] Interactive AI Chat rate limiting enforced! (HTTP 429)")
        clear_rate_limit(chat_key)
        
        # ── Test 3: Automated Bot / Scraper Detection ──────────────
        print("\n[Test 3] Testing Automated Bot & Headless Scraper Filter...")
        bot_headers = {
            "Cookie": f"session_id={session_id}",
            "User-Agent": "python-requests/2.28.1"
        }
        
        bot_res = client.post(
            "/heatmap/analyze",
            data={"roles_json": "[]"},
            headers=bot_headers
        )
        assert bot_res.status_code == 403, f"Expected HTTP 403 Forbidden for bot user-agent, got {bot_res.status_code}"
        assert "Automated scripts" in bot_res.text
        print("[SUCCESS] Automated Bot & Headless Scraper blocked! (HTTP 403)")
        
    print("\n==================================================")
    print("ALL ABUSE PROTECTION & BOT TESTS PASSED!")
    print("==================================================")

if __name__ == "__main__":
    run_abuse_protection_tests()
