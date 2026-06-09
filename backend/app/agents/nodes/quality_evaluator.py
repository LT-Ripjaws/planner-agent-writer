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

import asyncio
import json
import logging
import sys
import time
from collections.abc import Mapping
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.agents.markdown_sanitize import (
    clean_title,
    compact_evidence_for_prompt,
    sanitize_section_markdown,
)
from backend.app.agents.prompts import (
    EVALUATOR_SYSTEM,
    IMPROVEMENT_SYSTEM,
    wrap_untrusted,
)
from backend.app.agents.state import HallucinationFlag, Issue, QualityReport, State
from backend.app.core.config import settings
from backend.app.services.llm import get_llm, structured, with_role_fallback
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
    return f"# {clean_title(blog_title)}\n\n{body}".strip()


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

{wrap_untrusted("evidence", json.dumps(compact_evidence_for_prompt(evidence), ensure_ascii=False) if evidence else "No evidence provided.")}

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

{wrap_untrusted("evidence", json.dumps(compact_evidence_for_prompt(evidence), ensure_ascii=False) if evidence else "No evidence provided.")}

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


def structural_fallback_report(
    plan: dict[str, Any],
    sections: list[tuple[int, str]],
    *,
    reason: str,
) -> QualityReport:
    tasks = tasks_by_id(plan)
    section_by_id = {task_id: body for task_id, body in sections}
    issues: list[dict[str, Any]] = []
    complete_count = 0
    code_ok = True

    for task_id, task in tasks.items():
        body = section_by_id.get(task_id, "")
        if not body.strip():
            issues.append(
                {
                    "task_id": task_id,
                    "category": "incomplete",
                    "severity": "high",
                    "description": "Section is missing from the draft.",
                }
            )
            continue

        if "_Section unavailable:" in body:
            issues.append(
                {
                    "task_id": task_id,
                    "category": "incomplete",
                    "severity": "high",
                    "description": "Section is a provider-failure placeholder.",
                }
            )
            continue

        complete_count += 1
        if bool(task.get("requires_code")) and "```" not in body:
            code_ok = False
            issues.append(
                {
                    "task_id": task_id,
                    "category": "missing_code",
                    "severity": "high",
                    "description": "Section requires code but has no fenced code block.",
                }
            )

    task_count = max(len(tasks), 1)
    completeness = complete_count / task_count
    if not tasks:
        completeness = 1.0 if sections else 0.0

    score = 7.0 if completeness >= 1.0 and code_ok else max(3.0, 7.0 * completeness)
    redo = [issue["task_id"] for issue in issues[: settings.quality_max_sections_per_iter]]

    return QualityReport.model_validate(
        {
            "overall_score": round(score, 1),
            "on_topic": True,
            "on_topic_reason": f"LLM evaluator unavailable; structural fallback used after {reason}.",
            "completeness": round(completeness, 2),
            "tone_match": True,
            "code_present_where_required": code_ok,
            "issues": issues,
            "hallucinations": [],
            "sections_to_redo": redo,
        }
    )


# ---------------------------------------------------------------------------
# Evaluation pass (chunked: one or more LLM calls, merged)


def plan_subset(plan: dict[str, Any], task_ids: set[int]) -> dict[str, Any]:
    """A copy of ``plan`` whose ``tasks`` are restricted to ``task_ids``.

    Used when evaluating a batch of sections so the model judges only those
    tasks and doesn't penalize the draft for the sections that aren't in the
    batch.
    """
    subset = dict(plan)
    tasks = plan.get("tasks") or []
    subset["tasks"] = [
        t for t in tasks if isinstance(t, dict) and t.get("id") in task_ids
    ]
    return subset


def merge_reports(
    reports: list[QualityReport],
    section_counts: list[int],
) -> QualityReport:
    """Combine per-batch QualityReports into one whole-draft report.

    Holistic scores become section-count-weighted aggregates; boolean
    dimensions AND together; per-section lists (issues, hallucinations,
    sections_to_redo) concatenate.
    """
    if len(reports) == 1:
        return reports[0]

    total = sum(section_counts) or len(reports) or 1

    def weighted(attr: str) -> float:
        return sum(getattr(r, attr) * c for r, c in zip(reports, section_counts)) / total

    issues = [issue.model_dump() for r in reports for issue in r.issues]
    hallucinations = [h.model_dump() for r in reports for h in r.hallucinations]
    redo: list[int] = []
    for r in reports:
        for task_id in r.sections_to_redo:
            if task_id not in redo:
                redo.append(task_id)

    return QualityReport.model_validate(
        {
            "overall_score": round(weighted("overall_score"), 1),
            "on_topic": all(r.on_topic for r in reports),
            "on_topic_reason": f"merged from {len(reports)} batch evaluation(s)",
            "completeness": round(weighted("completeness"), 2),
            "tone_match": all(r.tone_match for r in reports),
            "code_present_where_required": all(
                r.code_present_where_required for r in reports
            ),
            "issues": issues,
            "hallucinations": hallucinations,
            "sections_to_redo": redo[:3],
        }
    )


