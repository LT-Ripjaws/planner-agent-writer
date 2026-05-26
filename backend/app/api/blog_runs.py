import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session

from backend.app.api.schemas import BlogRunCreate, BlogRunDetail, BlogRunResult, BlogRunSummary
from backend.app.db.base import get_session, engine
from backend.app.db import repository


router = APIRouter(prefix="/blog-runs", tags=["blog-runs"])


def to_summary(run) -> BlogRunSummary:
    return BlogRunSummary(
        id=run.id,
        topic=run.topic,
        status=run.status,
        progress_step=run.progress_step,
        mode=run.mode,
        blog_title=run.blog_title,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def to_detail(run) -> BlogRunDetail:
    return BlogRunDetail(
        **to_summary(run).model_dump(),
        error=run.error,
        warnings=[],
    )


def fake_complete_run(run_id: str) -> None:
    with Session(engine) as session:
        run = repository.get_run(session, run_id)
        if run is None:
            return

        repository.mark_running(session, run)

        time.sleep(2)

        markdown = f"""# Draft for {run.topic}

This is a placeholder blog draft.

The real LangGraph agent will replace this later.
"""

        repository.mark_completed(session, run, markdown)


@router.post("", status_code=202, response_model=BlogRunSummary)
def create_blog_run(
    payload: BlogRunCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> BlogRunSummary:
    run = repository.create_run(
        session=session,
        topic=payload.topic,
        audience=payload.audience,
        tone=payload.tone,
        blog_kind=payload.blog_kind,
        research_mode=payload.research_mode,
    )

    background_tasks.add_task(fake_complete_run, run.id)

    return to_summary(run)


@router.get("", response_model=list[BlogRunSummary])
def list_blog_runs(
    limit: int = 20,
    session: Session = Depends(get_session),
) -> list[BlogRunSummary]:
    runs = repository.list_runs(session, limit=limit)
    return [to_summary(run) for run in runs]


@router.get("/{run_id}", response_model=BlogRunDetail)
def get_blog_run(
    run_id: str,
    session: Session = Depends(get_session),
) -> BlogRunDetail:
    run = repository.get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Blog run not found")

    return to_detail(run)


@router.get("/{run_id}/result", response_model=BlogRunResult)
def get_blog_run_result(
    run_id: str,
    session: Session = Depends(get_session),
) -> BlogRunResult:
    run = repository.get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Blog run not found")

    if run.status != "completed":
        raise HTTPException(status_code=409, detail="Blog run is not completed yet")

    return BlogRunResult(
        id=run.id,
        markdown=run.markdown or "",
        plan=None,
        evidence=[],
        citations=[],
    )