from __future__ import annotations

from typing import Any

from backend.app.workers import retry
from backend.app.workers.retry import finalize_warnings, retry_placeholders
from backend.tests.fakes import make_plan


async def test_retry_marks_attempt_even_when_placeholder_remains(monkeypatch):
    async def placeholder_writer(state: dict[str, Any]) -> dict[str, Any]:
        task = state["task"]
        return {
            "sections": [
                (
                    task["id"],
                    f"## {task['title']}\n\n_Section unavailable: still slow._",
                )
            ],
            "warnings": ["still slow"],
        }

    monkeypatch.setattr(retry, "writer_node", placeholder_writer)

    plan = make_plan(n_tasks=5).model_dump()
    result = await retry_placeholders(
        "run-1",
        {
            "topic": "T",
            "plan": plan,
            "sections": [(1, "## Section 1\n\n_Section unavailable: timeout._")],
            "warnings": ["writer task=1 (Section 1): timeout"],
        },
    )

    assert result == {"placeholder_retry_attempted": True}


async def test_retry_marks_attempt_and_splices_success(monkeypatch):
    async def successful_writer(state: dict[str, Any]) -> dict[str, Any]:
        task = state["task"]
        return {"sections": [(task["id"], f"## {task['title']}\n\nRecovered.")]}

    monkeypatch.setattr(retry, "writer_node", successful_writer)

    plan = make_plan(n_tasks=5).model_dump()
    result = await retry_placeholders(
        "run-1",
        {
            "topic": "T",
            "plan": plan,
            "sections": [(1, "## Section 1\n\n_Section unavailable: timeout._")],
            "warnings": ["writer task=1 (Section 1): timeout"],
        },
    )

    assert result["placeholder_retry_attempted"] is True
    assert result["sections"] == [(1, "## Section 1\n\nRecovered.")]
    assert result["warnings"] == []


# --- finalize_warnings ----------------------------------------------------


def test_finalize_drops_stale_warning_for_recovered_section():
    # The graph accumulated a writer-timeout warning for task 1, but the
    # placeholder retry later recovered the section. Under operator.add the
    # warning is still in the channel; finalize must prune it.
    state = {
        "sections": [(1, "## Section 1\n\nRecovered content.")],
        "warnings": ["writer task=1 (Section 1): timeout after 600s"],
    }
    assert finalize_warnings(state) == []


def test_finalize_keeps_warning_for_unrecovered_placeholder():
    state = {
        "sections": [(1, "## Section 1\n\n_Section unavailable: timeout._")],
        "warnings": ["writer task=1 (Section 1): timeout after 600s"],
    }
    assert finalize_warnings(state) == ["writer task=1 (Section 1): timeout after 600s"]


def test_finalize_dedupes_and_keeps_non_writer_warnings():
    # citation_guard re-runs inside the quality loop can append duplicates.
    state = {
        "sections": [(1, "## Section 1\n\nGood.")],
        "warnings": [
            "citation_guard task=1 unresolved after repair",
            "citation_guard task=1 unresolved after repair",
            "quality evaluator fallback used: TimeoutError",
        ],
    }
    assert finalize_warnings(state) == [
        "citation_guard task=1 unresolved after repair",
        "quality evaluator fallback used: TimeoutError",
    ]
