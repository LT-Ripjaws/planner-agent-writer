import logging
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.agents.prompts import ROUTER_SYSTEM, wrap_untrusted
from backend.app.agents.state import RouterDecision, State
from backend.app.services.llm import get_llm, structured, with_role_fallback

logger = logging.getLogger(__name__)


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
{wrap_untrusted("user_topic", topic)}

{wrap_untrusted("audience", state.get("audience") or "general")}
Tone: {state.get("tone") or "neutral"}
Requested blog kind: {state.get("blog_kind") or "auto"}
Research mode requested by user: {state.get("research_mode") or "auto"}

Today is {date.today().isoformat()}.
Decide whether the topic above requires external research.
""".strip()


async def routing_decision(state: State) -> RouterDecision:
    """One structured LLM call producing the routing decision + queries."""
    primary = structured(get_llm(role="router", temperature=0.2), RouterDecision)
    fallback = structured(get_llm(role="fallback", temperature=0.2), RouterDecision)
    chain = with_role_fallback(primary, fallback)
    raw_decision = await chain.ainvoke(
        [
            SystemMessage(content=ROUTER_SYSTEM),
            HumanMessage(content=build_router_prompt(state)),
        ]
    )
    return RouterDecision.model_validate(raw_decision)


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

    if research_mode == "required":
        # Research is forced on. Still ask the model for queries so we search
        # several angles instead of just the raw topic — richer, more resilient
        # evidence. Fall back to the topic if generation fails or is empty so
        # `required` is never worse than the old single-query behavior.
        mode = "open_book" if state.get("blog_kind") == "news_roundup" else "hybrid"
        queries: list[str] = []
        max_results = 5
        try:
            decision = await routing_decision(state)
            queries = decision.queries
            max_results = decision.max_results_per_query
        except Exception:  # noqa: BLE001 — query generation is best-effort here
            logger.warning(
                "router: query generation failed in required mode; "
                "falling back to the topic as the sole query",
                exc_info=True,
            )
        if not queries:
            queries = [require_topic(state)]

        return {
            "needs_research": True,
            "mode": mode,
            "queries": queries,
            "max_results_per_query": max_results,
            "recency_days": recency_days_for_mode(mode),
            "as_of": date.today().isoformat(),
        }

    # auto: honor the model's decision
    decision = await routing_decision(state)

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
