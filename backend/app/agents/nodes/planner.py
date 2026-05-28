import json
from typing import cast

from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.agents.prompts import PLANNER_SYSTEM, wrap_untrusted
from backend.app.agents.state import BlogKind, Plan, State
from backend.app.services.llm import get_llm, structured

ALLOWED_BLOG_KINDS: set[BlogKind] = {
    "explainer",
    "tutorial",
    "news_roundup",
    "comparison",
    "system_design",
}


def require_topic(state: State) -> str:
    topic = state.get("topic")
    if not topic:
        raise ValueError("State is missing required field: topic")

    return topic


def evidence_preview(state: State) -> str:
    evidence = state.get("evidence", [])
    if not evidence:
        return wrap_untrusted("evidence", "No external evidence provided.")

    return wrap_untrusted("evidence", json.dumps(evidence[:16], indent=2))


def requested_blog_kind(state: State) -> BlogKind | None:
    blog_kind = state.get("blog_kind", "auto")
    if blog_kind in ALLOWED_BLOG_KINDS:
        return cast(BlogKind, blog_kind)

    return None


def build_planner_prompt(state: State) -> str:
    return f"""
{wrap_untrusted("user_topic", require_topic(state))}

Audience: {state.get("audience") or "general"}
Tone: {state.get("tone") or "neutral"}
Requested blog kind: {requested_blog_kind(state) or "auto"}
Research mode: {state.get("research_mode", "auto")}
Resolved mode: {state.get("mode", "closed_book")}
As of date: {state.get("as_of", "unknown")}

{evidence_preview(state)}

Create a blog plan that a set of parallel writer nodes can execute.
Use concise task titles and concrete bullets.
""".strip()


def normalize_plan(plan: Plan, state: State) -> Plan:
    forced_kind = requested_blog_kind(state)
    if forced_kind is not None:
        plan.blog_kind = forced_kind

    if state.get("mode") == "open_book":
        plan.blog_kind = "news_roundup"

    for index, task in enumerate(plan.tasks, start=1):
        task.id = index

        if state.get("mode") == "open_book":
            task.requires_research = True
            task.requires_citations = True

    return plan


async def planner_node(state: State) -> State:
    llm = get_llm(temperature=0.3)
    chain = structured(llm, Plan)

    raw_plan = await chain.ainvoke(
        [
            SystemMessage(content=PLANNER_SYSTEM),
            HumanMessage(content=build_planner_prompt(state)),
        ]
    )
    plan = normalize_plan(Plan.model_validate(raw_plan), state)

    return {
        "plan": plan.model_dump(),
    }