async def evaluate_chunk(
    topic: str,
    plan: dict[str, Any],
    sections: list[tuple[int, str]],
    evidence: list[dict[str, Any]],
    mode: str,
    timeout_seconds: float,
) -> QualityReport:
    """One structured evaluation LLM call over a batch of sections."""
    primary = structured(
        get_llm(role="evaluator", temperature=0.2, timeout=settings.quality_llm_timeout_seconds),
        QualityReport,
    )
    fallback = structured(
        get_llm(role="fallback", temperature=0.2, timeout=settings.quality_llm_timeout_seconds),
        QualityReport,
    )
    chain = with_role_fallback(primary, fallback)
    raw = await asyncio.wait_for(
        chain.ainvoke(
            [
                SystemMessage(content=EVALUATOR_SYSTEM),
                HumanMessage(content=build_evaluator_prompt(topic, plan, sections, evidence, mode)),
            ]
        ),
        timeout=timeout_seconds,
    )
    return QualityReport.model_validate(raw)


async def evaluate_once(
    topic: str,
    plan: dict[str, Any],
    sections: list[tuple[int, str]],
    evidence: list[dict[str, Any]],
    mode: str,
    timeout_seconds: float | None = None,
) -> QualityReport:
    """Evaluate the draft, chunking into batches when it has many sections.

    ``timeout_seconds`` is the TOTAL budget for the (possibly multi-call)
    evaluation; each batch call is additionally capped at the per-call
    ``quality_llm_timeout_seconds`` ceiling. Batches that fail are skipped; the
    surviving batches are merged. Only if *every* batch fails do we raise (the
    node then falls back).
    """
    total_budget = float(timeout_seconds or settings.quality_llm_timeout_seconds)
    batch_size = max(1, settings.evaluator_max_sections_per_call)
    per_call_ceiling = float(settings.quality_llm_timeout_seconds)

    if len(sections) <= batch_size:
        return await evaluate_chunk(
            topic, plan, sections, evidence, mode, min(per_call_ceiling, total_budget)
        )

    chunks = [sections[i:i + batch_size] for i in range(0, len(sections), batch_size)]
    deadline = time.monotonic() + total_budget
    reports: list[QualityReport] = []
    counts: list[int] = []

    for chunk in chunks:
        remaining = deadline - time.monotonic()
        if remaining < 5:
            log("quality eval budget exhausted; merging the batches scored so far")
            break
        per = min(per_call_ceiling, remaining)
        chunk_ids = {task_id for task_id, _ in chunk}
        try:
            report = await evaluate_chunk(
                topic, plan_subset(plan, chunk_ids), chunk, evidence, mode, per
            )
        except Exception as exc:  # noqa: BLE001 — skip a failed batch, keep the rest
            log(f"quality eval batch {sorted(chunk_ids)} failed ({type(exc).__name__}); skipping")
            continue
        reports.append(report)
        counts.append(len(chunk))

    if not reports:
        raise asyncio.TimeoutError("all quality evaluation batches failed")

    log(f"chunked eval: scored {len(reports)}/{len(chunks)} batch(es)")
    return merge_reports(reports, counts)


# ---------------------------------------------------------------------------
# Improvement pass (one LLM call per section to redo)


