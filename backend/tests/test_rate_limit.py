"""T2 (cont.) — slowapi rate-limit enforcement, in isolation.

This file deliberately omits `from __future__ import annotations`: FastAPI must
resolve the route's `request: Request` annotation to the real class at decoration
time. Under PEP 563 stringized annotations it would instead treat `request` as a
request body and return 422 before the limiter ever runs.

The route is built on its own app + a fresh `Limiter` so it doesn't perturb the
global in-memory limit state shared by the main app's tests.
"""
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address


def test_rate_limit_enforced_with_low_cap():
    limiter = Limiter(key_func=get_remote_address)
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.post("/thing")
    @limiter.limit("2/minute")
    def make_thing(request: Request):
        return {"ok": True}

    client = TestClient(app)
    statuses = [client.post("/thing").status_code for _ in range(3)]
    assert statuses[0] == 200
    assert statuses[1] == 200
    assert statuses[2] == 429
