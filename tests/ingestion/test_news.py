from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from src.agent.state import SourceType
from src.ingestion.news import NEWS_BASE_URL, NewsClient


@pytest.mark.asyncio
@respx.mock
async def test_search_happy_path() -> None:
    respx.get(f"{NEWS_BASE_URL}/everything").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "ok",
                "totalResults": 2,
                "articles": [
                    {
                        "source": {"name": "Reuters"},
                        "title": "TSM beats earnings",
                        "description": "Q3 numbers strong",
                        "url": "https://example.com/a",
                        "publishedAt": "2026-05-10T12:00:00Z",
                    },
                    {
                        "source": {"name": "Bloomberg"},
                        "title": "TSM AI capex update",
                        "description": "Capex raised",
                        "url": "https://example.com/b",
                        "publishedAt": "2026-05-11T08:00:00Z",
                    },
                ],
            },
        )
    )

    async with NewsClient(api_key="news-test") as client:
        evs = await client.search("TSM", as_of_date=date(2026, 5, 13))

    assert len(evs) == 2
    assert evs[0].source is SourceType.NEWS
    assert evs[0].value["title"] == "TSM beats earnings"
    assert evs[0].citation.url == "https://example.com/a"


@pytest.mark.asyncio
@respx.mock
async def test_search_empty() -> None:
    respx.get(f"{NEWS_BASE_URL}/everything").mock(
        return_value=httpx.Response(200, json={"status": "ok", "totalResults": 0, "articles": []})
    )

    async with NewsClient(api_key="news-test") as client:
        evs = await client.search("ZZZZ", as_of_date=date(2026, 5, 13))

    assert evs == []


@pytest.mark.asyncio
@respx.mock
async def test_search_unauthorized_raises() -> None:
    respx.get(f"{NEWS_BASE_URL}/everything").mock(
        return_value=httpx.Response(401, json={"status": "error", "code": "apiKeyInvalid"})
    )

    async with NewsClient(api_key="bad") as client:
        with pytest.raises(httpx.HTTPStatusError):
            await client.search("AAPL", as_of_date=date(2026, 5, 13))
