"""End-to-end /validate test using a mocked graph + JobStore.

We don't bring up the full lifespan (which would touch real API keys); instead
we instantiate FastAPI manually, attach a fake graph + job store to app.state,
and exercise the routes via httpx.AsyncClient.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.agent.state import (
    Confidence,
    Stance,
    ValidatorState,
    Verdict,
)
from src.api.jobs import JobStore
from src.api.routes import health, validate


def _build_test_app(graph: Any) -> FastAPI:
    app = FastAPI()
    app.state.graph = graph
    app.state.job_store = JobStore()
    app.include_router(health.router)
    app.include_router(validate.router)
    return app


@pytest.mark.asyncio
async def test_health() -> None:
    app = _build_test_app(graph=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_submit_then_poll_until_completed() -> None:
    completed_state = ValidatorState(
        thesis="t",
        ticker="X",
        as_of_date=datetime.now(UTC).date(),
        verdict=Verdict(stance=Stance.SUPPORTED, confidence=Confidence.HIGH, summary="ok"),
    )
    graph = AsyncMock()
    graph.ainvoke.return_value = completed_state

    app = _build_test_app(graph=graph)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post(
            "/validate", json={"thesis": "AAPL fundamentals are great", "ticker": "AAPL"}
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "queued"
        job_id = body["job_id"]

        # The background task is fired by FastAPI after the response is sent.
        # We poll a few times to give it time to run.
        final_status = None
        for _ in range(20):
            poll = await client.get(f"/validate/{job_id}")
            assert poll.status_code == 200
            final_status = poll.json()["status"]
            if final_status in ("completed", "failed"):
                break
            await asyncio.sleep(0.02)

        assert final_status == "completed"
        result = poll.json()
        assert result["verdict"]["stance"] == "SUPPORTED"
        # Guardrails always populated on completion
        assert result["guardrails"] is not None
        assert result["guardrails"]["cost_cap_exceeded"] is False
        graph.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_submit_when_graph_raises_marks_job_failed() -> None:
    graph = AsyncMock()
    graph.ainvoke.side_effect = RuntimeError("boom")

    app = _build_test_app(graph=graph)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post(
            "/validate", json={"thesis": "x", "ticker": "X"}
        )
        job_id = resp.json()["job_id"]

        for _ in range(20):
            poll = await client.get(f"/validate/{job_id}")
            if poll.json()["status"] in ("completed", "failed"):
                break
            await asyncio.sleep(0.02)

        body = poll.json()
        assert body["status"] == "failed"
        assert "boom" in body["error"]


@pytest.mark.asyncio
async def test_unknown_job_returns_404() -> None:
    app = _build_test_app(graph=AsyncMock())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/validate/no-such-job")
    assert resp.status_code == 404
