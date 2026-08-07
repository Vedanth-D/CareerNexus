from langgraph.graph import StateGraph, END
from core.state import AgentState
from agents.scraper import scraper_agent
from agents.planner import planner_agent
from agents.critic import critic_agent
from agents.writer import writer_agent
from agents.browser import browser_agent
from agents.tracker import tracker_agent

def route_after_critic(state: AgentState) -> str:
    if state.get("current_job"):
        return "writer"
    return END

def route_after_browser(state: AgentState) -> str:
    # If more approved jobs remain, loop back
    remaining = [j for j in state["listings"]
                 if j.get("approved") and j["id"] not in state.get("applied_jobs", [])]
    return "writer" if remaining else "tracker"

builder = StateGraph(AgentState)

builder.add_node("scraper", scraper_agent)
builder.add_node("planner", planner_agent)
builder.add_node("critic",  critic_agent)
builder.add_node("writer",  writer_agent)
builder.add_node("browser", browser_agent)
builder.add_node("tracker", tracker_agent)

builder.set_entry_point("scraper")
builder.add_edge("scraper", "planner")
builder.add_edge("planner", "critic")
builder.add_conditional_edges("critic", route_after_critic)
builder.add_edge("writer", "browser")
builder.add_conditional_edges("browser", route_after_browser)
builder.add_edge("tracker", END)

graph = builder.compile()