"""Shared fixtures. Sets a clean test environment BEFORE importing the app.

All LLM/Tavily access is faked in the individual tests, so no env keys are
required for real providers. We point the database at a throwaway temp file
per test session and override the FastAPI `get_session` dependency.
"""
from __future__ import annotations

import os
from collections.abc import Generator, Iterator

import pytest

# Configure env before any `backend.app.*` import reads settings.
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("TAVILY_API_KEY", "test-key")
os.environ.setdefault("RATE_LIMIT_RUNS_PER_MIN", "1000")
os.environ.setdefault("QUALITY_EVAL_ENABLED", "false")
os.environ.setdefault("HITL_PLAN_APPROVAL_ENABLED", "false")
os.environ.setdefault("OPENROUTER_API_KEY", "")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("LLM_FALLBACK_ENABLED", "false")


@pytest.fixture
def db_engine(tmp_path):
    """A fresh SQLite engine on a temp file with the schema created."""
    from sqlmodel import SQLModel, create_engine

    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(db_engine) -> Iterator:
    from sqlmodel import Session

    with Session(db_engine) as session:
        yield session


@pytest.fixture
def client(db_engine) -> Generator:
    """A TestClient with `get_session` pointed at the temp DB.

    We do NOT enter the app lifespan (which would open the LangGraph
    checkpointer and run startup sweeps); the REST endpoints under test only
    need the DB session. Background tasks (`runner.execute`) are neutralized
    so a POST doesn't try to reach a real LLM.
    """
    from fastapi.testclient import TestClient
    from sqlmodel import Session

    from backend.app.db.base import get_session
    from backend.app.main import app
    from backend.app.workers import runner

    def override_get_session() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    # Neutralize background execution: the API contract is what's under test,
    # not the agent pipeline (covered separately in test_graph).
    original_execute = runner.execute
    runner.execute = lambda run_id: None  # type: ignore[assignment]

    # Note: no `with` context manager — we deliberately skip the app lifespan
    # so tests don't open the real checkpointer or touch backend/data/*.db.
    # The slowapi limiter is attached at import time, so it still applies.
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()
        runner.execute = original_execute  # type: ignore[assignment]
        app.dependency_overrides.clear()
