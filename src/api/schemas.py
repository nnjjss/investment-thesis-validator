"""Public API schemas for the validate endpoint."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from src.agent.state import Verdict


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ValidateRequest(BaseModel):
    thesis: str = Field(..., min_length=1, max_length=4000)
    ticker: str = Field(..., min_length=1, max_length=10)
    as_of_date: date | None = None  # defaults to today UTC if omitted


class ValidateAcceptedResponse(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.QUEUED


class GuardrailReport(BaseModel):
    unsupported_claim_ids: list[str] = Field(default_factory=list)
    suspicious_numbers: list[str] = Field(default_factory=list)
    cost_cap_exceeded: bool = False
    cost_cap_usd: float = 0.0


class JobStateResponse(BaseModel):
    job_id: str
    status: JobStatus
    submitted_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cost_usd: float = 0.0
    verdict: Verdict | None = None
    guardrails: GuardrailReport | None = None
    error: str | None = None
