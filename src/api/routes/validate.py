from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from src.agent.state import ValidatorState
from src.api.jobs import JobStore, run_job
from src.api.schemas import (
    JobStateResponse,
    ValidateAcceptedResponse,
    ValidateRequest,
)

router = APIRouter(tags=["validate"])


def _job_store(request: Request) -> JobStore:
    store: JobStore = request.app.state.job_store
    return store


def _graph(request: Request) -> Any:
    return request.app.state.graph


@router.post(
    "/validate",
    response_model=ValidateAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_validation(
    payload: ValidateRequest,
    background: BackgroundTasks,
    request: Request,
) -> ValidateAcceptedResponse:
    job_store = _job_store(request)
    graph = _graph(request)
    job = await job_store.submit()

    initial = ValidatorState(
        thesis=payload.thesis,
        ticker=payload.ticker,
        as_of_date=payload.as_of_date or datetime.now(UTC).date(),
    )
    background.add_task(
        run_job,
        job_store=job_store,
        job_id=job.job_id,
        initial_state=initial,
        graph=graph,
        metrics=getattr(request.app.state, "metrics", None),
        metrics_model_label=getattr(request.app.state, "metrics_model_label", "agent"),
        cost_cap_usd=getattr(request.app.state, "cost_cap_usd", 0.50),
    )
    return ValidateAcceptedResponse(job_id=job.job_id, status=job.status)


@router.get("/validate/{job_id}", response_model=JobStateResponse)
async def get_validation(job_id: str, request: Request) -> JobStateResponse:
    job_store = _job_store(request)
    job = await job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} not found")
    return job.to_response()
