"""SEC EDGAR client.

EDGAR is the canonical filings source — chosen over FMP's wrapper. EDGAR
requires a User-Agent header identifying the requester (name + email);
requests without it return 403.

Point-in-time correctness: ``as_of_date`` clamps the upper bound of returned
filings (filing date <= as_of_date).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from src.agent.state import Citation, Evidence, SourceType
from src.ingestion._http import AsyncHTTPClient

EDGAR_DATA_BASE = "https://data.sec.gov"
EDGAR_FILING_BASE = "https://www.sec.gov/Archives/edgar/data"
DEFAULT_FORMS: tuple[str, ...] = ("10-K", "10-Q", "8-K")


class SECClient:
    def __init__(self, user_agent: str, *, base_url: str = EDGAR_DATA_BASE) -> None:
        if not user_agent.strip():
            raise ValueError(
                "SEC EDGAR requires a non-empty User-Agent identifying the requester "
                "(format: 'Company Name contact@example.com')."
            )
        self._http = AsyncHTTPClient(
            base_url=base_url,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> SECClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def recent_filings(
        self,
        cik: str,
        *,
        as_of_date: date,
        forms: tuple[str, ...] = DEFAULT_FORMS,
        limit: int = 20,
    ) -> list[Evidence]:
        cik_padded = cik.lstrip("0").zfill(10)
        data = await self._http.get_json(f"/submissions/CIK{cik_padded}.json")
        recent = (data.get("filings", {}) or {}).get("recent", {}) if isinstance(data, dict) else {}

        rows = _zip_columns(recent)
        filtered = [
            row
            for row in rows
            if row.get("form") in forms and _filing_on_or_before(row, as_of_date)
        ][:limit]

        return [_evidence_for(cik_padded, row, as_of_date) for row in filtered]


def _zip_columns(recent: dict[str, Any]) -> list[dict[str, Any]]:
    keys = ("accessionNumber", "filingDate", "form", "primaryDocument", "primaryDocDescription")
    cols = [recent.get(k, []) for k in keys]
    if not cols[0]:
        return []
    return [dict(zip(keys, row, strict=False)) for row in zip(*cols, strict=False)]


def _filing_on_or_before(row: dict[str, Any], as_of: date) -> bool:
    raw = row.get("filingDate")
    if not raw:
        return False
    try:
        return date.fromisoformat(str(raw)[:10]) <= as_of
    except ValueError:
        return False


def _evidence_for(cik_padded: str, row: dict[str, Any], as_of_date: date) -> Evidence:
    accession = str(row.get("accessionNumber", "")).replace("-", "")
    primary = row.get("primaryDocument", "")
    url = (
        f"{EDGAR_FILING_BASE}/{int(cik_padded)}/{accession}/{primary}"
        if accession and primary
        else None
    )
    eid = f"sec.{row.get('form', 'unknown')}.{cik_padded}.{row.get('filingDate', 'unknown')}"
    return Evidence(
        id=eid,
        source=SourceType.SEC,
        key=eid,
        value={
            "form": row.get("form"),
            "filingDate": row.get("filingDate"),
            "accessionNumber": row.get("accessionNumber"),
            "primaryDocDescription": row.get("primaryDocDescription"),
        },
        raw={"row": row, "as_of_date": as_of_date.isoformat()},
        citation=Citation(
            source=SourceType.SEC,
            evidence_id=eid,
            url=url,
            retrieved_at=datetime.now(UTC),
        ),
    )
