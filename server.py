import asyncio
import json
import os
import io
import re
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, UploadFile, File, Form, Cookie, Depends, HTTPException, status, Response, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from core.auth_security import (
    create_session, get_session, destroy_session, cleanup_expired_sessions,
    is_rate_limited, record_attempt, clear_rate_limit, generate_token, is_suspicious_bot
)

from core.security_logger import log_auth_event, log_security_event, log_api_error
from core.input_validation import (
    sanitize_text,
    validate_and_sanitize_email,
    validate_password,
    validate_token,
    validate_job_id,
    validate_search_query,
    validate_uploaded_file,
    validate_json_field
)

load_dotenv()

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

def enforce_rate_limit(request: Request, rate_key: str, max_requests: int, window_seconds: int, check_bot: bool = False):
    """Enforces rate limiting and optionally blocks suspicious bot user-agents."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    ua = request.headers.get("user-agent", "")
    
    if check_bot and is_suspicious_bot(ua):
        log_security_event("SECURITY_BOT_BLOCKED", client_ip, detail=f"Blocked bot user-agent: {ua[:50]}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Automated scripts and scrapers are restricted from this endpoint."
        )
        
    limited, retry_after = is_rate_limited(rate_key, max_requests=max_requests, window_seconds=window_seconds)
    if limited:
        log_security_event("SECURITY_RATE_LIMIT_EXCEEDED", client_ip, detail=f"Rate limit triggered for {rate_key}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Please retry in {retry_after} seconds."
        )
    record_attempt(rate_key)

# ── SECURITY HEADERS & AUDIT MIDDLEWARE ────────────────────────
@app.middleware("http")
async def security_middleware(request: Request, call_next):
    response = await call_next(request)
    
    # Enforce OWASP Recommended Security Headers
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    # Audit log 5xx API errors
    if response.status_code >= 500:
        client_ip = request.client.host if request.client else "127.0.0.1"
        log_api_error(request.url.path, client_ip, response.status_code, "Internal Server Error")
        
    return response

@app.on_event("startup")
def on_startup():
    from core.database import init_db
    init_db()

# --- Auth Dependency ---
def get_current_user_id(session_id: str = Cookie(None)):
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalid or expired. Please sign in again."
        )
    clean_session_id = sanitize_text(session_id, max_length=128)
    session = get_session(clean_session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalid or expired. Please sign in again."
        )
    return session["user_id"]

# --- File Extraction Utilities ---
def extract_text_from_pdf(file_bytes: bytes) -> str:
    import fitz
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    return text.strip()

def extract_text_from_docx(file_bytes: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(file_bytes))
    return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])

# --- User Auth Router Endpoints ---
@app.post("/register")
async def register(request: Request, email: str = Form(...), password: str = Form(...)):
    client_ip = request.client.host if request.client else "127.0.0.1"
    rate_key = f"register:{client_ip}"
    
    limited, retry_after = is_rate_limited(rate_key, max_requests=5, window_seconds=900)
    if limited:
        log_security_event("SECURITY_RATE_LIMIT_EXCEEDED", client_ip, detail=f"Register rate limit for {rate_key}")
        return JSONResponse(
            content={"error": f"Too many registration attempts. Please retry in {retry_after} seconds."},
            status_code=429
        )
    
    clean_email = validate_and_sanitize_email(email)
    clean_password = validate_password(password)

    from core.database import create_user
    try:
        v_token = generate_token("verify")
        v_expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        user_id = create_user(clean_email, clean_password, is_verified=0, verification_token=v_token, verification_token_expires=v_expires)
        log_auth_event("AUTH_REGISTER", client_ip, email=clean_email, success=True, detail="New user registered")
        return {
            "success": True,
            "message": "Account created successfully! Please verify your email.",
            "verification_token": v_token
        }
    except ValueError as e:
        record_attempt(rate_key)
        log_auth_event("AUTH_REGISTER", client_ip, email=clean_email, success=False, detail=str(e))
        return JSONResponse(content={"error": str(e)}, status_code=400)
    except Exception as e:
        record_attempt(rate_key)
        log_auth_event("AUTH_REGISTER", client_ip, email=clean_email, success=False, detail=f"Error: {str(e)}")
        return JSONResponse(content={"error": f"Registration failed: {str(e)}"}, status_code=500)

@app.post("/login")
async def login(request: Request, response: Response, email: str = Form(...), password: str = Form(...)):
    clean_email = validate_and_sanitize_email(email)
    clean_password = validate_password(password)
    client_ip = request.client.host if request.client else "127.0.0.1"
    rate_key = f"login:{client_ip}:{clean_email}"
    
    limited, retry_after = is_rate_limited(rate_key, max_requests=5, window_seconds=900)
    if limited:
        log_security_event("SECURITY_RATE_LIMIT_EXCEEDED", client_ip, detail=f"Login rate limit locked for {clean_email}")
        return JSONResponse(
            content={"error": f"Too many failed login attempts. Account temporarily locked. Retry in {retry_after} seconds."},
            status_code=429
        )

    from core.database import verify_user
    user = verify_user(clean_email, clean_password)
    if not user:
        record_attempt(rate_key)
        log_auth_event("AUTH_LOGIN_FAILED", client_ip, email=clean_email, success=False, detail="Invalid credentials")
        return JSONResponse(content={"error": "Invalid email or password."}, status_code=400)
    
    clear_rate_limit(rate_key)
    session_id = create_session(user["id"])
    
    is_https = request.headers.get("x-forwarded-proto") == "https" or os.getenv("ENV") == "production" or os.getenv("SECURE_COOKIES") == "true"
    
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        max_age=86400,
        samesite="lax",
        secure=bool(is_https)
    )
    log_auth_event("AUTH_LOGIN_SUCCESS", client_ip, email=clean_email, success=True)
    return {
        "success": True,
        "email": user["email"],
        "is_verified": user.get("is_verified", 1)
    }

@app.post("/verify-email")
async def verify_email(token: str = Form(...)):
    clean_token = validate_token(token)
    from core.database import verify_email_token
    success, message = verify_email_token(clean_token)
    if not success:
        return JSONResponse(content={"error": message}, status_code=400)
    return {"success": True, "message": message}

@app.post("/forgot-password")
async def forgot_password(request: Request, email: str = Form(...)):
    clean_email = validate_and_sanitize_email(email)
    client_ip = request.client.host if request.client else "127.0.0.1"
    rate_key = f"forgot:{client_ip}"
    
    limited, retry_after = is_rate_limited(rate_key, max_requests=3, window_seconds=900)
    if limited:
        return JSONResponse(
            content={"error": f"Too many password reset requests. Retry in {retry_after} seconds."},
            status_code=429
        )

    record_attempt(rate_key)
    from core.database import set_password_reset_token
    r_token = generate_token("reset")
    r_expires = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    
    found = set_password_reset_token(clean_email, r_token, r_expires)
    
    res = {
        "success": True,
        "message": "If an account exists with this email, password reset instructions have been generated."
    }
    if found:
        res["reset_token"] = r_token
    return res

@app.post("/reset-password")
async def reset_password(request: Request, token: str = Form(...), new_password: str = Form(...)):
    client_ip = request.client.host if request.client else "127.0.0.1"
    rate_key = f"reset:{client_ip}"
    
    limited, retry_after = is_rate_limited(rate_key, max_requests=5, window_seconds=900)
    if limited:
        return JSONResponse(
            content={"error": f"Too many reset attempts. Retry in {retry_after} seconds."},
            status_code=429
        )

    clean_token = validate_token(token)
    clean_password = validate_password(new_password)

    from core.database import verify_reset_token_and_update_password
    success, message = verify_reset_token_and_update_password(clean_token, clean_password)
    if not success:
        record_attempt(rate_key)
        return JSONResponse(content={"error": message}, status_code=400)
    return {"success": True, "message": message}

@app.post("/logout")
async def logout(response: Response, session_id: str = Cookie(None)):
    if session_id:
        clean_session_id = sanitize_text(session_id, max_length=128)
        destroy_session(clean_session_id)
    response.delete_cookie(key="session_id", httponly=True, samesite="lax")
    return {"success": True}

@app.get("/me")
async def get_me(user_id: int = Depends(get_current_user_id)):
    from core.database import get_user_by_id
    user = get_user_by_id(user_id)
    if not user:
        return JSONResponse(content={"error": "User profile not found"}, status_code=404)
    
    try:
        raw_keys = json.loads(user.get("api_keys_json", "{}"))
    except Exception:
        raw_keys = {}

    def mask_val(val: str) -> str:
        if not val:
            return ""
        if len(val) <= 8:
            return "********"
        return val[:4] + "..." + val[-4:]

    masked_keys = {k: mask_val(v) for k, v in raw_keys.items()}

    return {
        "email": user["email"],
        "resume_filename": user["resume_filename"],
        "resume_text": user["resume_text"],
        "is_verified": user.get("is_verified", 1),
        "keys": masked_keys,
        "has_keys": {
            "groq": bool(raw_keys.get("groq_key")),
            "notion": bool(raw_keys.get("notion_key")),
            "adzuna": bool(raw_keys.get("adzuna_id"))
        }
    }

# --- Settings Endpoints ---
@app.post("/settings/update-password")
async def update_pwd(new_password: str = Form(...), user_id: int = Depends(get_current_user_id)):
    clean_password = validate_password(new_password)
    from core.database import update_user_password
    try:
        update_user_password(user_id, clean_password)
        return {"success": True, "message": "Password updated successfully!"}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)

@app.post("/settings/update-keys")
async def update_keys(
    groq_key: str = Form(""),
    notion_key: str = Form(""),
    notion_db: str = Form(""),
    adzuna_id: str = Form(""),
    adzuna_key: str = Form(""),
    user_id: int = Depends(get_current_user_id)
):
    from core.database import update_user_api_keys
    keys = {
        "groq_key": sanitize_text(groq_key, max_length=256),
        "notion_key": sanitize_text(notion_key, max_length=256),
        "notion_db": sanitize_text(notion_db, max_length=256),
        "adzuna_id": sanitize_text(adzuna_id, max_length=256),
        "adzuna_key": sanitize_text(adzuna_key, max_length=256)
    }
    try:
        update_user_api_keys(user_id, keys)
        return {"success": True, "message": "API keys saved to profile!"}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)

# --- Resume Upload ---
@app.post("/upload-resume")
async def upload_resume(file: UploadFile = File(...), user_id: int = Depends(get_current_user_id)):
    from core.database import update_user_resume
    contents = await file.read()
    
    # 1. Enforce unsafe file upload security controls (magic bytes, extension whitelist, path traversal, max size)
    safe_filename, ext = validate_uploaded_file(file, contents)

    try:
        if ext == ".pdf":
            text = extract_text_from_pdf(contents)
        elif ext == ".docx":
            text = extract_text_from_docx(contents)
        elif ext in (".txt", ".md"):
            text = contents.decode("utf-8")
        else:
            return JSONResponse(content={"error": "Upload PDF, DOCX, TXT or MD only."}, status_code=400)
            
        clean_text = sanitize_text(text, max_length=50000)
        if not clean_text or len(clean_text) < 30:
            return JSONResponse(content={"error": "Could not read text. Try a different file."}, status_code=400)
            
        # Update user profile in database
        update_user_resume(user_id, clean_text, safe_filename)
        return {"text": clean_text, "filename": safe_filename}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

# --- Main App Static page ---
@app.get("/", response_class=HTMLResponse)
async def home():
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()

# --- Campaigns Execution endpoint ---
@app.post("/run-agent")
async def run_agent(request: Request, query: str = Form(...), resume: str = Form(...), user_id: int = Depends(get_current_user_id)):
    enforce_rate_limit(request, f"ai_run:{user_id}", max_requests=10, window_seconds=600, check_bot=True)
    
    clean_query = validate_search_query(query, max_length=200)
    clean_resume = sanitize_text(resume, max_length=50000)
    
    from core.database import get_user_by_id, add_application
    user = get_user_by_id(user_id)
    
    # Load user's private API keys (custom Groq key)
    try:
        keys = json.loads(user["api_keys_json"])
    except Exception:
        keys = {}
    
    user_api_key = keys.get("groq_key")
    if not user_api_key:
        user_api_key = os.getenv("GROQ_API_KEY")

    async def generate():
        from agents.scraper import scraper_agent
        from agents.planner import planner_agent
        from agents.critic  import critic_agent
        from agents.writer  import writer_agent
        from core.state import AgentState

        state: AgentState = {
            "job_search_query": clean_query,
            "resume_profile":   clean_resume,
            "preferences":      {"remote": True},
            "listings":         [],
            "current_job":      None,
            "tailored_resume":  None,
            "cover_letter":     None,
            "applied_jobs":     [],
            "errors":           [],
            "status":           "starting"
        }

        def send(event, data):
            return f"data: {json.dumps({'event': event, 'data': data})}\n\n"

        yield send("stage", {"stage": "scraper", "message": "Searching LinkedIn, Internshala and Remotive..."})
        await asyncio.sleep(0.1)
        state = await asyncio.to_thread(scraper_agent, state)
        yield send("scraper_done", {
            "count": len(state["listings"]),
            "jobs":  [{"title": sanitize_text(j["title"]), "company": sanitize_text(j["company"])}
                      for j in state["listings"]]
        })

        if not state["listings"]:
            yield send("done", {"message": "No jobs found. Try a different search term.", "total_applied": 0})
            return

        yield send("stage", {"stage": "planner", "message": "AI scoring each job against your resume..."})
        await asyncio.sleep(0.1)
        state = await asyncio.to_thread(planner_agent, state, api_key=user_api_key)
        yield send("planner_done", {
            "jobs": [{
                "title":   sanitize_text(j["title"]),
                "company": sanitize_text(j["company"]),
                "url":     j["url"],
                "source":  sanitize_text(j.get("source", "")),
                "score":   j.get("fit_score", 0),
                "reason":  sanitize_text(j.get("fit_reason", ""))
            } for j in state["listings"]]
        })

        yield send("stage", {"stage": "critic", "message": "Selecting best matches..."})
        await asyncio.sleep(0.1)
        state = await asyncio.to_thread(critic_agent, state)
        approved = [j for j in state["listings"] if j.get("approved")]
        yield send("critic_done", {
            "approved_count": len(approved),
            "current_job": sanitize_text(state["current_job"]["title"]) if state["current_job"] else None
        })

        if state.get("current_job"):
            yield send("stage", {"stage": "writer",
                                  "message": "Writing outreach materials and tailoring resume..."})
            await asyncio.sleep(0.1)
            state = await asyncio.to_thread(writer_agent, state, api_key=user_api_key)
            yield send("writer_done", {
                "job_title":       sanitize_text(state["current_job"]["title"]),
                "company":         sanitize_text(state["current_job"]["company"]),
                "job_url":         state["current_job"].get("url", "#"),
                "cover_letter":    sanitize_text(state.get("cover_letter", "")),
                "tailored_resume": sanitize_text(state.get("tailored_resume", "")),
                "recruiter_email": state.get("recruiter_email", {}),
                "linkedin_note":    sanitize_text(state.get("linkedin_note", ""))
            })

            # Save campaign to database under user_id
            yield send("stage", {"stage": "tracker", "message": "Logging campaign to database..."})
            await asyncio.sleep(0.1)
            
            job = state["current_job"]
            try:
                await asyncio.to_thread(
                    add_application,
                    user_id=user_id,
                    job_id=job["id"],
                    title=sanitize_text(job["title"]),
                    company=sanitize_text(job["company"]),
                    url=job["url"],
                    fit_score=job.get("fit_score", 0),
                    status="Sent",
                    cover_letter=sanitize_text(state.get("cover_letter", "")),
                    recruiter_email=state.get("recruiter_email", {}),
                    linkedin_note=sanitize_text(state.get("linkedin_note", "")),
                    tailored_resume=sanitize_text(state.get("tailored_resume", ""))
                )
                
                # Check for Notion Sync in user keys
                notion_key = keys.get("notion_key")
                notion_db = keys.get("notion_db")
                if notion_key and notion_db:
                    try:
                        from notion_client import Client
                        from datetime import datetime
                        notion = Client(auth=notion_key)
                        notion.pages.create(
                            parent={"database_id": notion_db},
                            properties={
                                "Name":         {"title":  [{"text": {"content": job["title"]}}]},
                                "Company":      {"rich_text": [{"text": {"content": job["company"]}}]},
                                "URL":          {"url": job["url"]},
                                "Fit Score":    {"number": job.get("fit_score", 0)},
                                "Status":       {"select": {"name": "Applied"}},
                                "Date Applied": {"date": {"start": datetime.now().date().isoformat()}},
                            }
                        )
                    except Exception as e:
                        print(f"Notion sync failed: {e}")
            except Exception as e:
                print(f"Error logging application to SQLite: {e}")

            yield send("done", {
                "message":       "Campaign created and assets drafted successfully!",
                "total_applied": 1
            })
        else:
            yield send("done", {
                "message":       "No matching jobs found with score >= 50. Try another search query.",
                "total_applied": 0
            })

    return StreamingResponse(generate(), media_type="text/event-stream")

# --- ATS Scorer endpoint ---
@app.post("/analyze-ats")
async def analyze_ats(request: Request, resume: str = Form(...), jd: str = Form(...), user_id: int = Depends(get_current_user_id)):
    enforce_rate_limit(request, f"ai_ats:{user_id}", max_requests=10, window_seconds=600, check_bot=True)
    
    clean_resume = sanitize_text(resume, max_length=50000)
    clean_jd = sanitize_text(jd, max_length=50000)
    
    from agents.ats_agent import ats_agent
    from agents.writer import writer_agent
    from core.database import get_user_by_id
    
    user = get_user_by_id(user_id)
    try:
        keys = json.loads(user.get("api_keys_json", "{}"))
    except Exception:
        keys = {}
        
    user_api_key = keys.get("groq_key") or os.getenv("GROQ_API_KEY")

    report = ats_agent(clean_resume, clean_jd, api_key=user_api_key)

    # Get Tailored Resume
    mock_state = {
        "resume_profile": clean_resume,
        "current_job": {
            "title": "Target Role",
            "company": "Target Company",
            "description": clean_jd
        }
    }
    try:
        res_state = await asyncio.to_thread(writer_agent, mock_state, api_key=user_api_key)
        report["tailored_resume"] = res_state.get("tailored_resume", clean_resume)
    except Exception as e:
        report["tailored_resume"] = clean_resume

    return JSONResponse(content=report)

# --- Company Intelligence Research endpoint ---
@app.post("/company-research")
async def company_research(request: Request, company_name: str = Form(...), resume: str = Form(""), user_id: int = Depends(get_current_user_id)):
    enforce_rate_limit(request, f"ai_intel:{user_id}", max_requests=10, window_seconds=600, check_bot=True)
    
    clean_company = sanitize_text(company_name, max_length=100)
    clean_resume = sanitize_text(resume, max_length=50000)
    
    from agents.company_agent import company_agent
    from core.database import get_user_by_id
    
    user = get_user_by_id(user_id)
    try:
        keys = json.loads(user.get("api_keys_json", "{}"))
    except Exception:
        keys = {}
        
    user_api_key = keys.get("groq_key") or os.getenv("GROQ_API_KEY")

    try:
        report = await asyncio.to_thread(company_agent, clean_company, clean_resume, api_key=user_api_key)
        return JSONResponse(content=report)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

# --- AI Chat endpoint ---
@app.post("/chat")
async def chat(request: Request, message: str = Form(...), history: str = Form("[]"), resume: str = Form(""), jd: str = Form(""), user_id: int = Depends(get_current_user_id)):
    enforce_rate_limit(request, f"ai_chat:{user_id}", max_requests=20, window_seconds=300)
    
    clean_message = sanitize_text(message, max_length=2000)
    parsed_history = validate_json_field(history, max_length=50000)
    clean_resume = sanitize_text(resume, max_length=50000)
    clean_jd = sanitize_text(jd, max_length=50000)
    
    from agents.chat_agent import chat_agent
    from core.database import get_user_by_id
    
    user = get_user_by_id(user_id)
    try:
        keys = json.loads(user.get("api_keys_json", "{}"))
    except Exception:
        keys = {}
        
    user_api_key = keys.get("groq_key") or os.getenv("GROQ_API_KEY")

    if isinstance(parsed_history, list):
        history_list = [
            {"role": sanitize_text(item.get("role", "")), "content": sanitize_text(item.get("content", ""))}
            for item in parsed_history if isinstance(item, dict)
        ]
    else:
        history_list = []

    history_list.append({"role": "user", "content": clean_message})
    reply = await asyncio.to_thread(chat_agent, history_list, clean_resume, clean_jd, api_key=user_api_key)
    return JSONResponse(content={"reply": sanitize_text(reply)})

# --- Database application retrieval endpoints ---
@app.get("/applications")
async def get_user_apps(request: Request, user_id: int = Depends(get_current_user_id)):
    enforce_rate_limit(request, f"api_apps:{user_id}", max_requests=60, window_seconds=60, check_bot=True)
    from core.database import get_applications
    return get_applications(user_id)

@app.delete("/applications/{job_id}")
async def delete_user_app(job_id: str, user_id: int = Depends(get_current_user_id)):
    clean_job_id = validate_job_id(job_id)
    from core.database import delete_application
    try:
        deleted = delete_application(user_id, clean_job_id)
        if not deleted:
            return JSONResponse(content={"error": "Application not found or unauthorized access."}, status_code=404)
        return {"success": True}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.delete("/applications")
async def delete_all_user_apps(user_id: int = Depends(get_current_user_id)):
    from core.database import delete_all_applications
    try:
        delete_all_applications(user_id)
        return {"success": True}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

# --- Novel AI Endpoints ---
@app.post("/interview/generate-question")
async def interview_gen(request: Request, role: str = Form("Full Stack Developer"), q_type: str = Form("technical"), user_id: int = Depends(get_current_user_id)):
    enforce_rate_limit(request, f"ai_interview:{user_id}", max_requests=20, window_seconds=300)
    
    clean_role = sanitize_text(role, max_length=100)
    clean_type = sanitize_text(q_type, max_length=50)
    
    from agents.interview_agent import generate_interview_question
    from core.database import get_user_by_id
    user = get_user_by_id(user_id)
    keys = json.loads(user.get("api_keys_json", "{}")) if user else {}
    user_api_key = keys.get("groq_key") or os.getenv("GROQ_API_KEY")
    resume = user.get("resume_text", "") if user else ""

    res = await asyncio.to_thread(generate_interview_question, clean_role, resume, clean_type, api_key=user_api_key)
    return JSONResponse(content=res)

@app.post("/interview/feedback")
async def interview_feedback(request: Request, role: str = Form(...), question: str = Form(...), response_text: str = Form(...), user_id: int = Depends(get_current_user_id)):
    enforce_rate_limit(request, f"ai_interview_fb:{user_id}", max_requests=20, window_seconds=300)
    
    clean_role = sanitize_text(role, max_length=100)
    clean_question = sanitize_text(question, max_length=1000)
    clean_response = sanitize_text(response_text, max_length=5000)
    
    from agents.interview_agent import evaluate_interview_response
    from core.database import get_user_by_id
    user = get_user_by_id(user_id)
    keys = json.loads(user.get("api_keys_json", "{}")) if user else {}
    user_api_key = keys.get("groq_key") or os.getenv("GROQ_API_KEY")
    resume = user.get("resume_text", "") if user else ""

    res = await asyncio.to_thread(evaluate_interview_response, clean_role, clean_question, clean_response, resume, api_key=user_api_key)
    return JSONResponse(content=res)

@app.post("/heatmap/analyze")
async def heatmap_analyze(request: Request, roles_json: str = Form("[]"), user_id: int = Depends(get_current_user_id)):
    enforce_rate_limit(request, f"ai_heatmap:{user_id}", max_requests=10, window_seconds=600, check_bot=True)
    
    parsed_roles = validate_json_field(roles_json, max_length=50000)
    if isinstance(parsed_roles, list):
        jds = [sanitize_text(str(item), max_length=10000) for item in parsed_roles]
    else:
        jds = []

    from agents.heatmap_agent import generate_skill_heatmap
    from core.database import get_user_by_id
    user = get_user_by_id(user_id)
    keys = json.loads(user.get("api_keys_json", "{}")) if user else {}
    user_api_key = keys.get("groq_key") or os.getenv("GROQ_API_KEY")
    resume = user.get("resume_text", "") if user else ""

    res = await asyncio.to_thread(generate_skill_heatmap, resume, jds, api_key=user_api_key)
    return JSONResponse(content=res)

@app.post("/bullet/rewrite")
async def bullet_rewrite(request: Request, bullet: str = Form(...), role: str = Form(""), tone: str = Form("Executive"), user_id: int = Depends(get_current_user_id)):
    enforce_rate_limit(request, f"ai_bullet:{user_id}", max_requests=20, window_seconds=300)
    
    clean_bullet = sanitize_text(bullet, max_length=1000)
    clean_role = sanitize_text(role, max_length=100)
    clean_tone = sanitize_text(tone, max_length=50)
    
    from agents.bullet_agent import rewrite_bullet_point
    from core.database import get_user_by_id
    user = get_user_by_id(user_id)
    keys = json.loads(user.get("api_keys_json", "{}")) if user else {}
    user_api_key = keys.get("groq_key") or os.getenv("GROQ_API_KEY")

    res = await asyncio.to_thread(rewrite_bullet_point, clean_bullet, clean_role, clean_tone, api_key=user_api_key)
    return JSONResponse(content=res)