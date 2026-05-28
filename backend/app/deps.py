"""Shared FastAPI dependencies and process-level singletons.

The slowapi `Limiter` lives here (not in `main.py`) so route modules can
import it without creating a circular import (main itself imports the
route modules).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.services.progress import ProgressBus, get_progress_bus

# Shared rate-limit instance. Endpoints opt in via `@limiter.limit(...)`.
limiter = Limiter(key_func=get_remote_address)


def get_bus() -> ProgressBus:
    return get_progress_bus()
