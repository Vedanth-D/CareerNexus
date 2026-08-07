from tools.llm import claude
from core.state import AgentState
from agents.email_agent import email_agent

def writer_agent(state: AgentState, api_key: str = None) -> AgentState:
    job = state.get("current_job")
    if not job:
        print("✍️  Writer: No job to write for.")
        return {**state, "status": "done"}

    print(f"Writer: Generating outreach assets and tailoring resume for {job['title']} at {job['company']}...")

    resume_text = state["resume_profile"]
    job_desc = job.get("description", "")
    
    # Use our modular email_agent to generate cover letter, recruiter email, and linkedin connection note
    assets = email_agent(resume_text, job["title"], job["company"], job_desc, api_key=api_key)
    
    cover_letter = assets.get("cover_letter", "")
    recruiter_email = assets.get("recruiter_email", {})
    linkedin_note = assets.get("linkedin_note", "")

    # Tailor the resume specifically to this job
    resume_prompt = f"""Rewrite this resume to be ATS-optimized for the job below.
- Mirror keywords from the job naturally
- Put most relevant experience first
- Keep all real facts, just reorder and reword
- Output in clean plain text format

JOB: {job['title']} at {job['company']}
JOB KEYWORDS: {job_desc[:600]}

ORIGINAL RESUME:
{resume_text[:1200]}

Tailored Resume:"""

    try:
        tailored = claude(resume_prompt, max_tokens=1000, api_key=api_key)
        print("  ✅ Resume tailored successfully")
    except Exception as e:
        tailored = resume_text
        print(f"  ⚠️ Resume tailoring fallback: {e}")

    return {
        **state,
        "tailored_resume": tailored,
        "cover_letter":    cover_letter,
        "recruiter_email": recruiter_email,
        "linkedin_note":    linkedin_note
    }