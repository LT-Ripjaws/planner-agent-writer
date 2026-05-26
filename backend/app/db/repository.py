from datetime import datetime, timezone

from sqlmodel import Session, col, select

from backend.app.db.models import BlogRun


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_run(
    session: Session, topic: str, audience: str | None = None,
    tone: str = "neutral", blog_kind: str = "auto", research_mode: str = "auto") -> BlogRun:

    run = BlogRun(
        topic=topic,
        audience=audience,
        tone=tone,
        blog_kind=blog_kind,
        research_mode=research_mode
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


def mark_running(session: Session, run: BlogRun) -> BlogRun:
    run.status = "running"
    run.progress_step = "running"
    run.updated_at = utc_now()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def mark_completed(session: Session, run: BlogRun, markdown: str | None = None) -> BlogRun:
    run.status = "completed"
    run.progress_step = "completed"
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