async def improve_section(
    task: dict[str, Any],
    section_body: str,
    issues_for_task: list[dict[str, Any]],
    hallucinations_for_task: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    timeout_seconds: float | None = None,
) -> str:
    llm = get_llm(role="improvement", temperature=0.5, timeout=settings.quality_llm_timeout_seconds)
    response = await asyncio.wait_for(
        llm.ainvoke(
            [
                SystemMessage(content=IMPROVEMENT_SYSTEM),
                HumanMessage(content=build_improvement_prompt(
                    task, section_body, issues_for_task, hallucinations_for_task, evidence,
                )),
            ]
        ),
        timeout=timeout_seconds or settings.quality_llm_timeout_seconds,
    )
    return sanitize_section_markdown(
        content_to_text(response.content),
        str(task.get("title") or ""),
    )


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
    prior_elapsed = float(state.get("quality_elapsed_seconds", 0) or 0)
    started = time.monotonic()
    budget_seconds = max(0, settings.quality_node_timeout_seconds)

    def total_elapsed() -> float:
        return prior_elapsed + (time.monotonic() - started)

    def remaining_budget() -> float:
        if budget_seconds <= 0:
            return float(settings.llm_timeout_seconds)
        return max(0.0, budget_seconds - total_elapsed())

    def elapsed_update() -> State:
        return {"quality_elapsed_seconds": round(total_elapsed(), 3)}

    placeholder_ids = [
        task_id for task_id, body in sections if "_Section unavailable:" in body
    ]
    if placeholder_ids:
        fallback_report = structural_fallback_report(
            plan,
            sections,
            reason="placeholder sections remain",
        )
        log(f"placeholder sections remain {placeholder_ids}; skipping quality LLM")
        return {
            "quality_report": fallback_report.model_dump(),
            "improvement_iter": max(iter_count, settings.quality_max_iterations),
            "warnings": [
                f"quality skipped because placeholder sections remain: {placeholder_ids}"
            ],
            **elapsed_update(),
        }

    # ---- Evaluate
    if run_id:
        await bus.publish(run_id, "node_started", {"node": "quality_eval", "iter": iter_count})
    log(f"evaluating draft (iter={iter_count})")

    try:
        # Pass the whole remaining budget; evaluate_once caps each batch call at
        # the per-call ceiling internally and spends across batches as needed.
        eval_budget = remaining_budget()
        if eval_budget < 5:
            raise asyncio.TimeoutError("quality budget exhausted before evaluation")
        report = await evaluate_once(
            topic,
            plan,
            sections,
            evidence,
            mode,
            timeout_seconds=eval_budget,
        )
    except Exception as exc:  # noqa: BLE001 — evaluator failures shouldn't kill the run
        log(f"evaluator failed: {type(exc).__name__}: {exc}; skipping quality loop")
        # If an earlier iteration already produced a real report, keep it rather
        # than masking it with a synthetic structural one. This is the common
        # free-tier case: iter 0 evaluates + improves fine, but the
        # re-evaluation runs out of the quality budget and times out — we'd
        # rather surface the real prior score than overwrite it.
        prior_report = state.get("quality_report")
        if isinstance(prior_report, dict) and iter_count > 0:
            report_dump = prior_report
            warning = (
                "quality re-evaluation after improvement did not complete "
                f"({type(exc).__name__}); keeping prior score"
            )
        else:
            report_dump = structural_fallback_report(
                plan,
                sections,
                reason=type(exc).__name__,
            ).model_dump()
            warning = f"quality evaluator fallback used: {type(exc).__name__}"

        if run_id:
            await bus.publish(run_id, "warning", {"message": warning})
        return {
            "quality_report": report_dump,
            "improvement_iter": max(iter_count, settings.quality_max_iterations),
            "warnings": [warning],
            **elapsed_update(),
        }

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
        return {"quality_report": report.model_dump(), **elapsed_update()}
    if iter_count >= max_iters:
        log(f"iter cap reached ({max_iters}); accepting draft with score {report.overall_score:.1f}")
        return {
            "quality_report": report.model_dump(),
            "warnings": [
                f"quality below threshold ({report.overall_score:.1f}/{threshold}) after {iter_count} improvement pass(es)"
            ],
            **elapsed_update(),
        }
    if not sections_to_redo:
        log("no sections flagged for redo; accepting draft")
        return {"quality_report": report.model_dump(), **elapsed_update()}

    if budget_seconds > 0 and remaining_budget() < settings.quality_min_improvement_seconds:
        log(
            "quality budget nearly exhausted; accepting draft "
            f"with score {report.overall_score:.1f}"
        )
        return {
            "quality_report": report.model_dump(),
            "warnings": [
                f"quality improvement skipped after {total_elapsed():.0f}s budget with score {report.overall_score:.1f}/{threshold}"
            ],
            **elapsed_update(),
        }

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
            improve_timeout = min(float(settings.quality_llm_timeout_seconds), remaining_budget())
            if improve_timeout < settings.quality_min_improvement_seconds:
                log("quality budget exhausted before next section improvement")
                break
            improved = await improve_section(
                task=task,
                section_body=current,
                issues_for_task=issues_for_task(report, task_id),
                hallucinations_for_task=hallucinations_for_task(report, task_id),
                evidence=evidence,
                timeout_seconds=improve_timeout,
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
        **elapsed_update(),
    }


def should_loop_quality(state: Mapping[str, Any]) -> str:
    """Conditional edge: stay in the loop until threshold or iter cap."""
    if not settings.quality_eval_enabled:
        return "end"

    report = state.get("quality_report")
    iter_count = int(state.get("improvement_iter", 0))
    quality_elapsed = float(state.get("quality_elapsed_seconds", 0) or 0)

    # If no report exists, the node short-circuited (e.g., no sections, no plan,
    # or evaluator failed) — exit.
    if not isinstance(report, dict):
        return "end"

    score = float(report.get("overall_score", 0))
    if score >= settings.quality_threshold:
        return "end"
    if iter_count >= settings.quality_max_iterations:
        return "end"
    if (
        settings.quality_node_timeout_seconds > 0
        and quality_elapsed >= settings.quality_node_timeout_seconds
    ):
        return "end"

    return "loop"
