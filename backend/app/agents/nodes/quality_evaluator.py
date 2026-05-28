"""Quality evaluator + bounded improvement loop.

Runs as a single LangGraph node after `citation_guard`. Internally:

1. **Evaluate** — call LLM with structured `QualityReport` output. Scores
   overall quality (0–10), on-topic-ness, completeness, tone match, code
   presence, per-section issues, and hallucination flags.
2. **Decide** — if `overall_score >= QUALITY_THRESHOLD` or we've already run
   `QUALITY_MAX_ITERATIONS`, stop.
3. **Improve** — for up to `QUALITY_MAX_SECTIONS_PER_ITER` sections in
   `sections_to_redo`, re-prompt the writer via `IMPROVEMENT_SYSTEM` with the
   evaluator's feedback for that section. Splice the improved text back into
   `state["sections"]`, regenerate `final`.
4. **Loop** — re-evaluate; repeat until threshold or cap.

The loop happens inside the node (not as a graph cycle) so the LangGraph
topology stays linear and the SSE event stream is easy to reason about. The
node still emits per-iteration bus events (`quality_started`,
`quality_completed`, `improvement_started`, `improvement_completed`) so the
frontend timeline can show the optimization arc.

Hallucination detection is part of `EVALUATOR_SYSTEM` — see that prompt
for the mode-specific rules. High-severity hallucinations force the parent
section into `sections_to_redo` even if other scores would have passed.
"""
from __future__ import annotations

import json
import logging
import sys
from collections.abc import Mapping
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.agents.prompts import (
    EVALUATOR_SYSTEM,
    IMPROVEMENT_SYSTEM,
    wrap_untrusted,
)
from backend.app.agents.state import HallucinationFlag, Issue, QualityReport, State
from backend.app.core.config import settings
from backend.app.services.llm import get_llm, structured
from backend.app.services.progress import ProgressBus, get_progress_bus

logger = logging.getLogger(__name__)


