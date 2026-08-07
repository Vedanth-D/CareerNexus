from core.state import AgentState

def critic_agent(state: AgentState) -> AgentState:
    print("🔎 Critic: Checking which jobs to apply to...")
    approved = []
    already_applied = state.get("applied_jobs", [])

    for job in state["listings"]:
        score = job.get("fit_score", 0)
        already_done = job["id"] in already_applied

        if already_done:
            print(f"  ⏭️  Skipping {job['title']} — already applied")
            approved.append({**job, "approved": False})
        elif score >= 50:          # lowered threshold from 60 to 50
            print(f"  ✅ Approved: {job['title']} ({score}/100)")
            approved.append({**job, "approved": True})
        else:
            print(f"  ❌ Rejected: {job['title']} ({score}/100)")
            approved.append({**job, "approved": False})

    state["listings"] = approved
    candidates = [j for j in approved if j["approved"]]

    if candidates:
        state["current_job"] = candidates[0]
        print(f"  Selected: {candidates[0]['title']} at {candidates[0]['company']}")
    else:
        state["current_job"] = None
        print("  No jobs approved this run")

    return state