from fastapi import FastAPI
from backend.app.core.config import settings
from backend.app.db.base import init_db

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}