from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class BlogRun(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)

    topic: str
    audience: Optional[str] = None
    tone: str = "neutral"
    blog_kind: str = "auto"
    research_mode: str = "auto"
    
    status: str = "queued"
    progress_step: str = "created"

    mode: Optional[str] = None
    blog_title: Optional[str] = None
    error: Optional[str] = None

    plan_json: Optional[str] = None
    evidence_json: Optional[str] = None
    markdown: Optional[str] = None
    warnings_json: Optional[str] = None
    quality_report_json: Optional[str] = None
    awaiting_approval_started_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
