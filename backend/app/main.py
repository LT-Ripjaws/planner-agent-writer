import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlmodel import Session

from backend.app.api.blog_runs import router as blog_runs_router
from backend.app.api.events import router as events_router
from backend.app.core.config import settings
from backend.app.db import repository
from backend.app.db.base import engine, init_db
from backend.app.deps import limiter
from backend.app.services.runtime import set_checkpointer

logger = logging.getLogger(__name__)


def rate_limit_exceeded_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, RateLimitExceeded):
        raise exc
    return _rate_limit_exceeded_handler(request, exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()

    # Startup zombie sweep: mark any runs left in `status='running'` from a
    # previous process (crashed uvicorn, OS shutdown, etc.) as failed.
    # Otherwise they hang forever.
    with Session(engine) as session:
        swept = repository.sweep_orphaned_running(
            session,
            reason="server restart before completion",
        )
    if swept:
        logger.warning("Swept %d orphaned 'running' blog run(s) at startup", swept)

    with Session(engine) as session:
        expired_approvals = repository.sweep_expired_approvals(
            session,
            hours=settings.hitl_approval_timeout_hours,
        )
    if expired_approvals:
        logger.warning(
            "Swept %d expired plan approval blog run(s) at startup",
            expired_approvals,
        )

    # Ensure the checkpoint database directory exists.
    checkpoint_path = Path(settings.checkpoint_database_path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    # Open the LangGraph checkpointer for the lifetime of the process.
    # `setup()` creates the checkpoint tables on first run.
    async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
        await checkpointer.setup()
        set_checkpointer(checkpointer)
        logger.info("Checkpointer ready at %s", checkpoint_path)
        try:
            yield
        finally:
            set_checkpointer(None)


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# register the limiter on app state + RateLimitExceeded handler so any
# route decorated with @limiter.limit(...) actually enforces it.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

cors_origins = [
    origin.strip()
    for origin in settings.cors_origins.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(blog_runs_router, prefix="/api")
app.include_router(events_router, prefix="/api")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error while processing %s %s", request.method, request.url.path)

    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "detail": "An unexpected server error occurred.",
        },
    )


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
