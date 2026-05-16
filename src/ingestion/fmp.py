"""FMP (financialmodelingprep.com) client.

Endpoint table mirrored from signalpilotai/.agents/skills/fmp-fetcher/SKILL.md.
Point-in-time correctness: every method accepts ``as_of_date`` and filters
historical rows where applicable. ``/quote`` and ``/profile`` are inherently
real-time; ``as_of_date`` is recorded for citation but not enforced.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from src.agent.state import Citation, Evidence, SourceType
from src.ingestion._http import AsyncHTTPClient

FMP_BASE_URL = "https://financialmodelingprep.com/stable"


class FMPClient:
    def __init__(self, api_key: str, *, base_url: str = FMP_BASE_URL) -> None:
        self._api_key = api_key
        self._http = AsyncHTTPClient(base_url=base_url)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> FMPClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def profile(self, symbol: str, *, as_of_date: date) -> Evidence:
        data = await self._get("/profile", {"symbol": symbol})
        first = _first_or_empty(data)
        return _evidence(
            key=f"fmp.profile.{symbol}",
            value=first,
            raw={"data": data},
            as_of_date=as_of_date,
        )

    async def quote(self, symbol: str, *, as_of_date: date) -> Evidence:
        data = await self._get("/quote", {"symbol": symbol})
        first = _first_or_empty(data)
        return _evidence(
            key=f"fmp.quote.{symbol}",
            value=first,
            raw={"data": data},
            as_of_date=as_of_date,
        )

    async def income_statement(
        self,
        symbol: str,
        *,
        as_of_date: date,
        period: str = "quarter",
        limit: int = 8,
    ) -> list[Evidence]:
        data = await self._get(
            "/income-statement",
            {"symbol": symbol, "period": period, "limit": limit},
        )
        rows = _filter_by_date(data, as_of_date)
        return [
            _evidence(
                key=f"fmp.income_statement.{symbol}.{row.get('date', 'unknown')}",
                value=row,
                raw={},
                as_of_date=as_of_date,
            )
            for row in rows
        ]

    async def ratios(
        self,
        symbol: str,
        *,
        as_of_date: date,
        period: str = "quarter",
        limit: int = 8,
    ) -> list[Evidence]:
        data = await self._get(
            "/ratios",
            {"symbol": symbol, "period": period, "limit": limit},
        )
        rows = _filter_by_date(data, as_of_date)
        return [
            _evidence(
                key=f"fmp.ratios.{symbol}.{row.get('date', 'unknown')}",
                value=row,
                raw={},
                as_of_date=as_of_date,
            )
            for row in rows
        ]

    async def cash_flow(
        self,
        symbol: str,
        *,
        as_of_date: date,
        period: str = "quarter",
        limit: int = 4,
    ) -> list[Evidence]:
        data = await self._get(
            "/cash-flow-statement",
            {"symbol": symbol, "period": period, "limit": limit},
        )
        rows = _filter_by_date(data, as_of_date)
        return [
            _evidence(
                key=f"fmp.cash_flow.{symbol}.{row.get('date', 'unknown')}",
                value=row,
                raw={},
                as_of_date=as_of_date,
            )
            for row in rows
        ]

    async def _get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        merged = {**params, "apikey": self._api_key}
        result = await self._http.get_json(path, params=merged)
        if not isinstance(result, list):
            return []
        return result


def _first_or_empty(data: list[dict[str, Any]]) -> dict[str, Any]:
    return data[0] if data else {}


def _filter_by_date(rows: list[dict[str, Any]], as_of: date) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        row_date_str = row.get("date")
        if not row_date_str:
            continue
        try:
            row_date = date.fromisoformat(str(row_date_str)[:10])
        except ValueError:
            continue
        if row_date <= as_of:
            out.append(row)
    return out


def _evidence(
    *,
    key: str,
    value: Any,
    raw: dict[str, Any],
    as_of_date: date,
) -> Evidence:
    eid = key
    return Evidence(
        id=eid,
        source=SourceType.FMP,
        key=key,
        value=value,
        raw=raw,
        citation=Citation(
            source=SourceType.FMP,
            evidence_id=eid,
            url=None,
            retrieved_at=datetime.now(UTC),
        ),
    )
