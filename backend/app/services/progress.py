import asyncio
from collections import defaultdict, deque
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

CLOSE_EVENT: Literal["__close__"] = "__close__"

# Bounded per-run history. A normal 7-section run publishes ~25 events
# (router/planner pairs + 6 writers × 2 + 6 section events + reducer + status).
# 100 leaves comfortable headroom for resume sessions and unusual paths
# without unbounded memory growth.
BUFFER_MAX = 100


@dataclass(frozen=True)
class ProgressEvent:
    event: ProgressEventType | Literal["__close__"]
    data: dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ProgressBus:
    """Per-run pub/sub bus with bounded event history.

    Each ``run_id`` has its own subscribers and its own ring buffer. Late
    subscribers (e.g., SSE connecting after the runner has already published
    several events) receive a replay of the buffered events on
    ``subscribe()`` before live events start arriving. This closes the
    race window between ``runner.execute`` kicking off the graph and the
    frontend opening its EventSource.

    Buffer is cleared on ``close()`` because subsequent subscribers for the
    same run hit the terminal-state DB-snapshot path in ``api/events.py``
    rather than re-attaching to the bus.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[ProgressEvent]]] = defaultdict(set)
        self._buffer: dict[str, deque[ProgressEvent]] = defaultdict(
            lambda: deque(maxlen=BUFFER_MAX)
        )
        self._lock = asyncio.Lock()

    async def publish(
        self,
        run_id: str,
        event: ProgressEventType,
        data: dict[str, Any] | None = None,
    ) -> None:
        progress_event = ProgressEvent(event=event, data=data or {})

        async with self._lock:
            # Append to history first so a subscriber that arrives between
            # this publish and any future one still sees this event.
            self._buffer[run_id].append(progress_event)
            queues = list(self._subscribers.get(run_id, set()))

        for queue in queues:
            await queue.put(progress_event)

    async def subscribe(self, run_id: str) -> asyncio.Queue[ProgressEvent]:
        queue: asyncio.Queue[ProgressEvent] = asyncio.Queue()

        async with self._lock:
            # Replay buffered events FIRST, then register the subscriber.
            # Doing both inside the lock prevents an interleaving publish()
            # from delivering a live event before the historical ones.
            # ``put_nowait`` is safe because the queue is unbounded.
            for event in self._buffer.get(run_id, ()):
                queue.put_nowait(event)
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
        close_event = ProgressEvent(event=CLOSE_EVENT, data={})

        async with self._lock:
            queues = list(self._subscribers.pop(run_id, set()))
            # Run is terminal — any future SSE subscribers go through the
            # DB-snapshot path in events.py, so buffered history is no
            # longer useful and is dropped to free memory.
            self._buffer.pop(run_id, None)

        for queue in queues:
            await queue.put(close_event)


progress_bus = ProgressBus()


def get_progress_bus() -> ProgressBus:
    return progress_bus
