import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

ProgressEventType = Literal[
    "status",
    "node_started",
    "node_completed",
    "section",
    "warning",
    "done",
    "error",
]

_CLOSE_EVENT = "__close__"


@dataclass(frozen=True)
class ProgressEvent:
    event: ProgressEventType | Literal["__close__"]
    data: dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ProgressBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[ProgressEvent]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def publish(
        self,
        run_id: str,
        event: ProgressEventType,
        data: dict[str, Any] | None = None,
    ) -> None:
        progress_event = ProgressEvent(event=event, data=data or {})

        async with self._lock:
            queues = list(self._subscribers.get(run_id, set()))

        for queue in queues:
            await queue.put(progress_event)

    async def subscribe(self, run_id: str) -> asyncio.Queue[ProgressEvent]:
        queue: asyncio.Queue[ProgressEvent] = asyncio.Queue()

        async with self._lock:
            self._subscribers[run_id].add(queue)

        return queue

    async def unsubscribe(
        self,
        run_id: str,
        queue: asyncio.Queue[ProgressEvent],
    ) -> None:
        async with self._lock:
            queues = self._subscribers.get(run_id)
            if queues is None:
                return

            queues.discard(queue)

            if not queues:
                self._subscribers.pop(run_id, None)

    async def close(self, run_id: str) -> None:
        close_event = ProgressEvent(event=_CLOSE_EVENT, data={})

        async with self._lock:
            queues = list(self._subscribers.pop(run_id, set()))

        for queue in queues:
            await queue.put(close_event)


progress_bus = ProgressBus()


def get_progress_bus() -> ProgressBus:
    return progress_bus
