"""Schema for the Golden Dataset used by the eval harness.

Each ``GoldenItem`` represents a single (thesis, expected outcome) pair. The
dataset lives in ``eval/datasets/golden_v1.jsonl`` (one JSON object per line).
``min_tools_called`` is checked by the eval harness as recall; ``expected_evidence_keys``
is checked as precision against the actual evidence the agent surfaced.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from src.agent.state import Stance


class GoldenItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    category: str  # fundamentals | sentiment | contradiction | edge_case | multi_claim
    thesis: str
    ticker: str
    as_of_date: date
    expected_stance: Stance
    expected_evidence_keys: list[str] = Field(default_factory=list)
    # Subset of {fetch_stock, fetch_news, fetch_filings}.
    min_tools_called: list[str] = Field(default_factory=list)
    notes: str = ""
