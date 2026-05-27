import json
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session

from backend.app.api.schemas import (
    BlogRunCreate,
    BlogRunDetail,
    BlogRunResult,
    BlogRunSummary,
)
from backend.app.db import repository
from backend.app.db.base import get_session
from backend.app.db.models import BlogRun
from backend.app.workers import runner

router = APIRouter(prefix="/blog-runs", tags=["blog-runs"])

RESULT_STATUSES = {"completed", "completed_with_warnings"}


def parse_json_value(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def warnings_for(run: BlogRun) -> list[str]:
    warnings = parse_json_value(run.warnings_json, [])
    if not isinstance(warnings, list):
        return []

    return [str(warning) for warning in warnings]


def to_summary(run: BlogRun) -> BlogRunSummary:
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


def to_detail(run: BlogRun) -> BlogRunDetail:
    return BlogRunDetail(
        **to_summary(run).model_dump(),
        error=run.error,
        warnings=warnings_for(run),
    )


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

    background_tasks.add_task(runner.execute, run.id)

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

    if run.status not in RESULT_STATUSES:
        raise HTTPException(status_code=409, detail="Blog run is not completed yet")

    plan = parse_json_value(run.plan_json, None)
    evidence = parse_json_value(run.evidence_json, [])

    return BlogRunResult(
        id=run.id,
        markdown=run.markdown or "",
        plan=plan if isinstance(plan, dict) else None,
        evidence=evidence if isinstance(evidence, list) else [],
        citations=[],
    )


@router.post("/{run_id}/resume", status_code=202, response_model=BlogRunSummary)
def resume_blog_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> BlogRunSummary:
    run = repository.get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Blog run not found")

    if run.status != "failed":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot resume run in status '{run.status}'; only 'failed' runs are resumable",
        )

    background_tasks.add_task(runner.resume, run.id)

    return to_summary(run)
