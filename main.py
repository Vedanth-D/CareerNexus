from core.graph import graph
from core.state import AgentState

initial_state: AgentState = {
    "job_search_query": "python developer remote",
    "resume_profile": "Test resume - use the web dashboard instead",
    "preferences": {"remote": True},
    "listings": [],
    "current_job": None,
    "tailored_resume": None,
    "cover_letter": None,
    "applied_jobs": [],
    "errors": [],
    "status": "starting"
}

print("Use the web dashboard instead — run: uvicorn server:app --reload")