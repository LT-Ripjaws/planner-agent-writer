from collections.abc import Generator

from sqlalchemy import inspect
from sqlmodel import Session, SQLModel, create_engine, text

from backend.app.core.config import settings
from backend.app.db import models as models  # noqa: F401
from backend.app.db.models import BlogRun

engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)

    with engine.begin() as connection:
        table_name = BlogRun.__table__.name
        columns = {
            column["name"]
            for column in inspect(connection).get_columns(table_name)
        }
        if "awaiting_approval_started_at" not in columns:
            connection.execute(
                text(
                    f"ALTER TABLE {table_name} "
                    "ADD COLUMN awaiting_approval_started_at DATETIME"
                )
            )

    with engine.connect() as connection:
        connection.execute(text("PRAGMA journal_mode=WAL;"))


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
