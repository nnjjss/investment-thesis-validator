"""NewsAPI.org client (developer tier — 100 requests/day, free).

Per the locked design decision, NewsAPI is the v1 news provider. Tavily is
deferred behind a flag in M9 if quality becomes the bottleneck.

Point-in-time correctness: ``as_of_date`` clamps the upper bound of returned
articles regardless of what ``to_date`` argument is passed.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from src.agent.state import Citation, Evidence, SourceType
from src.ingestion._http import AsyncHTTPClient

NEWS_BASE_URL = "https://newsapi.org/v2"


class NewsClient:
    def __init__(self, api_key: str, *, base_url: str = NEWS_BASE_URL) -> None:
        self._api_key = api_key
        self._http = AsyncHTTPClient(
            base_url=base_url,
            headers={"X-Api-Key": api_key},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> NewsClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def search(
        self,
        query: str,
        *,
        as_of_date: date,
        from_date: date | None = None,
        page_size: int = 20,
        language: str = "en",
    ) -> list[Evidence]:
        effective_from = from_date or (as_of_date - timedelta(days=14))
        params: dict[str, Any] = {
            "q": query,
            "from": effective_from.isoformat(),
            "to": as_of_date.isoformat(),
            "pageSize": page_size,
            "language": language,
            "sortBy": "publishedAt",
        }
        data = await self._http.get_json("/everything", params=params)
        articles = data.get("articles", []) if isinstance(data, dict) else []

        return [
            _evidence_for(query, idx, article, as_of_date)
            for idx, article in enumerate(articles)
        ]


def _evidence_for(
    query: str,
    idx: int,
    article: dict[str, Any],
    as_of_date: date,
) -> Evidence:
    published = article.get("publishedAt", "")
    eid = f"news.{query}.{published}.{idx}"
    return Evidence(
        id=eid,
        source=SourceType.NEWS,
        key=eid,
        value={
            "title": article.get("title"),
            "description": article.get("description"),
            "publishedAt": published,
            "source": (article.get("source") or {}).get("name"),
        },
        raw={"article": article, "as_of_date": as_of_date.isoformat()},
        citation=Citation(
            source=SourceType.NEWS,
            evidence_id=eid,
            url=article.get("url"),
            retrieved_at=datetime.now(UTC),
        ),
    )
