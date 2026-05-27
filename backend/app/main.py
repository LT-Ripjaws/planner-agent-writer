import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from sqlmodel import Session

from backend.app.api.blog_runs import router as blog_runs_router
from backend.app.api.events import router as events_router
from backend.app.core.config import settings
from backend.app.db import repository
from backend.app.db.base import engine, init_db
from backend.app.services.runtime import set_checkpointer

logger = logging.getLogger(__name__)


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
