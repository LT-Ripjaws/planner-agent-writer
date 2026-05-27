import inspect
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from backend.app.agents.nodes.planner import planner_node
from backend.app.agents.nodes.reducer import reducer_node
from backend.app.agents.nodes.research import research_node
from backend.app.agents.nodes.router import router_node
from backend.app.agents.nodes.writer import writer_node
from backend.app.agents.state import Plan, State
from backend.app.services.progress import ProgressBus

NodeFunc = Callable[[State], Awaitable[State] | State]
AsyncNodeFunc = Callable[[State], Awaitable[State]]


def route_after_router(state: State) -> Literal["research", "planner"]:
    if state.get("needs_research", False):
        return "research"

    return "planner"


def fanout_to_writers(state: State) -> list[Send]:
    plan = state.get("plan")
    if plan is None:
        raise ValueError("State is missing required field: plan")

    parsed_plan = Plan.model_validate(plan)
    max_sections = state.get("max_sections")
    tasks = parsed_plan.tasks[:max_sections] if max_sections else parsed_plan.tasks

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
                "writer_timeout_seconds": state.get("writer_timeout_seconds", 360),
            },
        )
        for task in tasks
    ]


def node_payload(name: str, state: State, result: State) -> dict[str, Any]:
    if name == "router":
        return {
            "node": name,
            "mode": result.get("mode"),
            "needs_research": result.get("needs_research"),
        }

    if name == "research":
        return {
            "node": name,
            "evidence_count": len(result.get("evidence", [])),
        }

    if name == "planner":
        plan = result.get("plan") or {}
        tasks = plan.get("tasks", []) if isinstance(plan, dict) else []
        return {
            "node": name,
            "section_count": len(tasks),
            "blog_title": plan.get("blog_title") if isinstance(plan, dict) else None,
        }

    if name == "writer":
        task = state.get("task") or {}
        sections = result.get("sections", [])
        return {
            "node": name,
            "task_id": task.get("id") if isinstance(task, dict) else None,
            "title": task.get("title") if isinstance(task, dict) else None,
            "section_count": len(sections),
        }

    if name == "reducer":
        return {
            "node": name,
            "has_final": bool(result.get("final")),
        }

    return {"node": name}


def wrap_with_progress(
    name: str,
    node: NodeFunc,
    progress: ProgressBus | None,
) -> AsyncNodeFunc:
    async def wrapped(state: State) -> State:
        run_id = state.get("run_id")
        if progress is not None and run_id:
            await progress.publish(run_id, "node_started", {"node": name})

        result = node(state)
        if inspect.isawaitable(result):
            result = await result

        if progress is not None and run_id:
            payload = node_payload(name, state, result)
            await progress.publish(run_id, "node_completed", payload)

            for warning in result.get("warnings", []):
                await progress.publish(run_id, "warning", {"message": warning})

            if name == "writer":
                for _, _section in result.get("sections", []):
                    task = state.get("task") or {}
                    await progress.publish(
                        run_id,
                        "section",
                        {
                            "task_id": task.get("id") if isinstance(task, dict) else None,
                            "title": task.get("title") if isinstance(task, dict) else None,
                        },
                    )

        return result

    return wrapped


def build_graph(
    progress: ProgressBus | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
):
    graph = StateGraph(State)

    graph.add_node("router", RunnableLambda(wrap_with_progress("router", router_node, progress)))
    graph.add_node(
        "research",
        RunnableLambda(wrap_with_progress("research", research_node, progress)),
    )
    graph.add_node(
        "planner",
        RunnableLambda(wrap_with_progress("planner", planner_node, progress)),
    )
    graph.add_node("writer", RunnableLambda(wrap_with_progress("writer", writer_node, progress)))
    graph.add_node(
        "reducer",
        RunnableLambda(wrap_with_progress("reducer", reducer_node, progress)),
    )

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

    return graph.compile(checkpointer=checkpointer)
