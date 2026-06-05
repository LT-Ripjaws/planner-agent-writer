from __future__ import annotations

import asyncio
from typing import Any

from backend.app.agents.nodes import quality_evaluator as qe
from backend.app.agents.nodes.quality_evaluator import (
    quality_evaluator_node,
    should_loop_quality,
)
from backend.app.agents.state import QualityReport
from backend.tests.fakes import make_plan


def _low_report() -> QualityReport:
    return QualityReport.model_validate(
        {
            "overall_score": 5.0,
            "on_topic": True,
            "completeness": 0.7,
            "tone_match": True,
            "code_present_where_required": True,
            "issues": [],
            "hallucinations": [],
            "sections_to_redo": [1, 2, 3],
        }
    )


def _state() -> dict[str, Any]:
    plan = make_plan(n_tasks=5, requires_citations=True)
    return {
        "topic": "AI hallucination explained",
        "mode": "hybrid",
        "plan": plan.model_dump(),
        "sections": [
            (1, "## Section 1\n\nOriginal 1."),
            (2, "## Section 2\n\nOriginal 2."),
            (3, "## Section 3\n\nOriginal 3."),
        ],
        "evidence": [{"title": "Source", "url": "https://example.com", "snippet": "s"}],
    }


async def test_quality_improves_only_configured_section_count(monkeypatch):
    improved_ids: list[int] = []

    async def fake_evaluate_once(*_args: Any, **_kwargs: Any) -> QualityReport:
        return _low_report()

    async def fake_improve_section(*, task: dict[str, Any], **_kwargs: Any) -> str:
        improved_ids.append(task["id"])
        return f"## {task['title']}\n\nImproved {task['id']}."

    monkeypatch.setattr(qe, "evaluate_once", fake_evaluate_once)
    monkeypatch.setattr(qe, "improve_section", fake_improve_section)
    monkeypatch.setattr(qe.settings, "quality_eval_enabled", True)
    monkeypatch.setattr(qe.settings, "quality_max_sections_per_iter", 1)
    monkeypatch.setattr(qe.settings, "quality_max_iterations", 2)
    monkeypatch.setattr(qe.settings, "quality_node_timeout_seconds", 240)
    monkeypatch.setattr(qe.settings, "quality_min_improvement_seconds", 1)

    state = _state()
    state["sections"] = [
        *state["sections"],
        (4, "## Section 4\n\nOriginal 4."),
        (5, "## Section 5\n\nOriginal 5."),
    ]
    result = await quality_evaluator_node(state)

    assert improved_ids == [1]
    assert result["improvement_iter"] == 1
    assert "Improved 1" in result["final"]
    assert "Original 2" in result["final"]


async def test_quality_skips_improvement_when_budget_is_low(monkeypatch):
    async def fake_evaluate_once(*_args: Any, **_kwargs: Any) -> QualityReport:
        return _low_report()

    async def fail_improve_section(**_kwargs: Any) -> str:
        raise AssertionError("improvement should not run")

    monkeypatch.setattr(qe, "evaluate_once", fake_evaluate_once)
    monkeypatch.setattr(qe, "improve_section", fail_improve_section)
    monkeypatch.setattr(qe.settings, "quality_eval_enabled", True)
    monkeypatch.setattr(qe.settings, "quality_max_sections_per_iter", 1)
    monkeypatch.setattr(qe.settings, "quality_max_iterations", 2)
    monkeypatch.setattr(qe.settings, "quality_node_timeout_seconds", 6)
    monkeypatch.setattr(qe.settings, "quality_min_improvement_seconds", 30)

    state = _state()
    state["sections"] = [
        *state["sections"],
        (4, "## Section 4\n\nOriginal 4."),
        (5, "## Section 5\n\nOriginal 5."),
    ]
    result = await quality_evaluator_node(state)

    assert "improvement_iter" not in result
    assert any("quality improvement skipped" in warning for warning in result["warnings"])


async def test_quality_evaluator_failure_returns_structural_fallback(monkeypatch):
    async def timeout_evaluate_once(*_args: Any, **_kwargs: Any) -> QualityReport:
        raise asyncio.TimeoutError

    async def fail_improve_section(**_kwargs: Any) -> str:
        raise AssertionError("improvement should not run")

    monkeypatch.setattr(qe, "evaluate_once", timeout_evaluate_once)
    monkeypatch.setattr(qe, "improve_section", fail_improve_section)
    monkeypatch.setattr(qe.settings, "quality_eval_enabled", True)
    monkeypatch.setattr(qe.settings, "quality_max_iterations", 2)
    monkeypatch.setattr(qe.settings, "quality_node_timeout_seconds", 240)

    state = _state()
    state["sections"] = [
        *state["sections"],
        (4, "## Section 4\n\nOriginal 4."),
        (5, "## Section 5\n\nOriginal 5."),
    ]
    result = await quality_evaluator_node(state)

    assert result["quality_report"]["overall_score"] == 7.0
    assert result["quality_report"]["hallucinations"] == []
    assert result["improvement_iter"] == 2
    assert any("quality evaluator fallback used" in warning for warning in result["warnings"])


async def test_quality_skips_llm_when_placeholders_remain(monkeypatch):
    async def fail_evaluate_once(*_args: Any, **_kwargs: Any) -> QualityReport:
        raise AssertionError("quality LLM should not run for placeholder drafts")

    monkeypatch.setattr(qe, "evaluate_once", fail_evaluate_once)
    monkeypatch.setattr(qe.settings, "quality_eval_enabled", True)
    monkeypatch.setattr(qe.settings, "quality_max_iterations", 2)

    state = _state()
    state["sections"][0] = (
        1,
        "## Section 1\n\n_Section unavailable: timeout after 300s._",
    )
    result = await quality_evaluator_node(state)

    assert result["quality_report"]["overall_score"] < 7.0
    assert result["improvement_iter"] == 2
    assert any("placeholder sections remain" in warning for warning in result["warnings"])


