from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.agents.prompts import ROUTER_SYSTEM
from backend.app.agents.state import RouterDecision, State
from backend.app.services.llm import get_llm, structured


def recency_days_for_mode(mode: str) -> int:
    if mode == "open_book":
        return 7

    if mode == "hybrid":
        return 45

    return 3650


def require_topic(state: State) -> str:
    topic = state.get("topic")
    if not topic:
        raise ValueError("State is missing required field: topic")

    return topic


def build_router_prompt(state: State) -> str:
    topic = require_topic(state)

    return f"""
    Topic: {topic}
    Audience: {state.get("audience") or "general"}
    Tone: {state.get("tone") or "neutral"}
    Requested blog kind: {state.get("blog_kind") or "auto"}
    Research mode requested by user: {state.get("research_mode") or "auto"}

    Today is {date.today().isoformat()}.
    Decide whether this blog requires external research.
    """.strip()


async def router_node(state: State) -> State:
    research_mode = state.get("research_mode", "auto")

    if research_mode == "off":
        mode = "closed_book"
        return {
            "needs_research": False,
            "mode": mode,
            "queries": [],
            "max_results_per_query": 0,
            "recency_days": recency_days_for_mode(mode),
            "as_of": date.today().isoformat(),
        }

    llm = get_llm(temperature=0.2)
    chain = structured(llm, RouterDecision)

    raw_decision = await chain.ainvoke(
        [
            SystemMessage(content=ROUTER_SYSTEM),
            HumanMessage(content=build_router_prompt(state)),
        ]
    )
    decision = RouterDecision.model_validate(raw_decision)

    if research_mode == "required":
        decision.needs_research = True
        if decision.mode == "closed_book":
            decision.mode = "hybrid"

    if not decision.needs_research:
        decision.queries = []
    elif not decision.queries:
        decision.queries = [require_topic(state)]

    return {
        "needs_research": decision.needs_research,
        "mode": decision.mode,
        "queries": decision.queries,
        "max_results_per_query": decision.max_results_per_query,
        "recency_days": recency_days_for_mode(decision.mode),
        "as_of": date.today().isoformat(),
    }
