"""Node: fetch_stock — pull profile, quote, and last 4 quarters of fundamentals from FMP.

Each FMP endpoint is queried independently and failures are isolated: if one
endpoint returns 402 (paywalled on a tier) or another error, the others still
contribute evidence. The node only marks itself as failed if ALL four endpoints
error out.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.agent.state import Evidence, NodeTrace, ValidatorState
from src.ingestion.fmp import FMPClient

logger = logging.getLogger(__name__)


async def _safe(label: str, coro: Any, errors: list[str]) -> list[Evidence]:
    try:
        result = await coro
    except Exception as exc:  # noqa: BLE001 — per-endpoint isolation
        msg = f"{label}: {type(exc).__name__}: {exc}"
        logger.warning("fmp_endpoint_failed", extra={"label": label, "error": msg})
        errors.append(msg)
        return []
    if isinstance(result, list):
        return result
    return [result]


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

    errors: list[str] = []
    new_evidence: list[Evidence] = []
    new_evidence.extend(
        await _safe("profile", fmp.profile(state.ticker, as_of_date=state.as_of_date), errors)
    )
    new_evidence.extend(
        await _safe("quote", fmp.quote(state.ticker, as_of_date=state.as_of_date), errors)
    )
    new_evidence.extend(
        await _safe(
            "income_statement",
            fmp.income_statement(state.ticker, as_of_date=state.as_of_date, limit=4),
            errors,
        )
    )
    new_evidence.extend(
        await _safe(
            "cash_flow",
            fmp.cash_flow(state.ticker, as_of_date=state.as_of_date, limit=4),
            errors,
        )
    )
    new_evidence.extend(
        await _safe(
            "ratios",
            fmp.ratios(state.ticker, as_of_date=state.as_of_date, limit=4),
            errors,
        )
    )

    finished = datetime.now(UTC)
    status = "ok" if new_evidence else "skipped"
    trace = NodeTrace(
        node="fetch_stock",
        started_at=started,
        finished_at=finished,
        status=status,
        error="; ".join(errors) if errors else None,
    )
    return {
        "evidence": [*state.evidence, *new_evidence],
        "traces": [*state.traces, trace],
    }