def log(message: str) -> None:
    print(f"[quality] {message}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Helpers


def tasks_by_id(plan: dict[str, Any] | None) -> dict[int, dict[str, Any]]:
    if not isinstance(plan, dict):
        return {}
    tasks = plan.get("tasks") or []
    return {t["id"]: t for t in tasks if isinstance(t, dict) and "id" in t}


def rebuild_final(blog_title: str, sections: list[tuple[int, str]]) -> str:
    ordered = [body for _, body in sorted(sections, key=lambda item: item[0])]
    body = "\n\n".join(s.strip() for s in ordered if s.strip())
    return f"# {blog_title}\n\n{body}".strip()


def build_evaluator_prompt(
    topic: str,
    plan: dict[str, Any],
    sections: list[tuple[int, str]],
    evidence: list[dict[str, Any]],
    mode: str,
) -> str:
    draft = rebuild_final(plan.get("blog_title", "Untitled"), sections)
    return f"""
Mode: {mode}

{wrap_untrusted("topic", topic)}

{wrap_untrusted("plan", json.dumps(plan, indent=2))}

{wrap_untrusted("evidence", json.dumps(evidence[:16], indent=2) if evidence else "No evidence provided.")}

{wrap_untrusted("draft", draft)}

Evaluate this draft against the plan and (if present) the evidence.
Return a QualityReport per the schema.
""".strip()


def build_improvement_prompt(
    task: dict[str, Any],
    section_body: str,
    issues_for_task: list[dict[str, Any]],
    hallucinations_for_task: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> str:
    return f"""
{wrap_untrusted("task", json.dumps(task, indent=2))}

{wrap_untrusted("section", section_body)}

{wrap_untrusted("issues", json.dumps(issues_for_task, indent=2))}

{wrap_untrusted("hallucinations", json.dumps(hallucinations_for_task, indent=2))}

{wrap_untrusted("evidence", json.dumps(evidence[:16], indent=2) if evidence else "No evidence provided.")}

Rewrite ONLY this section to address the listed issues and hallucinations.
""".strip()


def content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            part["text"] if isinstance(part, dict) and "text" in part else str(part)
            for part in content
        )
    return str(content)


# ---------------------------------------------------------------------------
# Hallucination handling 


def task_ids_with_high_severity_hallucinations(
    hallucinations: list[Any],
) -> set[int]:
    """Any section with a high-severity hallucination forces a redo."""
    ids: set[int] = set()
    for item in hallucinations:
        flag = HallucinationFlag.model_validate(item).model_dump()
        task_id = flag.get("task_id")
        if flag.get("severity") == "high" and isinstance(task_id, int):
            ids.add(task_id)
    return ids


# ---------------------------------------------------------------------------
# Evaluation pass (one LLM call)


async def evaluate_once(
    topic: str,
    plan: dict[str, Any],
    sections: list[tuple[int, str]],
    evidence: list[dict[str, Any]],
    mode: str,
) -> QualityReport:
    llm = get_llm(temperature=0.2)
    chain = structured(llm, QualityReport)
    raw = await chain.ainvoke(
        [
            SystemMessage(content=EVALUATOR_SYSTEM),
            HumanMessage(content=build_evaluator_prompt(topic, plan, sections, evidence, mode)),
        ]
    )
    return QualityReport.model_validate(raw)


# ---------------------------------------------------------------------------
# Improvement pass (one LLM call per section to redo)


async def improve_section(
    task: dict[str, Any],
    section_body: str,
    issues_for_task: list[dict[str, Any]],
    hallucinations_for_task: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> str:
    llm = get_llm(temperature=0.5)
    response = await llm.ainvoke(
        [
            SystemMessage(content=IMPROVEMENT_SYSTEM),
            HumanMessage(content=build_improvement_prompt(
                task, section_body, issues_for_task, hallucinations_for_task, evidence,
            )),
        ]
    )
    return content_to_text(response.content).strip()


def issues_for_task(report: QualityReport, task_id: int) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for item in report.issues:
        issue = Issue.model_validate(item).model_dump()
        if issue.get("task_id") == task_id:
            matches.append(issue)
    return matches


def hallucinations_for_task(report: QualityReport, task_id: int) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for item in report.hallucinations:
        hallucination = HallucinationFlag.model_validate(item).model_dump()
        if hallucination.get("task_id") == task_id:
            matches.append(hallucination)
    return matches


# ---------------------------------------------------------------------------
# Node entry point


async def quality_evaluator_node(state: State) -> State:
    """One round of evaluate-and-maybe-improve.

    Each invocation evaluates the current draft and runs at most one
    improvement pass. The graph runs this node multiple times (via a
    conditional edge back to itself) until either the score clears the
    threshold or `improvement_iter` reaches the cap.
    """
    if not settings.quality_eval_enabled:
        return {}

    sections: list[tuple[int, str]] = list(state.get("sections", []))
    if not sections:
        return {}

    plan: dict[str, Any] = state.get("plan") or {}
    if not plan:
        return {}

    topic: str = state.get("topic", "")
    evidence: list[dict[str, Any]] = list(state.get("evidence", []))
    mode: str = state.get("mode", "closed_book")
    run_id: str = state.get("run_id", "")
    bus: ProgressBus = get_progress_bus()
    iter_count: int = int(state.get("improvement_iter", 0))

    # ---- Evaluate
    if run_id:
        await bus.publish(run_id, "node_started", {"node": "quality_eval", "iter": iter_count})
    log(f"evaluating draft (iter={iter_count})")

    try:
        report = await evaluate_once(topic, plan, sections, evidence, mode)
    except Exception as exc:  # noqa: BLE001 — evaluator failures shouldn't kill the run
        log(f"evaluator failed: {type(exc).__name__}: {exc}; skipping quality loop")
        if run_id:
            await bus.publish(
                run_id,
                "warning",
                {"message": f"quality evaluator failed: {type(exc).__name__}"},
            )
        return {}

    log(
        f"score={report.overall_score:.1f} on_topic={report.on_topic} "
        f"completeness={report.completeness:.2f} "
        f"issues={len(report.issues)} hallucinations={len(report.hallucinations)} "
        f"sections_to_redo={report.sections_to_redo}"
    )

    if run_id:
        await bus.publish(
            run_id,
            "node_completed",
            {
                "node": "quality_eval",
                "iter": iter_count,
                "score": report.overall_score,
                "issues_count": len(report.issues),
                "hallucinations_count": len(report.hallucinations),
                "sections_to_redo": report.sections_to_redo,
            },
        )

    # high-severity hallucinations override sections_to_redo
    forced = task_ids_with_high_severity_hallucinations(report.hallucinations)
    sections_to_redo: list[int] = list(dict.fromkeys(list(report.sections_to_redo) + sorted(forced)))
    sections_to_redo = sections_to_redo[: settings.quality_max_sections_per_iter]

    threshold = settings.quality_threshold
    max_iters = settings.quality_max_iterations

    # ---- Decide
    if report.overall_score >= threshold and not forced:
        log(f"score >= threshold ({threshold}); accepting draft")
        return {"quality_report": report.model_dump()}
    if iter_count >= max_iters:
        log(f"iter cap reached ({max_iters}); accepting draft with score {report.overall_score:.1f}")
        return {
            "quality_report": report.model_dump(),
            "warnings": [
                f"quality below threshold ({report.overall_score:.1f}/{threshold}) after {iter_count} improvement pass(es)"
            ],
        }
    if not sections_to_redo:
        log("no sections flagged for redo; accepting draft")
        return {"quality_report": report.model_dump()}

    # ---- Improve
    if run_id:
        await bus.publish(
            run_id,
            "node_started",
            {"node": "improvement", "iter": iter_count + 1, "sections": sections_to_redo},
        )
    log(f"improving sections {sections_to_redo} (iter -> {iter_count + 1})")

    tasks = tasks_by_id(plan)
    new_sections: list[tuple[int, str]] = list(sections)
    section_by_id: dict[int, str] = {tid: body for tid, body in sections}
    improved_count = 0

    for task_id in sections_to_redo:
        task = tasks.get(task_id)
        current = section_by_id.get(task_id)
        if task is None or current is None:
            continue

        try:
            improved = await improve_section(
                task=task,
                section_body=current,
                issues_for_task=issues_for_task(report, task_id),
                hallucinations_for_task=hallucinations_for_task(report, task_id),
                evidence=evidence,
            )
        except Exception as exc:  # noqa: BLE001
            log(f"task={task_id} improvement raised {type(exc).__name__}: {exc}")
            if run_id:
                await bus.publish(
                    run_id,
                    "warning",
                    {"message": f"improvement failed for task {task_id}: {type(exc).__name__}"},
                )
            continue

        if not improved:
            continue

        new_sections = [
            (tid, improved) if tid == task_id else (tid, body)
            for tid, body in new_sections
        ]
        improved_count += 1

    if run_id:
        await bus.publish(
            run_id,
            "node_completed",
            {"node": "improvement", "iter": iter_count + 1, "improved": improved_count},
        )

    final = rebuild_final(plan.get("blog_title", "Untitled"), new_sections)

    return {
        "sections": new_sections,
        "final": final,
        "improvement_iter": iter_count + 1,
        "quality_report": report.model_dump(),
    }


def should_loop_quality(state: Mapping[str, Any]) -> str:
    """Conditional edge: stay in the loop until threshold or iter cap."""
    if not settings.quality_eval_enabled:
        return "end"

    report = state.get("quality_report")
    iter_count = int(state.get("improvement_iter", 0))

    # If no report exists, the node short-circuited (e.g., no sections, no plan,
    # or evaluator failed) — exit.
    if not isinstance(report, dict):
        return "end"

    score = float(report.get("overall_score", 0))
    if score >= settings.quality_threshold:
        return "end"
    if iter_count >= settings.quality_max_iterations:
        return "end"

    return "loop"
