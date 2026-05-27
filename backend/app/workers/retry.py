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


def _drop_warnings_for(warnings: list[str], retried_task_ids: set[int]) -> list[str]:
    """Remove writer warnings whose task id is in ``retried_task_ids``.

    Warning format from `writer_node.placeholder_section`:
        "writer task=N (Title): reason"
    """
    kept: list[str] = []
    for warning in warnings:
        # Find "task=N" anywhere in the warning text
        if "writer task=" in warning:
            try:
                # crude but stable parser; matches "writer task=N "
                after = warning.split("writer task=", 1)[1]
                task_id_str = after.split(" ", 1)[0].rstrip(":")
                task_id = int(task_id_str)
                if task_id in retried_task_ids:
                    continue
            except (ValueError, IndexError):
                pass
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
            "writer_timeout_seconds": state.get("writer_timeout_seconds", 360),
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
        return {}

    cleaned_warnings = _drop_warnings_for(
        [str(w) for w in state.get("warnings", [])],
        succeeded_task_ids,
    )
    new_final = _rebuild_final(plan if isinstance(plan, dict) else None, new_sections)

    return {
        "sections": new_sections,
        "warnings": cleaned_warnings,
        "final": new_final,
    }
