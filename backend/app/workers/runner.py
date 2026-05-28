import asyncio
import logging
from collections.abc import Mapping
from typing import Any

from langchain_core.runnables import RunnableConfig
from sqlmodel import Session

from backend.app.agents.graph import build_graph
from backend.app.agents.state import State
from backend.app.core.config import settings
from backend.app.db import repository
from backend.app.db.base import engine
from backend.app.db.models import BlogRun
from backend.app.services.progress import ProgressBus, get_progress_bus
from backend.app.services.runtime import get_checkpointer
from backend.app.workers.retry import retry_placeholders

logger = logging.getLogger(__name__)


def build_initial_state(run: BlogRun) -> State:
    return {
        "run_id": run.id,
        "topic": run.topic,
        "audience": run.audience,
        "tone": run.tone,
        "blog_kind": run.blog_kind,
        "research_mode": run.research_mode,
        "writer_timeout_seconds": 360,
    }


def progress_step_from_state(state: Mapping[str, Any]) -> str:
    if state.get("final"):
        return "reducer"

    if state.get("sections"):
        return "writer"

    if state.get("plan"):
        return "planner"

    if state.get("evidence"):
        return "research"

    if state.get("mode"):
        return "router"

    return "running"


def persist_partial(run_id: str, state: Mapping[str, Any]) -> None:
    with Session(engine) as session:
        run = repository.get_run(session, run_id)
        if run is None:
            return

        step = progress_step_from_state(state)
        if run.progress_step != step:
            run = repository.update_step(session, run, step)

        mode = state.get("mode")
        if isinstance(mode, str) and mode and run.mode != mode:
            run = repository.save_mode(session, run, mode)

        plan = state.get("plan")
        if isinstance(plan, dict):
            run = repository.save_plan(session, run, plan)

        evidence = state.get("evidence")
        if isinstance(evidence, list):
            run = repository.save_evidence(session, run, evidence)

        final = state.get("final")
        if isinstance(final, str) and final:
            run = repository.save_markdown(session, run, final)

        warnings = state.get("warnings")
        if isinstance(warnings, list):
            repository.save_warnings(session, run, [str(warning) for warning in warnings])

        quality_report = state.get("quality_report")
        if isinstance(quality_report, dict):
            repository.save_quality_report(session, run, quality_report)


async def _stream_graph(
    run_id: str,
    initial_state: State | None,
    bus: ProgressBus,
) -> Mapping[str, Any]:
    """Stream the graph to completion; return the final state snapshot.

    ``initial_state=None`` resumes from the checkpointer's saved state
    (LangGraph behavior: passing ``None`` plus an existing thread_id continues
    from the last persisted node).
    """
    checkpointer = get_checkpointer()
    graph = build_graph(bus, checkpointer=checkpointer)

    config: RunnableConfig = (
        {
            "max_concurrency": 3,
            "configurable": {"thread_id": run_id},
        }
        if checkpointer is not None
        else {"max_concurrency": 3}
    )

    final_state: Mapping[str, Any] = {}
    async for snapshot in graph.astream(
        initial_state,
        config=config,
        stream_mode="values",
    ):
        final_state = snapshot
        persist_partial(run_id, snapshot)

    return final_state


async def _finalize_run(
    run_id: str,
    final_state: Mapping[str, Any],
    bus: ProgressBus,
) -> None:
    """Post-graph: placeholder retry, persist, mark completed, emit terminal events."""
    retry_update = await retry_placeholders(run_id, final_state, bus)
    if retry_update:
        final_state = {**final_state, **retry_update}
        persist_partial(run_id, final_state)
        await bus.publish(
            run_id,
            "node_completed",
            {"node": "retry", "recovered": True},
        )

    final = str(final_state.get("final", "")).strip()
    warnings = [str(warning) for warning in final_state.get("warnings", [])]

    with Session(engine) as session:
        run = repository.get_run(session, run_id)
        if run is None:
            return

        repository.mark_completed(
            session,
            run,
            final,
            with_warnings=bool(warnings),
        )
        # Keep persisted warnings in sync with post-retry state.
        repository.save_warnings(session, run, warnings)

    status = "completed_with_warnings" if warnings else "completed"
    await bus.publish(
        run_id,
        "status",
        {"status": status, "warnings_count": len(warnings)},
    )
    await bus.publish(run_id, "done", {"status": status})


