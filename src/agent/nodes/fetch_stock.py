"""Node: fetch_stock — pull profile, quote, and last 4 quarters of fundamentals from FMP."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.agent.state import NodeTrace, ValidatorState
from src.ingestion.fmp import FMPClient


async def fetch_stock(
    state: ValidatorState,
    fmp: FMPClient,
) -> dict[str, Any]:
    started = datetime.now(UTC)

    if state.tool_plan is None or not state.tool_plan.need_stock_data:
        finished = datetime.now(UTC)
        skip_trace = NodeTrace(
            node="fetch_stock",
            started_at=started,
            finished_at=finished,
            status="skipped",
        )
        return {"traces": [*state.traces, skip_trace]}

    profile = await fmp.profile(state.ticker, as_of_date=state.as_of_date)
    quote = await fmp.quote(state.ticker, as_of_date=state.as_of_date)
    income = await fmp.income_statement(state.ticker, as_of_date=state.as_of_date, limit=4)
    ratios = await fmp.ratios(state.ticker, as_of_date=state.as_of_date, limit=4)

    new_evidence = [profile, quote, *income, *ratios]
    finished = datetime.now(UTC)
    trace = NodeTrace(
        node="fetch_stock",
        started_at=started,
        finished_at=finished,
        status="ok",
    )
    return {
        "evidence": [*state.evidence, *new_evidence],
        "traces": [*state.traces, trace],
    }
