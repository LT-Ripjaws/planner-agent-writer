from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class BlogRunCreate(BaseModel):
    topic: str = Field(min_length=3, max_length=500)
    audience: str | None = None
    tone: Literal["neutral", "technical", "casual", "authoritative"] = "neutral"
    blog_kind: Literal[
        "auto",
        "explainer",
        "tutorial",
        "news_roundup",
        "comparison",
        "system_design",
    ] = "auto"
    research_mode: Literal["auto", "required", "off"] = "auto"


class BlogRunSummary(BaseModel):
    id: str
    topic: str
    status: str
    progress_step: str
    mode: str | None = None
    blog_title: str | None = None
    created_at: datetime
    updated_at: datetime


class BlogRunDetail(BlogRunSummary):
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)


class BlogRunResult(BaseModel):
    id: str
    markdown: str
    plan: dict | None = None
    evidence: list[dict] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)


class EventEnvelope(BaseModel):
    event: Literal[
        "status",
        "node_started",
        "node_completed",
        "section",
        "warning",
        "done",
        "error",
    ]
    data: dict