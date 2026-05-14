"""Node: fetch_filings — pull recent SEC filings via EDGAR.

Ticker→CIK mapping is a separate problem; for v1 we ship a small built-in
table covering common test tickers, and skip with a logged trace if a CIK
isn't known. A proper SEC ticker.json loader is M2c work.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from src.agent.state import NodeTrace, ValidatorState
from src.ingestion.sec import SECClient

logger = structlog.get_logger(__name__)

# Minimal built-in ticker→CIK table. Extend or replace with a JSON loader later.
KNOWN_CIK: dict[str, str] = {
    "AAPL": "320193",
    "MSFT": "789019",
    "NVDA": "1045810",
    "TSM": "1046179",
    "GOOGL": "1652044",
    "META": "1326801",
    "AMZN": "1018724",
}


async def fetch_filings(
    state: ValidatorState,
    sec: SECClient,
    *,
    ticker_to_cik: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = datetime.now(UTC)
    plan = state.tool_plan
    table = ticker_to_cik or KNOWN_CIK

    if plan is None or not plan.need_filings:
        finished = datetime.now(UTC)
        return {
            "traces": [
                *state.traces,
                NodeTrace(
                    node="fetch_filings",
                    started_at=started,
                    finished_at=finished,
                    status="skipped",
                ),
            ]
        }

    cik = table.get(state.ticker)
    if cik is None:
        logger.warning("fetch_filings_no_cik", ticker=state.ticker)
        finished = datetime.now(UTC)
        return {
            "traces": [
                *state.traces,
                NodeTrace(
                    node="fetch_filings",
                    started_at=started,
                    finished_at=finished,
                    status="skipped",
                    error=f"no CIK for ticker {state.ticker}",
                ),
            ]
        }

    new_evidence = await sec.recent_filings(cik=cik, as_of_date=state.as_of_date)
    finished = datetime.now(UTC)
    trace = NodeTrace(
        node="fetch_filings",
        started_at=started,
        finished_at=finished,
        status="ok",
    )
    return {
        "evidence": [*state.evidence, *new_evidence],
        "traces": [*state.traces, trace],
    }
