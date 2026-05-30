import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langgraph.types import StateSnapshot
from sqlmodel import Session

from backend.app.agents.graph import build_graph
from backend.app.agents.state import Plan, State
from backend.app.core.config import settings
from backend.app.db import repository
from backend.app.db.base import engine
from backend.app.db.models import BlogRun
from backend.app.services.progress import ProgressBus, get_progress_bus
from backend.app.services.runtime import get_checkpointer
from backend.app.workers.retry import retry_placeholders

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GraphRunResult:
    status: Literal["complete", "paused"]
    state: Mapping[str, Any]
    snapshot: StateSnapshot | None = None


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


def graph_config(run_id: str, checkpointer: object | None) -> RunnableConfig:
    if checkpointer is not None:
        return {
            "max_concurrency": 3,
            "configurable": {"thread_id": run_id},
        }

    return {"max_concurrency": 3}


def snapshot_values(
    snapshot: StateSnapshot,
    fallback: Mapping[str, Any],
) -> Mapping[str, Any]:
    return snapshot.values if isinstance(snapshot.values, Mapping) else fallback


async def _stream_graph(
    run_id: str,
    initial_state: State | None,
    bus: ProgressBus,
) -> GraphRunResult:
    """Stream the graph until completion or a LangGraph interrupt.

    ``initial_state=None`` resumes from the checkpointer's saved state
    (LangGraph behavior: passing ``None`` plus an existing thread_id continues
    from the last persisted node).
    """
    checkpointer = get_checkpointer()
    graph = build_graph(
        bus,
        checkpointer=checkpointer,
        hitl_plan_approval=settings.hitl_plan_approval_enabled,
    )
    config = graph_config(run_id, checkpointer)

    final_state: Mapping[str, Any] = {}
    async for snapshot in graph.astream(
        initial_state,
        config=config,
        stream_mode="values",
    ):
        final_state = snapshot
        persist_partial(run_id, snapshot)

    if checkpointer is not None:
        state_snapshot = await graph.aget_state(config)
        if state_snapshot.next:
            paused_state = snapshot_values(state_snapshot, final_state)
            persist_partial(run_id, paused_state)
            return GraphRunResult(
                status="paused",
                state=paused_state,
                snapshot=state_snapshot,
            )

    return GraphRunResult(status="complete", state=final_state)


async def _pause_for_plan_approval(
    run_id: str,
    state: Mapping[str, Any],
    bus: ProgressBus,
) -> None:
    plan = state.get("plan")
    if not isinstance(plan, dict):
        raise RuntimeError("graph paused for plan approval without a plan")

    with Session(engine) as session:
        run = repository.get_run(session, run_id)
        if run is None:
            raise RuntimeError("blog run disappeared before plan approval pause")

        repository.save_plan(session, run, plan)
        repository.mark_awaiting_approval(session, run)

    await bus.publish(
        run_id,
        "status",
        {
            "status": "awaiting_approval",
            "progress_step": "awaiting_plan_approval",
        },
    )
    await bus.publish(
        run_id,
        "awaiting_input",
        {
            "type": "plan_approval",
            "plan": plan,
        },
    )


async def _mark_failed_and_publish(
    run_id: str,
    reason: str,
    bus: ProgressBus,
) -> None:
    with Session(engine) as session:
        run = repository.get_run(session, run_id)
        if run is not None:
            repository.mark_failed(session, run, reason)

    await bus.publish(run_id, "status", {"status": "failed"})
    await bus.publish(run_id, "error", {"reason": reason})


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


async def _drive_graph(
    run_id: str,
    initial_state: State | None,
    *,
    allow_pause: bool = True,
) -> None:
    """Run a graph with all safety nets, then finalize.

    Used by both ``execute()`` (fresh runs) and ``resume()`` (continue from
    checkpoint). The caller is responsible for marking the row ``running``
    and emitting the initial ``status`` event before calling this.
    """
    bus = get_progress_bus()
    close_bus = True

    try:
        result = await asyncio.wait_for(
            _stream_graph(run_id, initial_state, bus),
            timeout=settings.run_fallback_timeout_seconds,
        )
        if result.status == "paused":
            if not allow_pause:
                raise RuntimeError("graph paused unexpectedly after plan approval")

            await _pause_for_plan_approval(run_id, result.state, bus)
            close_bus = False
            return

        await _finalize_run(run_id, result.state, bus)
    except asyncio.TimeoutError:
        reason = (
            f"run exceeded fallback timeout of "
            f"{settings.run_fallback_timeout_seconds}s"
        )
        logger.error("Blog run %s timed out: %s", run_id, reason)
        await _mark_failed_and_publish(run_id, reason, bus)
    except Exception as exc:
        logger.exception("Blog run %s failed", run_id)
        reason = f"{type(exc).__name__}: {exc}"
        await _mark_failed_and_publish(run_id, reason, bus)
    finally:
        if close_bus:
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


async def continue_after_approval(
    run_id: str,
    action: str,
    plan: dict[str, Any] | None = None,
) -> None:
    """Continue or terminate a run currently paused after the planner."""
    bus = get_progress_bus()

    if action == "reject":
        with Session(engine) as session:
            run = repository.get_run(session, run_id)
            if run is None or run.status != "awaiting_approval":
                return

            repository.mark_failed(session, run, "user rejected plan")

        await bus.publish(run_id, "status", {"status": "failed"})
        await bus.publish(run_id, "error", {"reason": "user rejected plan"})
        await bus.close(run_id)
        return

    if action != "approve":
        await _mark_failed_and_publish(
            run_id,
            f"unsupported plan approval action: {action}",
            bus,
        )
        await bus.close(run_id)
        return

    try:
        validated_plan = (
            Plan.model_validate(plan).model_dump()
            if plan is not None
            else None
        )
        checkpointer = get_checkpointer()
        if checkpointer is None:
            raise RuntimeError("cannot approve plan without a LangGraph checkpointer")

        graph = build_graph(
            bus,
            checkpointer=checkpointer,
            hitl_plan_approval=settings.hitl_plan_approval_enabled,
        )
        config = graph_config(run_id, checkpointer)

        with Session(engine) as session:
            run = repository.get_run(session, run_id)
            if run is None or run.status != "awaiting_approval":
                return

            if validated_plan is not None:
                run = repository.save_plan(session, run, validated_plan)

            repository.mark_running(session, run)

        if validated_plan is not None:
            await graph.aupdate_state(
                config,
                {"plan": validated_plan},
                as_node="planner",
            )

        await bus.publish(
            run_id,
            "status",
            {
                "status": "running",
                "approved": True,
                "edited": validated_plan is not None,
            },
        )
        await _drive_graph(run_id, None, allow_pause=False)
    except Exception as exc:
        logger.exception("Blog run %s failed while handling plan approval", run_id)
        reason = f"{type(exc).__name__}: {exc}"
        await _mark_failed_and_publish(run_id, reason, bus)
        await bus.close(run_id)
