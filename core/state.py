from typing import TypedDict, Optional, List

class JobListing(TypedDict):
    id: str
    title: str
    company: str
    url: str
    description: str
    fit_score: Optional[float]   # filled by planner
    approved: Optional[bool]     # filled by critic

class AgentState(TypedDict):
    # inputs
    job_search_query: str
    resume_profile: str          # base resume as markdown
    preferences: dict            # role, location, salary, remote

    # pipeline data
    listings: List[JobListing]
    current_job: Optional[JobListing]
    tailored_resume: Optional[str]
    cover_letter: Optional[str]

    # outputs
    applied_jobs: List[str]      # job IDs already applied to
    errors: List[str]
    status: str                  # "scraping" | "evaluating" | "applying" | "done"