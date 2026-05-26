from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class BlogRun(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)

    topic: str
    status: str = "queued"
    progress_step: str = "created"

    mode: Optional[str] = None
    blog_title: Optional[str] = None
    error: Optional[str] = None

    plan_json: Optional[str] = None
    evidence_json: Optional[str] = None
    markdown: Optional[str] = None
    warnings_json: Optional[str] = None

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)