import json
import re
from tools.llm import claude
from core.state import AgentState

def planner_agent(state: AgentState, api_key: str = None) -> AgentState:
    print("Planner: Scoring job fits...")
    scored = []

    for job in state["listings"]:
        # If no description, give a base score based on title match
        if not job["description"] or len(job["description"]) < 50:
            title_lower = job["title"].lower()
            query_words = state["job_search_query"].lower().split()
            matches = sum(1 for w in query_words if w in title_lower)
            base_score = 55 + (matches * 10)
            scored.append({
                **job,
                "fit_score": min(base_score, 75),
                "fit_reason": "Scored by title match"
            })
            print(f"  {job['title']}: {min(base_score,75)}/100 (title match)")
            continue

        prompt = f"""Score this job fit for the candidate.
Reply ONLY with valid JSON. No extra text. No markdown. No explanation.

CANDIDATE PROFILE:
{state["resume_profile"][:800]}

JOB TITLE: {job["title"]}
COMPANY: {job["company"]}
DESCRIPTION: {job["description"][:1200]}

Reply in this EXACT format only:
{{"score": 72, "reason": "Strong Python match"}}"""

        try:
            result = claude(prompt, max_tokens=150, api_key=api_key)
            result = result.strip()
            # Extract JSON even if model adds extra text
            match = re.search(r'\{.*?\}', result, re.DOTALL)
            if match:
                data = json.loads(match.group())
                score = int(data.get("score", 50))
                reason = data.get("reason", "")
                scored.append({**job, "fit_score": score, "fit_reason": reason})
                print(f"  {job['title']}: {score}/100")
            else:
                raise ValueError("No JSON found")
        except Exception as e:
            print(f"  Could not score {job['title']}: {e}")
            scored.append({**job, "fit_score": 50, "fit_reason": "Auto scored"})

    top = sorted(scored, key=lambda j: j["fit_score"], reverse=True)[:8]
    return {**state, "listings": top}