# --- chunked evaluation -------------------------------------------------


def _report(score: float, *, on_topic: bool = True, code_ok: bool = True,
            issues: list | None = None, redo: list | None = None) -> QualityReport:
    return QualityReport.model_validate(
        {
            "overall_score": score,
            "on_topic": on_topic,
            "completeness": 1.0,
            "tone_match": True,
            "code_present_where_required": code_ok,
            "issues": issues or [],
            "hallucinations": [],
            "sections_to_redo": redo or [],
        }
    )


def test_plan_subset_filters_tasks_and_keeps_other_fields():
    plan = make_plan(n_tasks=5).model_dump()
    subset = qe.plan_subset(plan, {2, 4})

    assert [t["id"] for t in subset["tasks"]] == [2, 4]
    assert subset["blog_title"] == plan["blog_title"]


def test_merge_reports_weights_scores_and_concatenates():
    r1 = _report(
        6.0,
        code_ok=True,
        issues=[{"task_id": 1, "category": "tone", "severity": "low", "description": "abc"}],
        redo=[1],
    )
    r2 = _report(9.0, on_topic=False, code_ok=False, redo=[3])

    merged = qe.merge_reports([r1, r2], [2, 2])

    assert merged.overall_score == 7.5  # (6*2 + 9*2) / 4
    assert merged.on_topic is False  # AND across batches
    assert merged.code_present_where_required is False
    assert len(merged.issues) == 1
    assert merged.sections_to_redo == [1, 3]


async def test_evaluate_once_chunks_large_draft(monkeypatch):
    seen_batches: list[list[int]] = []

    async def fake_chunk(topic, plan, sections, evidence, mode, timeout_seconds):
        ids = [task_id for task_id, _ in sections]
        seen_batches.append(ids)
        return _report(
            8.0,
            issues=[{"task_id": ids[0], "category": "tone", "severity": "low", "description": "abc"}],
        )

    monkeypatch.setattr(qe, "evaluate_chunk", fake_chunk)
    monkeypatch.setattr(qe.settings, "evaluator_max_sections_per_call", 2)
    monkeypatch.setattr(qe.settings, "quality_llm_timeout_seconds", 280)

    plan = make_plan(n_tasks=5).model_dump()
    sections = [(i, f"## Section {i}\n\nBody {i}.") for i in range(1, 6)]
    report = await qe.evaluate_once("topic", plan, sections, [], "hybrid", timeout_seconds=900)

    # 5 sections / batch 2 -> [1,2], [3,4], [5]
    assert seen_batches == [[1, 2], [3, 4], [5]]
    assert report.overall_score == 8.0
    assert len(report.issues) == 3  # one per batch, concatenated


async def test_evaluate_once_single_call_for_small_draft(monkeypatch):
    seen_batches: list[list[int]] = []

    async def fake_chunk(topic, plan, sections, evidence, mode, timeout_seconds):
        seen_batches.append([task_id for task_id, _ in sections])
        return _report(9.0)

    monkeypatch.setattr(qe, "evaluate_chunk", fake_chunk)
    monkeypatch.setattr(qe.settings, "evaluator_max_sections_per_call", 4)

    plan = make_plan(n_tasks=5).model_dump()
    # Only 3 sections (<= batch size) -> single call, no chunking.
    sections = [(i, f"## Section {i}\n\nBody {i}.") for i in range(1, 4)]
    report = await qe.evaluate_once("topic", plan, sections, [], "hybrid", timeout_seconds=300)

    assert seen_batches == [[1, 2, 3]]  # one call, no chunking
    assert report.overall_score == 9.0


async def test_evaluate_once_merges_surviving_batches(monkeypatch):
    # If one batch fails, the rest are still merged (best-effort).
    async def flaky_chunk(topic, plan, sections, evidence, mode, timeout_seconds):
        ids = [task_id for task_id, _ in sections]
        if ids == [3, 4]:
            raise asyncio.TimeoutError
        return _report(8.0)

    monkeypatch.setattr(qe, "evaluate_chunk", flaky_chunk)
    monkeypatch.setattr(qe.settings, "evaluator_max_sections_per_call", 2)
    monkeypatch.setattr(qe.settings, "quality_llm_timeout_seconds", 280)

    plan = make_plan(n_tasks=5).model_dump()
    sections = [(i, f"## Section {i}\n\nBody {i}.") for i in range(1, 6)]
    report = await qe.evaluate_once("topic", plan, sections, [], "hybrid", timeout_seconds=900)

    # batches [1,2] and [5] survive; [3,4] was skipped
    assert report.overall_score == 8.0


def test_should_loop_quality_stops_after_elapsed_budget(monkeypatch):
    monkeypatch.setattr(qe.settings, "quality_threshold", 7.0)
    monkeypatch.setattr(qe.settings, "quality_eval_enabled", True)
    monkeypatch.setattr(qe.settings, "quality_max_iterations", 2)
    monkeypatch.setattr(qe.settings, "quality_node_timeout_seconds", 10)

    route = should_loop_quality(
        {
            "quality_report": {"overall_score": 5.0},
            "improvement_iter": 0,
            "quality_elapsed_seconds": 10,
        }
    )

    assert route == "end"
