"""Agent pipeline node behavior (no real provider calls).

Exercises the individual nodes with faked LLM/Tavily:
- router: research_mode=off short-circuits to closed_book, no LLM call;
  research_mode=required forces needs_research even on a closed_book decision.
- research: closed-book skips Tavily; required + zero evidence -> ResearchEmpty;
  dedupe + recency filtering + top-16 cap; transient per-query errors tolerated.
- planner: open_book forces news_roundup + per-task citations; task ids renumber.
- reducer: orders sections by task id and prepends the title.
"""
from __future__ import annotations

import pytest

from backend.app.agents.nodes import planner as planner_node_mod
from backend.app.agents.nodes import research as research_mod
from backend.app.agents.nodes import router as router_mod
from backend.app.agents.nodes.reducer import reducer_node
from backend.app.agents.nodes.research import ResearchEmpty, research_node
from backend.app.agents.nodes.router import router_node
from backend.app.agents.state import EvidenceItem, RouterDecision
from backend.tests.fakes import FakeLLM, make_plan


# --- router ---------------------------------------------------------------


async def test_router_off_skips_llm_and_research():
    state = {"topic": "Anything", "research_mode": "off"}
    result = await router_node(state)

    assert result["needs_research"] is False
    assert result["mode"] == "closed_book"
    assert result["queries"] == []
    # closed_book recency window is the widest (3650 days).
    assert result["recency_days"] == 3650


async def test_router_required_forces_research(monkeypatch):
    # The model returns a closed_book / no-research decision; research_mode
    # "required" must override it.
    fake = FakeLLM(
        router_decision=RouterDecision(
            needs_research=False,
            mode="closed_book",
            reason="model thinks it knows enough",
            queries=[],
        )
    )
    monkeypatch.setattr(router_mod, "get_llm", lambda *a, **k: fake)

    state = {"topic": "Latest AI news", "research_mode": "required"}
    result = await router_node(state)

    assert result["needs_research"] is True
    # closed_book gets bumped to hybrid when research is forced.
    assert result["mode"] == "hybrid"
    # No queries from the model -> falls back to the topic.
    assert result["queries"] == ["Latest AI news"]


async def test_router_required_uses_llm_queries(monkeypatch):
    # In required mode we now ask the model for several search angles instead
    # of just the raw topic.
    fake = FakeLLM(
        router_decision=RouterDecision(
            needs_research=True,
            mode="open_book",
            reason="multi-angle",
            queries=["vector db benchmarks 2026", "pgvector vs pinecone", "HNSW recall"],
            max_results_per_query=4,
        )
    )
    monkeypatch.setattr(router_mod, "get_llm", lambda *a, **k: fake)

    state = {"topic": "Vector databases", "research_mode": "required"}
    result = await router_node(state)

    assert result["needs_research"] is True
    assert result["queries"] == [
        "vector db benchmarks 2026",
        "pgvector vs pinecone",
        "HNSW recall",
    ]
    assert result["max_results_per_query"] == 4


async def test_router_required_falls_back_when_query_gen_fails(monkeypatch):
    # If the model call raises, required mode must still proceed with the topic
    # as the sole query rather than crashing the run.
    async def boom(*args, **kwargs):
        raise RuntimeError("provider down")

    class _Boom:
        def with_structured_output(self, _schema):
            return self

        def with_retry(self, *a, **k):
            return self

        ainvoke = staticmethod(boom)

    monkeypatch.setattr(router_mod, "get_llm", lambda *a, **k: _Boom())

    state = {"topic": "Vector databases", "research_mode": "required"}
    result = await router_node(state)

    assert result["needs_research"] is True
    assert result["queries"] == ["Vector databases"]


# --- research -------------------------------------------------------------


async def test_research_skipped_when_not_needed():
    result = await research_node({"needs_research": False})
    assert result == {"evidence": []}


async def test_research_required_with_no_evidence_raises(monkeypatch):
    async def empty_search(query, max_results=5):
        return []

    monkeypatch.setattr(research_mod, "tavily_search_async", empty_search)

    state = {
        "needs_research": True,
        "research_mode": "required",
        "queries": ["something obscure"],
        "max_results_per_query": 5,
    }
    with pytest.raises(ResearchEmpty):
        await research_node(state)


async def test_research_required_missing_tavily_key_raises_clear_error(monkeypatch):
    monkeypatch.setattr(research_mod.settings, "tavily_api_key", None, raising=False)

    state = {
        "needs_research": True,
        "research_mode": "required",
        "queries": ["anything"],
        "max_results_per_query": 5,
    }
    with pytest.raises(ResearchEmpty) as exc_info:
        await research_node(state)

    assert "TAVILY_API_KEY" in str(exc_info.value)


async def test_research_auto_missing_tavily_key_degrades(monkeypatch):
    monkeypatch.setattr(research_mod.settings, "tavily_api_key", None, raising=False)

    state = {
        "needs_research": True,
        "research_mode": "auto",
        "queries": ["anything"],
        "max_results_per_query": 5,
    }
    result = await research_node(state)

    assert result["evidence"] == []
    assert any("TAVILY_API_KEY" in w for w in result["warnings"])


