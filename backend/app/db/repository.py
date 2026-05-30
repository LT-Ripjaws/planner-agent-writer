import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlmodel import Session, col, select

from backend.app.db.models import BlogRun


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_run(
    session: Session,
    topic: str,
    audience: str | None = None,
    tone: str = "neutral",
    blog_kind: str = "auto",
    research_mode: str = "auto",
) -> BlogRun:
    run = BlogRun(
        topic=topic,
        audience=audience,
        tone=tone,
        blog_kind=blog_kind,
        research_mode=research_mode,
    )

    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def list_runs(session: Session, limit: int = 20) -> list[BlogRun]:
    statement = select(BlogRun).order_by(col(BlogRun.created_at).desc()).limit(limit)
    return list(session.exec(statement).all())


def get_run(session: Session, run_id: str) -> BlogRun | None:
    return session.get(BlogRun, run_id)


def update_step(session: Session, run: BlogRun, progress_step: str) -> BlogRun:
    run.progress_step = progress_step
    run.updated_at = utc_now()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def save_mode(session: Session, run: BlogRun, mode: str) -> BlogRun:
    run.mode = mode
    run.updated_at = utc_now()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def save_plan(session: Session, run: BlogRun, plan: dict[str, Any]) -> BlogRun:
    run.plan_json = json.dumps(plan)
    run.blog_title = plan.get("blog_title")
    run.updated_at = utc_now()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def save_evidence(session: Session, run: BlogRun, evidence: list[dict[str, Any]]) -> BlogRun:
    run.evidence_json = json.dumps(evidence)
    run.updated_at = utc_now()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def save_markdown(session: Session, run: BlogRun, markdown: str) -> BlogRun:
    run.markdown = markdown
    run.updated_at = utc_now()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def save_warnings(session: Session, run: BlogRun, warnings: list[str]) -> BlogRun:
    run.warnings_json = json.dumps(warnings)
    run.updated_at = utc_now()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def save_quality_report(
    session: Session,
    run: BlogRun,
    report: dict[str, Any],
) -> BlogRun:
    run.quality_report_json = json.dumps(report)
    run.updated_at = utc_now()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def mark_running(session: Session, run: BlogRun) -> BlogRun:
    run.status = "running"
    run.progress_step = "running"
    run.awaiting_approval_started_at = None
    run.updated_at = utc_now()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def mark_completed(
    session: Session,
    run: BlogRun,
    markdown: str | None = None,
    *,
    with_warnings: bool = False,
) -> BlogRun:
    run.status = "completed_with_warnings" if with_warnings else "completed"
    run.progress_step = "completed"
    run.awaiting_approval_started_at = None
    if markdown is not None:
        run.markdown = markdown
    run.updated_at = utc_now()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def mark_failed(session: Session, run: BlogRun, error: str) -> BlogRun:
    run.status = "failed"
    run.progress_step = "failed"
    run.error = error
    run.awaiting_approval_started_at = None
    run.updated_at = utc_now()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def mark_awaiting_approval(session: Session, run: BlogRun) -> BlogRun:
    run.status = "awaiting_approval"
    run.progress_step = "awaiting_plan_approval"
    run.awaiting_approval_started_at = utc_now()
    run.error = None
    run.updated_at = utc_now()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def sweep_orphaned_running(session: Session, reason: str) -> int:
    """Mark any row left in ``status='running'`` as failed.

    Called from the FastAPI lifespan startup so that a crashed previous process
    doesn't leave runs hanging indefinitely. Returns the count of rows updated
    for logging purposes.
    """
    statement = select(BlogRun).where(BlogRun.status == "running")
    orphans = list(session.exec(statement).all())
    now = utc_now()

    for run in orphans:
        run.status = "failed"
        run.progress_step = "failed"
        run.error = reason
        run.updated_at = now
        session.add(run)

    if orphans:
        session.commit()

    return len(orphans)


def sweep_expired_approvals(session: Session, hours: int) -> int:
    """Fail runs that were left awaiting plan approval past the timeout."""
    statement = select(BlogRun).where(BlogRun.status == "awaiting_approval")
    awaiting = list(session.exec(statement).all())
    now = utc_now()
    cutoff = now - timedelta(hours=hours)
    expired: list[BlogRun] = []

    for run in awaiting:
        started_at = run.awaiting_approval_started_at
        if started_at is None or _as_aware_utc(started_at) < cutoff:
            expired.append(run)

    for run in expired:
        run.status = "failed"
        run.progress_step = "failed"
        run.error = "approval timeout"
        run.awaiting_approval_started_at = None
        run.updated_at = now
        session.add(run)

    if expired:
        session.commit()

    return len(expired)
