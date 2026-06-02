"""Test doubles for the LLM and Tavily search services.

These let the agent graph run end-to-end in tests with **zero real API
calls**. They mimic just enough of the LangChain `ChatOpenAI` /
`AsyncTavilyClient` surface that the nodes exercise:

- `FakeLLM.with_structured_output(schema)` -> object whose `.ainvoke()`
  returns a scripted instance of `schema` (used by router/planner).
- `FakeLLM.ainvoke(messages)` -> object with `.content` string (used by the
  writer and citation-repair, which call the model in free-form mode).
- `FakeTavily` -> returns canned hits shaped like Tavily's `search()` output.
"""
from __future__ import annotations

from typing import Any

from backend.app.agents.state import Plan, RouterDecision


class _Response:
    """Mimics a LangChain message: only `.content` is read by the nodes."""

    def __init__(self, content: str) -> None:
        self.content = content


class _StructuredRunnable:
    """Stands in for `llm.with_structured_output(schema).with_retry(...)`."""

    def __init__(self, llm: "FakeLLM", schema: type) -> None:
        self._llm = llm
        self._schema = schema

    def with_retry(self, *args: Any, **kwargs: Any) -> "_StructuredRunnable":
        return self

    async def ainvoke(self, _messages: Any, *args: Any, **kwargs: Any) -> Any:
        return self._llm._structured_for(self._schema)


class FakeLLM:
    """Scripted chat model.

    Parameters let a test tailor the run:
    - `router_decision`: the `RouterDecision` the router node receives.
    - `plan`: the `Plan` the planner node receives.
    - `section_markdown(task_id, title) -> str`: writer output per section.
    - `repair_markdown(section) -> str`: citation-repair output.
    """

    def __init__(
        self,
        *,
        router_decision: RouterDecision | None = None,
        plan: Plan | None = None,
        section_markdown: Any = None,
        repair_markdown: Any = None,
    ) -> None:
        self.router_decision = router_decision
        self.plan = plan
        self._section_markdown = section_markdown
        self._repair_markdown = repair_markdown
        self.invocations: list[Any] = []

    # -- structured path (router, planner) --------------------------------
    def with_structured_output(self, schema: type) -> _StructuredRunnable:
        return _StructuredRunnable(self, schema)

    def _structured_for(self, schema: type) -> Any:
        if schema is RouterDecision:
            if self.router_decision is None:
                raise AssertionError("FakeLLM got an unexpected RouterDecision call")
            return self.router_decision
        if schema is Plan:
            if self.plan is None:
                raise AssertionError("FakeLLM got an unexpected Plan call")
            return self.plan
        raise AssertionError(f"FakeLLM has no scripted output for schema {schema!r}")

    # -- free-form path (writer, citation repair) -------------------------
    async def ainvoke(self, messages: Any, *args: Any, **kwargs: Any) -> _Response:
        self.invocations.append(messages)
        text = self._render_freeform(messages)
        return _Response(text)

    def _render_freeform(self, messages: Any) -> str:
        human = messages[-1].content if messages else ""
        # Citation-repair calls carry "Issues to fix:" in the human prompt.
        if "Issues to fix:" in human and self._repair_markdown is not None:
            return self._repair_markdown(human)
        if self._section_markdown is not None:
            return self._section_markdown(human)
        return "## Section\n\nFake section body."


class FakeTavily:
    """Mimics `AsyncTavilyClient`. Returns canned hits or raises per-query."""

    def __init__(self, hits_by_query: dict[str, list[dict]] | None = None) -> None:
        self.hits_by_query = hits_by_query or {}
        self.default_hits: list[dict] = []
        self.queries: list[str] = []

    async def search(self, query: str, **kwargs: Any) -> dict:
        self.queries.append(query)
        hits = self.hits_by_query.get(query, self.default_hits)
        return {"results": hits}


def make_hit(
    *,
    url: str,
    title: str = "Example source",
    content: str = "A relevant snippet of evidence.",
    score: float = 0.9,
    published_date: str | None = None,
) -> dict:
    """Build a Tavily-shaped raw hit."""
    return {
        "url": url,
        "title": title,
        "content": content,
        "score": score,
        "published_date": published_date,
    }


def make_plan(
    *,
    blog_title: str = "Test Title",
    blog_kind: str = "explainer",
    n_tasks: int = 5,
    requires_citations: bool = False,
) -> Plan:
    """Build a valid `Plan` (5-9 tasks, each 3-6 bullets, 120-220 words)."""
    tasks = [
        {
            "id": i,
            "title": f"Section {i}",
            "goal": f"Explain part {i} of the topic.",
            "bullets": [f"Point {i}.1", f"Point {i}.2", f"Point {i}.3"],
            "target_words": 150,
            "tags": [],
            "requires_research": requires_citations,
            "requires_citations": requires_citations,
            "requires_code": False,
        }
        for i in range(1, n_tasks + 1)
    ]
    return Plan.model_validate(
        {
            "blog_title": blog_title,
            "audience": "general",
            "tone": "neutral",
            "blog_kind": blog_kind,
            "constraints": [],
            "tasks": tasks,
        }
    )
