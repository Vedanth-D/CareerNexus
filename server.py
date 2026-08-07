import asyncio
import json
import os
import io
import re
import secrets
from fastapi import FastAPI, UploadFile, File, Form, Cookie, Depends, HTTPException, status, Response
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# In-memory session store (session_id -> user_id)
SESSIONS = {}

@app.on_event("startup")
def on_startup():
    from core.database import init_db
    init_db()

# --- Auth Dependency ---
def get_current_user_id(session_id: str = Cookie(None)):
    if not session_id or session_id not in SESSIONS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    return SESSIONS[session_id]

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
async def register(email: str = Form(...), password: str = Form(...)):
    from core.database import create_user
    try:
        user_id = create_user(email, password)
        return {"success": True, "message": "Account created successfully!"}
    except ValueError as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse(content={"error": f"Registration failed: {str(e)}"}, status_code=500)

@app.post("/login")
async def login(response: Response, email: str = Form(...), password: str = Form(...)):
    from core.database import verify_user
    user = verify_user(email, password)
    if not user:
        return JSONResponse(content={"error": "Invalid email or password."}, status_code=400)
    
    session_id = secrets.token_hex(16)
    SESSIONS[session_id] = user["id"]
    response.set_cookie(key="session_id", value=session_id, httponly=True, secure=False)
    return {"success": True, "email": user["email"]}

@app.post("/logout")
async def logout(response: Response, session_id: str = Cookie(None)):
    if session_id in SESSIONS:
        del SESSIONS[session_id]
    response.delete_cookie("session_id")
    return {"success": True}

@app.get("/me")
async def get_me(user_id: int = Depends(get_current_user_id)):
    from core.database import get_user_by_id
    user = get_user_by_id(user_id)
    if not user:
        return JSONResponse(content={"error": "User profile not found"}, status_code=404)
    
    try:
        keys = json.loads(user.get("api_keys_json", "{}"))
    except Exception:
        keys = {}

    return {
        "email": user["email"],
        "resume_filename": user["resume_filename"],
        "resume_text": user["resume_text"],
        "keys": keys
    }

# --- Settings Endpoints ---
@app.post("/settings/update-password")
async def update_pwd(new_password: str = Form(...), user_id: int = Depends(get_current_user_id)):
    from core.database import update_user_password
    try:
        update_user_password(user_id, new_password)
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
        "groq_key": groq_key.strip(),
        "notion_key": notion_key.strip(),
        "notion_db": notion_db.strip(),
        "adzuna_id": adzuna_id.strip(),
        "adzuna_key": adzuna_key.strip()
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
    filename = file.filename.lower()
    try:
        if filename.endswith(".pdf"):
            text = extract_text_from_pdf(contents)
        elif filename.endswith(".docx"):
            text = extract_text_from_docx(contents)
        elif filename.endswith(".txt") or filename.endswith(".md"):
            text = contents.decode("utf-8")
        else:
            return JSONResponse(content={"error": "Upload PDF, DOCX or TXT only."}, status_code=400)
            
        if not text or len(text) < 30:
            return JSONResponse(content={"error": "Could not read text. Try a different file."}, status_code=400)
            
        # Update user profile in SQLite
        update_user_resume(user_id, text, file.filename)
        return {"text": text, "filename": file.filename}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

# --- Main App Static page ---
@app.get("/", response_class=HTMLResponse)
async def home():
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()

