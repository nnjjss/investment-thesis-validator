from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from src.agent.state import SourceType
from src.ingestion._http import RateLimitedError
from src.ingestion.fmp import FMP_BASE_URL, FMPClient


@pytest.mark.asyncio
@respx.mock
async def test_profile_happy_path() -> None:
    respx.get(f"{FMP_BASE_URL}/profile").mock(
        return_value=httpx.Response(
            200,
            json=[{"symbol": "AAPL", "companyName": "Apple Inc.", "sector": "Technology"}],
        )
    )

    async with FMPClient(api_key="test") as client:
        ev = await client.profile("AAPL", as_of_date=date(2026, 5, 13))

    assert ev.source is SourceType.FMP
    assert ev.key == "fmp.profile.AAPL"
    assert ev.value["companyName"] == "Apple Inc."
    assert ev.citation.evidence_id == "fmp.profile.AAPL"


@pytest.mark.asyncio
@respx.mock
async def test_income_statement_filters_by_as_of_date() -> None:
    rows = [
        {"date": "2026-03-31", "revenue": 100},
        {"date": "2025-12-31", "revenue": 90},
        {"date": "2025-09-30", "revenue": 80},
    ]
    respx.get(f"{FMP_BASE_URL}/income-statement").mock(
        return_value=httpx.Response(200, json=rows)
    )

    async with FMPClient(api_key="test") as client:
        evs = await client.income_statement("AAPL", as_of_date=date(2026, 1, 1))

    # Only rows with date <= 2026-01-01 should pass.
    assert [ev.value["date"] for ev in evs] == ["2025-12-31", "2025-09-30"]


@pytest.mark.asyncio
@respx.mock
async def test_cash_flow_happy_path() -> None:
    rows = [
        {
            "date": "2025-12-31",
            "operatingCashFlow": 30000,
            "capitalExpenditure": -5000,
            "freeCashFlow": 25000,
        },
        {
            "date": "2025-09-30",
            "operatingCashFlow": 28000,
            "capitalExpenditure": -4500,
            "freeCashFlow": 23500,
        },
    ]
    respx.get(f"{FMP_BASE_URL}/cash-flow-statement").mock(
        return_value=httpx.Response(200, json=rows)
    )

    async with FMPClient(api_key="test") as client:
        evs = await client.cash_flow("AAPL", as_of_date=date(2026, 1, 1))

    assert len(evs) == 2
    assert evs[0].key == "fmp.cash_flow.AAPL.2025-12-31"
    assert evs[0].value["freeCashFlow"] == 25000


@pytest.mark.asyncio
@respx.mock
async def test_quote_empty_payload() -> None:
    respx.get(f"{FMP_BASE_URL}/quote").mock(return_value=httpx.Response(200, json=[]))

    async with FMPClient(api_key="test") as client:
        ev = await client.quote("ZZZZ", as_of_date=date(2026, 5, 13))

    assert ev.value == {}
    assert ev.key == "fmp.quote.ZZZZ"


@pytest.mark.asyncio
@respx.mock
async def test_rate_limit_retries_then_raises() -> None:
    route = respx.get(f"{FMP_BASE_URL}/profile").mock(
        return_value=httpx.Response(429, json={"error": "rate limited"})
    )

    async with FMPClient(api_key="test") as client:
        with pytest.raises(RateLimitedError):
            await client.profile("AAPL", as_of_date=date(2026, 5, 13))

    # 3 attempts (default RETRY_ATTEMPTS=3)
    assert route.call_count == 3
