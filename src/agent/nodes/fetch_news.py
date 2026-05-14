"""Node: fetch_news — search NewsAPI for the planner-supplied query."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.agent.state import NodeTrace, ValidatorState
from src.ingestion.news import NewsClient


async def fetch_news(
    state: ValidatorState,
    news: NewsClient,
) -> dict[str, Any]:
    started = datetime.now(UTC)

    plan = state.tool_plan
    if plan is None or not plan.need_news:
        finished = datetime.now(UTC)
        return {
            "traces": [
                *state.traces,
                NodeTrace(
                    node="fetch_news",
                    started_at=started,
                    finished_at=finished,
                    status="skipped",
                ),
            ]
        }

    query = (plan.news_query or state.ticker).strip()
    new_evidence = await news.search(query, as_of_date=state.as_of_date)
    finished = datetime.now(UTC)
    trace = NodeTrace(
        node="fetch_news",
        started_at=started,
        finished_at=finished,
        status="ok",
    )
    return {
        "evidence": [*state.evidence, *new_evidence],
        "traces": [*state.traces, trace],
    }