async def test_research_recency_filter_does_not_empty_required_run(monkeypatch):
    # Evergreen topic: Tavily returns real hits, but every one is dated well
    # outside the recency window. The recency filter must NOT discard them all
    # and fail the run — it keeps the older sources and warns instead.
    async def dated_search(query, max_results=5):
        return [
            EvidenceItem(
                title="Old but relevant",
                url="https://old.com",
                snippet="s",
                score=0.8,
                published_at="2020-01-01",
            )
        ]

    monkeypatch.setattr(research_mod, "tavily_search_async", dated_search)

    state = {
        "needs_research": True,
        "research_mode": "required",
        "queries": ["evergreen topic"],
        "max_results_per_query": 5,
        "as_of": "2026-06-03",
        "recency_days": 7,  # tight window; the 2020 source falls outside it
    }
    result = await research_node(state)

    assert [item["url"] for item in result["evidence"]] == ["https://old.com"]
    assert any("recency window" in w for w in result["warnings"])


async def test_research_dedupes_and_caps(monkeypatch):
    # Two queries return overlapping URLs with different scores -> dedup keeps
    # the highest score; result is sorted by score desc.
    async def fake_search(query, max_results=5):
        if query == "q1":
            return [
                EvidenceItem(title="A", url="https://a.com", snippet="s", score=0.5),
                EvidenceItem(title="B", url="https://b.com", snippet="s", score=0.9),
            ]
        return [
            EvidenceItem(title="A2", url="https://a.com", snippet="s", score=0.8),
        ]

    monkeypatch.setattr(research_mod, "tavily_search_async", fake_search)

    state = {
        "needs_research": True,
        "research_mode": "auto",
        "queries": ["q1", "q2"],
        "max_results_per_query": 5,
    }
    result = await research_node(state)
    evidence = result["evidence"]

    urls = [item["url"] for item in evidence]
    assert urls == ["https://b.com", "https://a.com"]  # sorted by score desc
    # a.com deduped to the higher 0.8 score.
    a_item = next(item for item in evidence if item["url"] == "https://a.com")
    assert a_item["score"] == 0.8


async def test_research_tolerates_per_query_failure(monkeypatch):
    async def flaky_search(query, max_results=5):
        if query == "boom":
            raise RuntimeError("network down")
        return [EvidenceItem(title="OK", url="https://ok.com", snippet="s", score=0.7)]

    monkeypatch.setattr(research_mod, "tavily_search_async", flaky_search)

    state = {
        "needs_research": True,
        "research_mode": "auto",
        "queries": ["boom", "fine"],
        "max_results_per_query": 5,
    }
    result = await research_node(state)

    assert [item["url"] for item in result["evidence"]] == ["https://ok.com"]
    assert any("boom" in w for w in result["warnings"])


async def test_research_retries_empty_query_once(monkeypatch):
    calls = 0

    async def empty_then_hit(query, max_results=5):
        nonlocal calls
        calls += 1
        if calls == 1:
            return []
        return [EvidenceItem(title="OK", url="https://ok.com", snippet="s", score=0.7)]

    monkeypatch.setattr(research_mod, "tavily_search_async", empty_then_hit)

    state = {
        "needs_research": True,
        "research_mode": "required",
        "queries": ["fine"],
        "max_results_per_query": 5,
    }
    result = await research_node(state)

    assert calls == 2
    assert [item["url"] for item in result["evidence"]] == ["https://ok.com"]


# --- planner --------------------------------------------------------------


async def test_planner_open_book_forces_citations(monkeypatch):
    fake = FakeLLM(plan=make_plan(blog_kind="explainer", n_tasks=5))
    monkeypatch.setattr(planner_node_mod, "get_llm", lambda *a, **k: fake)

    state = {"topic": "T", "mode": "open_book", "research_mode": "required"}
    result = await planner_node_mod.planner_node(state)

    plan = result["plan"]
    assert plan["blog_kind"] == "news_roundup"  # forced in open_book
    assert all(task["requires_citations"] for task in plan["tasks"])
    # Task ids are renumbered 1..N.
    assert [task["id"] for task in plan["tasks"]] == [1, 2, 3, 4, 5]


# --- reducer --------------------------------------------------------------


def test_reducer_orders_sections_and_prepends_title():
    plan = make_plan(blog_title="My Title", n_tasks=5).model_dump()
    state = {
        "plan": plan,
        "sections": [
            (3, "## Third\n\nC"),
            (1, "## First\n\nA"),
            (2, "## Second\n\nB"),
        ],
    }
    result = reducer_node(state)
    final = result["final"]

    assert final.startswith("# My Title")
    # Sections appear in task-id order regardless of input order.
    assert final.index("## First") < final.index("## Second") < final.index("## Third")
    assert result["merged_md"] == final
