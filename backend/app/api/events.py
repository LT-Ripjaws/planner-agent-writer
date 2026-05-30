import asyncio
import json
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from backend.app.db import repository
from backend.app.db.base import get_session
from backend.app.db.models import BlogRun
from backend.app.deps import get_bus
from backend.app.services.progress import CLOSE_EVENT, ProgressBus, ProgressEvent

router = APIRouter(prefix="/blog-runs", tags=["blog-runs"])

TERMINAL_STATUSES = {"completed", "completed_with_warnings", "failed"}


def encode_sse(event: ProgressEvent) -> str:
    payload = {
        "data": event.data,
        "created_at": event.created_at,
    }
    return (
        f"id: {event.event_id}\n"
        f"event: {event.event}\n"
        f"data: {json.dumps(payload)}\n\n"
    )


def heartbeat() -> str:
    return ": heartbeat\n\n"


def parse_warnings(value: str | None) -> list[str]:
    if not value:
        return []

    try:
        warnings = json.loads(value)
    except json.JSONDecodeError:
        return []

    if not isinstance(warnings, list):
        return []

    return [str(warning) for warning in warnings]


def parse_plan(value: str | None) -> dict | None:
    if not value:
        return None

    try:
        plan = json.loads(value)
    except json.JSONDecodeError:
        return None

    return plan if isinstance(plan, dict) else None


async def terminal_stream(
    run_id: str,
    status: str,
    *,
    error: str | None,
    warnings: list[str],
) -> AsyncIterator[str]:
    event_name: Literal["error", "done"] = "error" if status == "failed" else "done"
    yield encode_sse(
        ProgressEvent(
            event="status",
            data={
                "run_id": run_id,
                "status": status,
                "error": error,
                "warnings": warnings,
            },
        )
    )
    yield encode_sse(
        ProgressEvent(
            event=event_name,
            data={
                "run_id": run_id,
                "status": status,
                "error": error,
                "warnings": warnings,
            },
        )
    )


def snapshot_for(run: BlogRun) -> dict[str, object]:
    """DB-derived snapshot sent on the initial `status: subscribed` event.

    A late SSE subscriber (curl with a delay, or a frontend tab refresh
    after the run has progressed) won't have seen the original
    ``node_completed`` events. The bus's event buffer replays those, but
    the snapshot gives the client a coherent boot state independent of
    buffer retention.
    """
    snapshot: dict[str, object] = {
        "status": run.status,
        "progress_step": run.progress_step,
        "mode": run.mode,
        "blog_title": run.blog_title,
    }
    if run.status == "awaiting_approval":
        snapshot["plan"] = parse_plan(run.plan_json)

    return snapshot


async def live_stream(
    run_id: str,
    request: Request,
    bus: ProgressBus,
    run: BlogRun,
) -> AsyncIterator[str]:
    queue = await bus.subscribe(run_id)

    try:
        yield encode_sse(
            ProgressEvent(
                event="status",
                data={
                    "run_id": run_id,
                    "status": "subscribed",
                    "snapshot": snapshot_for(run),
                },
            )
        )

        while True:
            if await request.is_disconnected():
                break

            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
            except asyncio.TimeoutError:
                yield heartbeat()
                continue

            if event.event == CLOSE_EVENT:
                break

            yield encode_sse(event)
    finally:
        await bus.unsubscribe(run_id, queue)


@router.get("/{run_id}/events")
async def stream_blog_run_events(
    run_id: str,
    request: Request,
    session: Session = Depends(get_session),
    bus: ProgressBus = Depends(get_bus),
) -> StreamingResponse:
    run = repository.get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Blog run not found")

    if run.status in TERMINAL_STATUSES:
        stream = terminal_stream(
            run_id,
            run.status,
            error=run.error,
            warnings=parse_warnings(run.warnings_json),
        )
    else:
        stream = live_stream(run_id, request, bus, run)

    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
