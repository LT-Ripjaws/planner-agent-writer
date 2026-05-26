from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine, text

from backend.app.db import models # Yes, I know this import looks unused, but it is intentionally here for model registration.
from backend.app.core.config import settings

engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False},
)

def init_db() -> None:
    SQLModel.metadata.create_all(engine)

    with engine.connect() as connection:
        connection.execute(text("PRAGMA journal_mode=WAL;"))

def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session