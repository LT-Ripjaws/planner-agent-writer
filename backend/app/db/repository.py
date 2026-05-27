import json
from datetime import datetime, timezone
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


def mark_running(session: Session, run: BlogRun) -> BlogRun:
    run.status = "running"
    run.progress_step = "running"
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
    run.updated_at = utc_now()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


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
