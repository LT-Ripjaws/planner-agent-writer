"""Post-graph placeholder retry pass.

When `writer_node` fails (timeout, 524, any provider exception) it returns a
non-fatal placeholder section so the graph can complete. This module runs
after `graph.astream` finishes, finds any sections still marked as placeholders,
re-invokes the writer logic one more time per failed section, and splices
successful retries back into the state.

Bounded: at most one retry per section. If the retry also produces a placeholder
or raises, the original placeholder is kept and the warning stays.

This is intentionally a post-graph pass (not a graph node) so it doesn't
complicate the LangGraph fanout/reduce semantics. The runner calls it, then
re-runs the reducer logic on the updated sections to regenerate `final`.
"""
from __future__ import annotations

import logging
import sys
from collections.abc import Mapping
from typing import Any

from backend.app.agents.state import State
from backend.app.agents.nodes.writer import writer_node
from backend.app.core.config import settings
from backend.app.services.progress import ProgressBus

logger = logging.getLogger(__name__)

PLACEHOLDER_MARKER = "_Section unavailable:"


def log(message: str) -> None:
    print(f"[retry] {message}", file=sys.stderr, flush=True)


def _section_is_placeholder(body: str) -> bool:
    return PLACEHOLDER_MARKER in body


def _find_placeholder_task_ids(sections: list[tuple[int, str]]) -> list[int]:
    return [task_id for task_id, body in sections if _section_is_placeholder(body)]


def _tasks_by_id(plan: dict[str, Any] | None) -> dict[int, dict[str, Any]]:
    if not isinstance(plan, dict):
        return {}
    tasks = plan.get("tasks") or []
    return {task["id"]: task for task in tasks if isinstance(task, dict) and "id" in task}


def _rebuild_final(plan: dict[str, Any] | None, sections: list[tuple[int, str]]) -> str:
    title = "Untitled"
    if isinstance(plan, dict) and isinstance(plan.get("blog_title"), str):
        title = plan["blog_title"]

    ordered = [body for _, body in sorted(sections, key=lambda item: item[0])]
    body = "\n\n".join(s.strip() for s in ordered if s.strip())
    return f"# {title}\n\n{body}".strip()


def _writer_warning_task_id(warning: str) -> int | None:
    """Parse the task id out of a writer placeholder warning, or None.

    Warning format from `writer_node.placeholder_section`:
        "writer task=N (Title): reason"
    """
    if "writer task=" not in warning:
        return None
    try:
        after = warning.split("writer task=", 1)[1]
        return int(after.split(" ", 1)[0].rstrip(":"))
    except (ValueError, IndexError):
        return None


def finalize_warnings(state: Mapping[str, Any]) -> list[str]:
    """Authoritative warning list for a finished run.

    ``State.warnings`` is an ``operator.add`` channel, so nodes can append but
    never remove. Two artifacts therefore need cleaning once the graph is done:

    1. A ``writer task=N ... timeout/error`` warning whose section was later
       recovered (placeholder retry, or a quality improvement pass) is stale —
       drop it when section N is present and no longer a placeholder.
    2. Nodes that run more than once (citation_guard re-runs inside the quality
       loop) can append an identical warning repeatedly — dedupe, preserving
       first-seen order.
    """
    sections = {task_id: body for task_id, body in state.get("sections", [])}
    seen: set[str] = set()
    kept: list[str] = []
    for raw in state.get("warnings", []):
        warning = str(raw)
        task_id = _writer_warning_task_id(warning)
        if task_id is not None:
            body = sections.get(task_id)
            if body is not None and PLACEHOLDER_MARKER not in body:
                continue  # section was recovered; the warning is stale
        if warning in seen:
            continue
        seen.add(warning)
        kept.append(warning)
    return kept


async def retry_placeholders(
    run_id: str,
    state: Mapping[str, Any],
    bus: ProgressBus | None = None,
) -> dict[str, Any]:
    """One-shot retry for placeholder sections.

    Returns an update dict suitable for merging into the final graph state:
    ``{"sections": [...], "warnings": [...], "final": "..."}`` if anything
    was retried successfully, otherwise an empty dict.
    """
    sections: list[tuple[int, str]] = list(state.get("sections", []))
    if not sections:
        return {}

    placeholder_ids = _find_placeholder_task_ids(sections)
    if not placeholder_ids:
        return {}

    plan = state.get("plan")
    tasks = _tasks_by_id(plan if isinstance(plan, dict) else None)

    log(f"found {len(placeholder_ids)} placeholder section(s); attempting one retry each")
    if bus is not None:
        await bus.publish(
            run_id,
            "warning",
            {"message": f"Retrying {len(placeholder_ids)} placeholder section(s)"},
        )

    succeeded_task_ids: set[int] = set()
    new_sections: list[tuple[int, str]] = list(sections)

    for task_id in placeholder_ids:
        task = tasks.get(task_id)
        if task is None:
            log(f"task={task_id} not found in plan; skipping")
            continue

        retry_input: State = {
            "run_id": run_id,
            "topic": state.get("topic", ""),
            "audience": state.get("audience"),
            "tone": state.get("tone", "neutral"),
            "blog_kind": state.get("blog_kind", "auto"),
            "research_mode": state.get("research_mode", "auto"),
            "mode": state.get("mode", "closed_book"),
            "as_of": state.get("as_of", ""),
            "recency_days": state.get("recency_days", 3650),
            "evidence": state.get("evidence", []),
            "plan": plan,
            "task": task,
            "writer_timeout_seconds": state.get(
                "writer_timeout_seconds",
                settings.writer_timeout_seconds,
            ),
        }

        try:
            result = await writer_node(retry_input)
        except Exception as exc:  # noqa: BLE001 — defensive; writer_node should already handle this
            log(f"task={task_id} retry raised {type(exc).__name__}: {exc}")
            continue

        new_pair = (result.get("sections") or [None])[0]
        if not new_pair:
            continue

        _, new_body = new_pair
        if _section_is_placeholder(new_body):
            log(f"task={task_id} retry still produced a placeholder; keeping original")
            continue

        log(f"task={task_id} retry succeeded; splicing in {len(new_body)} chars")
        new_sections = [
            (tid, new_body) if tid == task_id else (tid, body)
            for tid, body in new_sections
        ]
        succeeded_task_ids.add(task_id)

    if not succeeded_task_ids:
        return {"placeholder_retry_attempted": True}

    new_final = _rebuild_final(plan if isinstance(plan, dict) else None, new_sections)

    # NOTE: `State.warnings` is an `operator.add` channel — returning a filtered
    # list here would *append* it (re-adding the resolved warning and
    # duplicating the rest). We add nothing; the stale warning for a recovered
    # section is pruned authoritatively by `finalize_warnings()` at run end.
    return {
        "sections": new_sections,
        "warnings": [],
        "final": new_final,
        "placeholder_retry_attempted": True,
    }
