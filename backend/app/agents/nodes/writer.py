import asyncio
import json
import sys
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.agents.prompts import WRITER_SYSTEM, wrap_untrusted
from backend.app.agents.state import Plan, State, Task
from backend.app.services.llm import get_llm


def log(message: str) -> None:
    print(f"[writer] {message}", file=sys.stderr, flush=True)


def require_task(state: State) -> Task:
    task = state.get("task")
    if task is None:
        raise ValueError("State is missing required field: task")

    return Task.model_validate(task)


def require_plan(state: State) -> Plan:
    plan = state.get("plan")
    if plan is None:
        raise ValueError("State is missing required field: plan")

    return Plan.model_validate(plan)


def content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            else:
                parts.append(str(item))

        return "\n".join(parts)

    return str(content)


def build_writer_prompt(state: State, task: Task, plan: Plan) -> str:
    evidence = state.get("evidence", [])
    evidence_block = (
        "\n\n" + wrap_untrusted("evidence", json.dumps(evidence[:16], indent=2))
        if evidence
        else ""
    )
    return f"""
Blog title: {plan.blog_title}
{wrap_untrusted("user_topic", state.get("topic", ""))}

Audience: {plan.audience}
Tone: {plan.tone}
Mode: {state.get("mode", "closed_book")}
As of date: {state.get("as_of", "unknown")}

{wrap_untrusted("task", task.model_dump_json(indent=2))}{evidence_block}

Write only this section.
""".strip()


def placeholder_section(task: Task, reason: str) -> State:
    """Non-fatal failure path for the writer node.

    Returns a stub section that preserves task ordering and surfaces the
    failure to the reducer/runner via the ``warnings`` aggregator. The
    graph still completes; downstream code can decide whether a run with
    placeholders should be considered ``completed`` or ``failed``.
    """
    body = f"## {task.title}\n\n_Section unavailable: {reason}._"
    return {
        "sections": [(task.id, body)],
        "warnings": [f"writer task={task.id} ({task.title}): {reason}"],
    }


async def writer_node(state: State) -> State:
    task = require_task(state)
    plan = require_plan(state)
    llm = get_llm(temperature=0.7)
    timeout_seconds = state.get("writer_timeout_seconds", 360)

    log(
        f"start task={task.id} title={task.title!r} "
        f"target_words={task.target_words} timeout={timeout_seconds}s"
    )
    started = time.monotonic()

    try:
        response = await asyncio.wait_for(
            llm.ainvoke(
                [
                    SystemMessage(content=WRITER_SYSTEM),
                    HumanMessage(content=build_writer_prompt(state, task, plan)),
                ]
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - started
        reason = f"timeout after {timeout_seconds}s"
        log(f"timeout task={task.id} after={elapsed:.1f}s")
        return placeholder_section(task, reason)
    except Exception as exc:  # noqa: BLE001 — surface any provider error as a placeholder
        elapsed = time.monotonic() - started
        reason = f"{type(exc).__name__}: {exc}"
        log(f"error task={task.id} after={elapsed:.1f}s reason={reason}")
        return placeholder_section(task, reason)

    markdown = content_to_text(response.content).strip()
    elapsed = time.monotonic() - started
    log(f"done task={task.id} elapsed={elapsed:.1f}s chars={len(markdown)}")
    return {
        "sections": [(task.id, markdown)],
    }
