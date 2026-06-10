import asyncio
import json
import sys
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.agents.markdown_sanitize import (
    clean_title,
    compact_evidence_for_prompt,
    sanitize_section_markdown,
)
from backend.app.agents.prompts import WRITER_SYSTEM, wrap_untrusted
from backend.app.agents.state import Plan, State, Task
from backend.app.core.config import settings
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


def is_transient_provider_error(exc: Exception) -> bool:
    text = str(exc)
    return (
        "Provider returned error" in text
        or "'code': 504" in text
        or '"code": 504' in text
        or "'code': 524" in text
        or '"code": 524' in text
        or "'code': 429" in text
        or '"code": 429' in text
    )


def build_writer_prompt(state: State, task: Task, plan: Plan) -> str:
    evidence = compact_evidence_for_prompt(list(state.get("evidence", [])))
    evidence_block = (
        "\n\n" + wrap_untrusted("evidence", json.dumps(evidence, ensure_ascii=False))
        if evidence
        else ""
    )
    grounding_note = ""
    if task.requires_citations:
        grounding_note = (
            "\n\nGrounding note: this section requires citations. Use concrete "
            "real-world examples only when they are supported by the evidence. "
            "If you need an illustrative example that is not in the evidence, "
            "make it clearly hypothetical and do not present it as a real event."
        )
    return f"""
Blog title: {plan.blog_title}
{wrap_untrusted("user_topic", state.get("topic", ""))}

Audience: {plan.audience}
Tone: {plan.tone}
Mode: {state.get("mode", "closed_book")}
As of date: {state.get("as_of", "unknown")}

{wrap_untrusted("task", task.model_dump_json(indent=2))}{evidence_block}

Write only this section.{grounding_note}
""".strip()


def placeholder_section(task: Task, reason: str) -> State:
    """Non-fatal failure path for the writer node.

    Returns a stub section that preserves task ordering and surfaces the
    failure to the reducer/runner via the ``warnings`` aggregator. The
    graph still completes; downstream code can decide whether a run with
    placeholders should be considered ``completed`` or ``failed``.
    """
    body = f"## {clean_title(task.title, fallback='Section')}\n\n_Section unavailable: {reason}._"
    return {
        "sections": [(task.id, body)],
        "warnings": [f"writer task={task.id} ({task.title}): {reason}"],
    }


async def invoke_writer_with_retry(
    llm: Any,
    messages: list[SystemMessage | HumanMessage],
    *,
    task: Task,
    started: float,
    timeout_seconds: int,
) -> Any:
    last_exc: Exception | None = None
    for attempt in range(1, 3):
        elapsed = time.monotonic() - started
        remaining = timeout_seconds - elapsed
        if remaining <= 0:
            raise asyncio.TimeoutError

        try:
            return await asyncio.wait_for(
                llm.ainvoke(messages),
                timeout=remaining,
            )
        except asyncio.TimeoutError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            elapsed = time.monotonic() - started
            remaining = timeout_seconds - elapsed
            if attempt == 1 and is_transient_provider_error(exc) and remaining > 1:
                log(
                    f"retrying task={task.id} after transient provider error "
                    f"elapsed={elapsed:.1f}s reason={type(exc).__name__}: {exc}"
                )
                await asyncio.sleep(min(1, remaining))
                continue
            raise

    raise RuntimeError(f"writer retry exhausted: {last_exc}")


async def writer_node(state: State) -> State:
    task = require_task(state)
    plan = require_plan(state)
    llm = get_llm(role="writer", temperature=0.7)
    timeout_seconds = state.get("writer_timeout_seconds", settings.writer_timeout_seconds)

    log(
        f"start task={task.id} title={task.title!r} "
        f"target_words={task.target_words} timeout={timeout_seconds}s"
    )
    started = time.monotonic()

    try:
        response = await invoke_writer_with_retry(
            llm,
            [
                SystemMessage(content=WRITER_SYSTEM),
                HumanMessage(content=build_writer_prompt(state, task, plan)),
            ],
            task=task,
            started=started,
            timeout_seconds=timeout_seconds,
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

    markdown = sanitize_section_markdown(content_to_text(response.content), task.title)
    elapsed = time.monotonic() - started
    log(f"done task={task.id} elapsed={elapsed:.1f}s chars={len(markdown)}")
    return {
        "sections": [(task.id, markdown)],
    }
