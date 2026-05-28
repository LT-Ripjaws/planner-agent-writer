import operator
from typing import Annotated, Any, Literal, Optional, TypedDict

from pydantic import BaseModel, Field

BlogKind = Literal[
    "explainer",
    "tutorial",
    "news_roundup",
    "comparison",
    "system_design",
]


class EvidenceItem(BaseModel):
    title: str
    url: str
    published_at: Optional[str] = None
    snippet: str
    source: Optional[str] = None
    score: Optional[float] = None


class Task(BaseModel):
    id: int
    title: str
    goal: str
    bullets: list[str] = Field(min_length=3, max_length=6)
    target_words: int = Field(ge=120, le=220)
    tags: list[str] = Field(default_factory=list)
    requires_research: bool = False
    requires_citations: bool = False
    requires_code: bool = False


class Plan(BaseModel):
    blog_title: str
    audience: str
    tone: str
    blog_kind: BlogKind
    constraints: list[str] = Field(default_factory=list)
    tasks: list[Task] = Field(min_length=5, max_length=9)


class RouterDecision(BaseModel):
    needs_research: bool
    mode: Literal["closed_book", "hybrid", "open_book"]
    reason: str
    queries: list[str] = Field(default_factory=list, max_length=10)
    max_results_per_query: int = Field(default=5, ge=1, le=10)


#  Quality evaluation


IssueCategory = Literal[
    "off_topic",
    "incomplete",
    "tone",
    "missing_code",
    "length",
]

Severity = Literal["low", "medium", "high"]


class Issue(BaseModel):
    task_id: int
    category: IssueCategory
    severity: Severity
    description: str = Field(min_length=3, max_length=500)


class HallucinationFlag(BaseModel):
    task_id: int
    claim: str = Field(min_length=3, max_length=600)
    severity: Severity
    rationale: str = Field(min_length=3, max_length=600)


class QualityReport(BaseModel):
    overall_score: float = Field(ge=0, le=10)
    on_topic: bool
    on_topic_reason: Optional[str] = None
    completeness: float = Field(ge=0, le=1)
    tone_match: bool
    code_present_where_required: bool
    issues: list[Issue] = Field(default_factory=list)
    hallucinations: list[HallucinationFlag] = Field(default_factory=list)
    sections_to_redo: list[int] = Field(default_factory=list, max_length=3)


class State(TypedDict, total=False):
    run_id: str

    topic: str
    audience: str | None
    tone: str
    blog_kind: str
    research_mode: str

    mode: str
    needs_research: bool
    queries: list[str]
    max_results_per_query: int

    evidence: list[dict]
    plan: dict | None
    task: dict

    as_of: str
    recency_days: int

    sections: Annotated[list[tuple[int, str]], operator.add]
    merged_md: str
    final: str
    warnings: Annotated[list[str], operator.add]
    max_sections: int
    writer_timeout_seconds: int

    # quality evaluation
    quality_report: dict[str, Any]
    improvement_iter: int
