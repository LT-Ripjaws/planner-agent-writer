"""Process-lifetime singletons that need lifecycle hooks (setup/teardown).

The progress bus is a stateless singleton created at import time (`services/progress.py`),
so it doesn't live here. The LangGraph checkpointer holds an open SQLite connection
that needs to be opened in `main.py`'s lifespan and closed on shutdown — that's what
this module holds.

Pattern: `main.py` calls `set_checkpointer(...)` during lifespan startup and
`set_checkpointer(None)` during teardown. The runner reads via `get_checkpointer()`.
`None` is a valid value — graph compiles without a checkpointer in that case
(used by `scripts/run_once.py` and tests).
"""
from __future__ import annotations

from typing import Optional

from langgraph.checkpoint.base import BaseCheckpointSaver

_checkpointer: Optional[BaseCheckpointSaver] = None


def set_checkpointer(checkpointer: Optional[BaseCheckpointSaver]) -> None:
    global _checkpointer
    _checkpointer = checkpointer


def get_checkpointer() -> Optional[BaseCheckpointSaver]:
    return _checkpointer
