from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from src.agent.state import SourceType
from src.ingestion.sec import EDGAR_DATA_BASE, SECClient


def _submissions_payload() -> dict[str, object]:
    return {
        "cik": "0000320193",
        "name": "Apple Inc.",
        "filings": {
            "recent": {
                "accessionNumber": [
                    "0000320193-26-000005",
                    "0000320193-25-000010",
                    "0000320193-24-000020",
                ],
                "filingDate": ["2026-04-30", "2025-10-30", "2024-11-01"],
                "form": ["10-Q", "10-K", "10-K"],
                "primaryDocument": ["aapl-20260331.htm", "aapl-20250930.htm", "aapl-20240928.htm"],
                "primaryDocDescription": ["Form 10-Q", "Form 10-K", "Form 10-K"],
            }
        },
    }


@pytest.mark.asyncio
@respx.mock
async def test_recent_filings_filters_by_as_of_and_form() -> None:
    respx.get(f"{EDGAR_DATA_BASE}/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(200, json=_submissions_payload())
    )

    async with SECClient(user_agent="ITV Test contact@example.com") as client:
        evs = await client.recent_filings(
            cik="320193",
            as_of_date=date(2026, 1, 1),
            forms=("10-K",),
        )

    # Only 10-K rows with filingDate <= 2026-01-01 → 2025-10-30 and 2024-11-01.
    dates = [ev.value["filingDate"] for ev in evs]
    assert dates == ["2025-10-30", "2024-11-01"]
    assert evs[0].source is SourceType.SEC
    assert evs[0].citation.url and "0000320193" in evs[0].citation.url


@pytest.mark.asyncio
@respx.mock
async def test_recent_filings_empty_after_filter() -> None:
    respx.get(f"{EDGAR_DATA_BASE}/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(200, json=_submissions_payload())
    )

    async with SECClient(user_agent="ITV Test contact@example.com") as client:
        evs = await client.recent_filings(
            cik="320193",
            as_of_date=date(2020, 1, 1),
        )

    assert evs == []


def test_constructor_rejects_blank_user_agent() -> None:
    with pytest.raises(ValueError, match="non-empty User-Agent"):
        SECClient(user_agent="   ")
