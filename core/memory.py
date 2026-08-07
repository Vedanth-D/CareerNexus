import json
import os

MEMORY_FILE = "data/memory.json"

def load_memory() -> dict:
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE) as f:
            return json.load(f)
    return {
        "applied_jobs": [],
        "blacklisted_companies": [],
        "total_applied": 0
    }

def save_memory(memory: dict):
    os.makedirs("data", exist_ok=True)
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)

def add_applied_job(job_id: str, job_title: str, company: str):
    memory = load_memory()
    memory["applied_jobs"].append({
        "id": job_id,
        "title": job_title,
        "company": company
    })
    memory["total_applied"] += 1
    save_memory(memory)
    print(f"  Memory updated: {memory['total_applied']} total applications")

def get_applied_ids() -> list:
    memory = load_memory()
    return [j["id"] for j in memory["applied_jobs"]]