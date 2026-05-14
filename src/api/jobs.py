"""In-process job store for the validate endpoint.

Intentionally not Celery / Redis — solo-dev, single-process. Document the
upgrade path in docs/RUNBOOK.md when the time comes.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.agent.state import ValidatorState, Verdict
from src.api.schemas import GuardrailReport, JobStateResponse, JobStatus
from src.guardrails.citation_binding import unsupported_claims
from src.guardrails.numeric_check import numeric_findings

logger = logging.getLogger(__name__)


@dataclass
class JobState:
    job_id: str
    status: JobStatus = JobStatus.QUEUED
    submitted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cost_usd: float = 0.0
    verdict: Verdict | None = None
    guardrails: GuardrailReport | None = None
    error: str | None = None

    def to_response(self) -> JobStateResponse:
        return JobStateResponse(
            job_id=self.job_id,
            status=self.status,
            submitted_at=self.submitted_at,
            started_at=self.started_at,
            finished_at=self.finished_at,
            cost_usd=self.cost_usd,
            verdict=self.verdict,
            guardrails=self.guardrails,
            error=self.error,
        )


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}
        self._lock = asyncio.Lock()

    async def submit(self) -> JobState:
        job = JobState(job_id=uuid.uuid4().hex)
        async with self._lock:
            self._jobs[job.job_id] = job
        return job

    async def get(self, job_id: str) -> JobState | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def update(self, job_id: str, **fields: Any) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in fields.items():
                setattr(job, key, value)


async def run_job(
    job_store: JobStore,
    job_id: str,
    *,
    initial_state: ValidatorState,
    graph: Any,
    metrics: Any = None,
    metrics_model_label: str = "agent",
    cost_cap_usd: float = 0.50,
) -> None:
    await job_store.update(
        job_id, status=JobStatus.RUNNING, started_at=datetime.now(UTC)
    )
    try:
        raw = await graph.ainvoke(initial_state)
        state = (
            raw if isinstance(raw, ValidatorState) else ValidatorState.model_validate(raw)
        )
        cost = sum(t.cost_usd for t in state.traces)

        unsupported = unsupported_claims(state)
        suspicious = numeric_findings(state)
        guardrails = GuardrailReport(
            unsupported_claim_ids=[u.claim_id for u in unsupported],
            suspicious_numbers=[f.span for f in suspicious],
            cost_cap_exceeded=cost > cost_cap_usd,
            cost_cap_usd=cost_cap_usd,
        )
        if guardrails.cost_cap_exceeded:
            logger.warning(
                "cost_cap_exceeded",
                extra={"job_id": job_id, "cost_usd": cost, "cap": cost_cap_usd},
            )

        await job_store.update(
            job_id,
            status=JobStatus.COMPLETED,
            finished_at=datetime.now(UTC),
            verdict=state.verdict,
            cost_usd=cost,
            guardrails=guardrails,
        )
        if metrics is not None:
            metrics.emit_completed(state, model_for_costs=metrics_model_label)
    except Exception as exc:  # noqa: BLE001 — surface to client via error field
        logger.exception("job_failed", extra={"job_id": job_id})
        await job_store.update(
            job_id,
            status=JobStatus.FAILED,
            finished_at=datetime.now(UTC),
            error=str(exc),
        )
        if metrics is not None:
            metrics.emit_failed()