async def _drive_graph(run_id: str, initial_state: State | None) -> None:
    """Run a graph with all safety nets, then finalize.

    Used by both ``execute()`` (fresh runs) and ``resume()`` (continue from
    checkpoint). The caller is responsible for marking the row ``running``
    and emitting the initial ``status`` event before calling this.
    """
    bus = get_progress_bus()

    try:
        final_state = await asyncio.wait_for(
            _stream_graph(run_id, initial_state, bus),
            timeout=settings.run_fallback_timeout_seconds,
        )
        await _finalize_run(run_id, final_state, bus)
    except asyncio.TimeoutError:
        reason = (
            f"run exceeded fallback timeout of "
            f"{settings.run_fallback_timeout_seconds}s"
        )
        logger.error("Blog run %s timed out: %s", run_id, reason)

        with Session(engine) as session:
            run = repository.get_run(session, run_id)
            if run is not None:
                repository.mark_failed(session, run, reason)

        await bus.publish(run_id, "status", {"status": "failed"})
        await bus.publish(run_id, "error", {"reason": reason})
    except Exception as exc:
        logger.exception("Blog run %s failed", run_id)
        reason = f"{type(exc).__name__}: {exc}"

        with Session(engine) as session:
            run = repository.get_run(session, run_id)
            if run is not None:
                repository.mark_failed(session, run, reason)

        await bus.publish(run_id, "status", {"status": "failed"})
        await bus.publish(run_id, "error", {"reason": reason})
    finally:
        await bus.close(run_id)


async def execute(run_id: str) -> None:
    """Start a fresh blog run from a ``queued`` row."""
    bus = get_progress_bus()

    with Session(engine) as session:
        run = repository.get_run(session, run_id)
        if run is None:
            return

        run = repository.mark_running(session, run)
        initial_state = build_initial_state(run)

    await bus.publish(run_id, "status", {"status": "running"})
    await _drive_graph(run_id, initial_state)


async def resume(run_id: str) -> None:
    """Resume a previously failed run.

    If a LangGraph checkpoint exists for this run's ``thread_id``, the graph
    continues from the last completed node (no LLM cost for the work already
    done). If no checkpoint exists — e.g., the original run crashed before any
    node finished — we restart from scratch using the saved DB row.
    """
    bus = get_progress_bus()

    with Session(engine) as session:
        run = repository.get_run(session, run_id)
        if run is None:
            return

        # Clear the prior failure reason before re-engaging.
        run.error = None
        session.add(run)
        session.commit()
        session.refresh(run)

        run = repository.mark_running(session, run)
        # Hold an initial_state in case the checkpointer has nothing for us.
        fallback_state = build_initial_state(run)

    # Probe for an existing checkpoint to decide between resume vs restart.
    use_checkpoint = False
    checkpointer = get_checkpointer()
    if checkpointer is not None:
        try:
            saved = await checkpointer.aget({"configurable": {"thread_id": run_id}})
            use_checkpoint = saved is not None
        except Exception:
            logger.exception("Failed to probe checkpoint for run %s", run_id)
            use_checkpoint = False

    if use_checkpoint:
        logger.info("Resuming blog run %s from checkpoint", run_id)
        await bus.publish(run_id, "status", {"status": "running", "resumed": True})
        await _drive_graph(run_id, None)
    else:
        logger.info("No checkpoint for blog run %s; restarting from scratch", run_id)
        await bus.publish(run_id, "status", {"status": "running", "resumed": False})
        await _drive_graph(run_id, fallback_state)
