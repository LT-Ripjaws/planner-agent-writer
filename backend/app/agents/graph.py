from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from backend.app.agents.nodes.planner import planner_node
from backend.app.agents.nodes.reducer import reducer_node
from backend.app.agents.nodes.research import research_node
from backend.app.agents.nodes.router import router_node
from backend.app.agents.nodes.writer import writer_node
from backend.app.agents.state import Plan, State


def route_after_router(state: State) -> Literal["research", "planner"]:
    if state.get("needs_research", False):
        return "research"

    return "planner"


def fanout_to_writers(state: State) -> list[Send]:
    plan = state.get("plan")
    if plan is None:
        raise ValueError("State is missing required field: plan")

    parsed_plan = Plan.model_validate(plan)
    return [
        Send(
            "writer",
            {
                "run_id": state.get("run_id", ""),
                "topic": state.get("topic", ""),
                "audience": state.get("audience"),
                "tone": state.get("tone", "neutral"),
                "blog_kind": state.get("blog_kind", "auto"),
                "research_mode": state.get("research_mode", "auto"),
                "mode": state.get("mode", "closed_book"),
                "as_of": state.get("as_of", ""),
                "recency_days": state.get("recency_days", 3650),
                "evidence": state.get("evidence", []),
                "plan": parsed_plan.model_dump(),
                "task": task.model_dump(),
            },
        )
        for task in parsed_plan.tasks
    ]


def build_graph():
    graph = StateGraph(State)

    graph.add_node("router", router_node)
    graph.add_node("research", research_node)
    graph.add_node("planner", planner_node)
    graph.add_node("writer", writer_node)
    graph.add_node("reducer", reducer_node)

    graph.add_edge(START, "router")
    graph.add_conditional_edges(
        "router",
        route_after_router,
        {
            "research": "research",
            "planner": "planner",
        },
    )
    graph.add_edge("research", "planner")
    graph.add_conditional_edges("planner", fanout_to_writers, ["writer"])
    graph.add_edge("writer", "reducer")
    graph.add_edge("reducer", END)

    return graph.compile()
