import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.agents.state import Plan

# Jailbreak phrase denylist. Compiled once at import time.
# Catches the most common low-effort prompt-injection attempts in the topic
# field.
_JAILBREAK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bignore (previous|prior|above|all)\b", re.IGNORECASE),
    re.compile(r"\bsystem prompt\b", re.IGNORECASE),
    re.compile(r"\breveal (your|the) (instructions|prompt|system)\b", re.IGNORECASE),
    re.compile(r"\bdisregard (previous|prior|all)\b", re.IGNORECASE),
    re.compile(r"\b(forget|override) (your|all) (instructions|rules)\b", re.IGNORECASE),
)


def matched_jailbreak_phrase(text: str) -> str | None:
    """Returns the first matching jailbreak phrase, or None if clean."""
    for pattern in _JAILBREAK_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None


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

    @field_validator("topic")
    @classmethod
    def reject_jailbreak_topics(cls, value: str) -> str:
        match = matched_jailbreak_phrase(value)
        if match is not None:
            raise ValueError(
                f"Topic contains a disallowed phrase ('{match}'). "
                "Please rephrase to describe the subject you want written about."
            )
        return value


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
    plan: dict | None = None
    markdown: str | None = None


class PlanApprovalDecision(BaseModel):
    action: Literal["approve", "reject"]
    plan: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_edited_plan(self) -> "PlanApprovalDecision":
        if self.action == "approve" and self.plan is not None:
            validated_plan = Plan.model_validate(self.plan)
            self.plan = validated_plan.model_dump()

        return self


class BlogRunResult(BaseModel):
    id: str
    markdown: str
    plan: dict | None = None
    evidence: list[dict] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)
    quality_report: dict | None = None


class EventEnvelope(BaseModel):
    event: Literal[
        "status",
        "node_started",
        "node_completed",
        "section",
        "warning",
        "awaiting_input",
        "done",
        "error",
    ]
    data: dict
