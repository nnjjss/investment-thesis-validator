from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceType(StrEnum):
    FMP = "fmp"
    NEWS = "news"
    SEC = "sec"


class Stance(StrEnum):
    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    UNCERTAIN = "UNCERTAIN"


class Confidence(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ClaimType(StrEnum):
    FUNDAMENTAL = "fundamental"
    SENTIMENT = "sentiment"
    EVENT = "event"
    VALUATION = "valuation"
    OTHER = "other"


class ThesisClaim(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    subject: str
    claim_text: str
    claim_type: ClaimType = ClaimType.OTHER


class Citation(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: SourceType
    evidence_id: str
    url: str | None = None
    retrieved_at: datetime


class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    source: SourceType
    key: str
    value: Any
    raw: dict[str, Any] = Field(default_factory=dict)
    citation: Citation


class ClaimVerdict(BaseModel):
    model_config = ConfigDict(frozen=True)

    claim_id: str
    stance: Stance
    rationale: str
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    refuting_evidence_ids: list[str] = Field(default_factory=list)


class Verdict(BaseModel):
    stance: Stance
    confidence: Confidence
    summary: str
    claim_verdicts: list[ClaimVerdict] = Field(default_factory=list)
    evidence_used: list[str] = Field(default_factory=list)
    cost_usd: float = 0.0


class ToolCallPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    need_stock_data: bool
    need_news: bool
    need_filings: bool
    news_query: str | None = None
    rationale: str = ""


class ContradictionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    supporting_evidence_ids: list[str] = Field(default_factory=list)
    refuting_evidence_ids: list[str] = Field(default_factory=list)
    rationale: str = ""


class NodeTrace(BaseModel):
    node: str
    started_at: datetime
    finished_at: datetime
    status: str = "ok"
    tokens_in: int = 0
    tokens_out: int = 0
    cache_read: int = 0
    cache_write: int = 0
    cost_usd: float = 0.0
    error: str | None = None


class ValidatorState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    thesis: str
    ticker: str
    as_of_date: date
    claims: list[ThesisClaim] = Field(default_factory=list)
    tool_plan: ToolCallPlan | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    contradiction: ContradictionResult | None = None
    verdict: Verdict | None = None
    traces: list[NodeTrace] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def _ticker_upper(cls, v: str) -> str:
        return v.strip().upper()