# --- Campaigns Execution endpoint ---
@app.post("/run-agent")
async def run_agent(query: str = Form(...), resume: str = Form(...), user_id: int = Depends(get_current_user_id)):
    from core.database import get_user_by_id, add_application
    user = get_user_by_id(user_id)
    
    # Load user's private API keys (custom Groq key)
    try:
        keys = json.loads(user["api_keys_json"])
    except Exception:
        keys = {}
    
    user_api_key = keys.get("groq_key")
    if not user_api_key:
        user_api_key = os.getenv("GROQ_API_KEY") # Fallback to server's default

    async def generate():
        from agents.scraper import scraper_agent
        from agents.planner import planner_agent
        from agents.critic  import critic_agent
        from agents.writer  import writer_agent
        from core.state import AgentState

        state: AgentState = {
            "job_search_query": query,
            "resume_profile":   resume,
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
            "jobs":  [{"title": j["title"], "company": j["company"]}
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
                "title":   j["title"],
                "company": j["company"],
                "url":     j["url"],
                "source":  j.get("source", ""),
                "score":   j.get("fit_score", 0),
                "reason":  j.get("fit_reason", "")
            } for j in state["listings"]]
        })

        yield send("stage", {"stage": "critic", "message": "Selecting best matches..."})
        await asyncio.sleep(0.1)
        state = await asyncio.to_thread(critic_agent, state)
        approved = [j for j in state["listings"] if j.get("approved")]
        yield send("critic_done", {
            "approved_count": len(approved),
            "current_job": state["current_job"]["title"] if state["current_job"] else None
        })

        if state.get("current_job"):
            yield send("stage", {"stage": "writer",
                                  "message": "Writing outreach materials and tailoring resume..."})
            await asyncio.sleep(0.1)
            state = await asyncio.to_thread(writer_agent, state, api_key=user_api_key)
            yield send("writer_done", {
                "job_title":       state["current_job"]["title"],
                "company":         state["current_job"]["company"],
                "job_url":         state["current_job"].get("url", "#"),
                "cover_letter":    state.get("cover_letter", ""),
                "tailored_resume": state.get("tailored_resume", ""),
                "recruiter_email": state.get("recruiter_email", {}),
                "linkedin_note":    state.get("linkedin_note", "")
            })

            # Save the campaign directly to SQLite under user_id
            yield send("stage", {"stage": "tracker", "message": "Logging campaign to database..."})
            await asyncio.sleep(0.1)
            
            job = state["current_job"]
            try:
                await asyncio.to_thread(
                    add_application,
                    user_id=user_id,
                    job_id=job["id"],
                    title=job["title"],
                    company=job["company"],
                    url=job["url"],
                    fit_score=job.get("fit_score", 0),
                    status="Sent",
                    cover_letter=state.get("cover_letter", ""),
                    recruiter_email=state.get("recruiter_email", {}),
                    linkedin_note=state.get("linkedin_note", ""),
                    tailored_resume=state.get("tailored_resume", "")
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
                        print("Synced campaign to user Notion Database")
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
async def analyze_ats(resume: str = Form(...), jd: str = Form(...), user_id: int = Depends(get_current_user_id)):
    from agents.ats_agent import ats_agent
    from agents.writer import writer_agent
    from core.database import get_user_by_id
    
    user = get_user_by_id(user_id)
    try:
        keys = json.loads(user.get("api_keys_json", "{}"))
    except Exception:
        keys = {}
        
    user_api_key = keys.get("groq_key") or os.getenv("GROQ_API_KEY")

    print("Endpoint: Running ATS Scorer...")
    report = ats_agent(resume, jd, api_key=user_api_key)

    # Get Tailored Resume
    mock_state = {
        "resume_profile": resume,
        "current_job": {
            "title": "Target Role",
            "company": "Target Company",
            "description": jd
        }
    }
    try:
        res_state = await asyncio.to_thread(writer_agent, mock_state, api_key=user_api_key)
        report["tailored_resume"] = res_state.get("tailored_resume", resume)
    except Exception as e:
        print(f"Tailored Resume generation failed: {e}")
        report["tailored_resume"] = resume

    return JSONResponse(content=report)

# --- Company Intelligence Research endpoint ---
@app.post("/company-research")
async def company_research(company_name: str = Form(...), resume: str = Form(""), user_id: int = Depends(get_current_user_id)):
    from agents.company_agent import company_agent
    from core.database import get_user_by_id
    
    user = get_user_by_id(user_id)
    try:
        keys = json.loads(user.get("api_keys_json", "{}"))
    except Exception:
        keys = {}
        
    user_api_key = keys.get("groq_key") or os.getenv("GROQ_API_KEY")

    print(f"Endpoint: Running Company Intelligence for {company_name}...")
    try:
        report = await asyncio.to_thread(company_agent, company_name, resume, api_key=user_api_key)
        return JSONResponse(content=report)
    except Exception as e:
        print(f"Company research failed: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

# --- AI Chat endpoint ---
@app.post("/chat")
async def chat(message: str = Form(...), history: str = Form("[]"), resume: str = Form(""), jd: str = Form(""), user_id: int = Depends(get_current_user_id)):
    from agents.chat_agent import chat_agent
    from core.database import get_user_by_id
    
    user = get_user_by_id(user_id)
    try:
        keys = json.loads(user.get("api_keys_json", "{}"))
    except Exception:
        keys = {}
        
    user_api_key = keys.get("groq_key") or os.getenv("GROQ_API_KEY")

    print("Endpoint: Chat Assistant invoked...")
    try:
        history_list = json.loads(history)
    except Exception:
        history_list = []

    history_list.append({"role": "user", "content": message})
    reply = await asyncio.to_thread(chat_agent, history_list, resume, jd, api_key=user_api_key)
    return JSONResponse(content={"reply": reply})

# --- Database application retrieval endpoints ---
@app.get("/applications")
async def get_user_apps(user_id: int = Depends(get_current_user_id)):
    from core.database import get_applications
    return get_applications(user_id)

@app.delete("/applications/{job_id}")
async def delete_user_app(job_id: str, user_id: int = Depends(get_current_user_id)):
    from core.database import delete_application
    try:
        delete_application(user_id, job_id)
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