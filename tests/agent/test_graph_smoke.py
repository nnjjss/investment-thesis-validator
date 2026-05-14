from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import pytest
import respx

from src.agent.graph import GraphModels, build_graph
from src.agent.llm import LLMResponse, LLMToolUse, LLMUsage
from src.agent.state import Stance, ValidatorState
from src.ingestion.fmp import FMP_BASE_URL, FMPClient
from src.ingestion.news import NewsClient
from src.ingestion.sec import SECClient
from tests.agent.conftest import FakeLLMClient


def _routed_llm() -> FakeLLMClient:
    """LLM that returns a different canned response per tool_choice.name."""

    by_name: dict[str, LLMResponse] = {
        "extract_claims": _tool_response(
            "extract_claims",
            {
                "claims": [
                    {
                        "id": "c1",
                        "subject": "TSM",
                        "claim_text": "TSM trades at 18x forward P/E",
                        "claim_type": "valuation",
                    },
                    {
                        "id": "c2",
                        "subject": "TSM",
                        "claim_text": "AI capex tailwind drives revenue",
                        "claim_type": "fundamental",
                    },
                ]
            },
        ),
        "plan_evidence_tools": _tool_response(
            "plan_evidence_tools",
            {
                "need_stock_data": True,
                "need_news": False,
                "need_filings": False,
                "rationale": "fundamentals from FMP cover both claims",
            },
        ),
        "classify_evidence": _tool_response(
            "classify_evidence",
            {
                "supporting_evidence_ids": ["fmp.profile.TSM", "fmp.quote.TSM"],
                "refuting_evidence_ids": [],
                "rationale": "Profile and quote both consistent with thesis.",
            },
        ),
        "produce_verdict": _tool_response(
            "produce_verdict",
            {
                "stance": "SUPPORTED",
                "confidence": "MEDIUM",
                "summary": "TSM fundamentals broadly consistent with thesis.",
                "claim_verdicts": [
                    {
                        "claim_id": "c1",
                        "stance": "SUPPORTED",
                        "rationale": "Quote-derived multiple aligns.",
                        "supporting_evidence_ids": ["fmp.quote.TSM"],
                        "refuting_evidence_ids": [],
                    },
                    {
                        "claim_id": "c2",
                        "stance": "UNCERTAIN",
                        "rationale": "Income data alone cannot prove AI tailwind.",
                        "supporting_evidence_ids": [],
                        "refuting_evidence_ids": [],
                    },
                ],
                "evidence_used": ["fmp.profile.TSM", "fmp.quote.TSM"],
            },
        ),
    }

    def factory(kwargs: dict[str, Any]) -> LLMResponse:
        tool_name = (kwargs.get("tool_choice") or {}).get("name")
        if tool_name not in by_name:
            raise AssertionError(f"unexpected tool_choice in smoke test: {tool_name}")
        return by_name[tool_name]

    return FakeLLMClient(response_factory=factory)


def _tool_response(name: str, tool_input: dict[str, Any]) -> LLMResponse:
    return LLMResponse(
        model="fake",
        text="",
        tool_uses=[LLMToolUse(id=f"tu_{name}", name=name, input=tool_input)],
        usage=LLMUsage(
            input_tokens=100,
            output_tokens=50,
            cache_creation_tokens=0,
            cache_read_tokens=0,
        ),
        cost_usd=0.001,
        stop_reason="tool_use",
    )


@pytest.mark.asyncio
@respx.mock
async def test_graph_smoke_supported_verdict() -> None:
    respx.get(f"{FMP_BASE_URL}/profile").mock(
        return_value=httpx.Response(
            200, json=[{"symbol": "TSM", "companyName": "TSMC", "sector": "Technology"}]
        )
    )
    respx.get(f"{FMP_BASE_URL}/quote").mock(
        return_value=httpx.Response(200, json=[{"symbol": "TSM", "price": 180.0, "pe": 18.2}])
    )
    respx.get(f"{FMP_BASE_URL}/income-statement").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"date": "2026-03-31", "revenue": 25000000000, "netIncome": 9000000000},
                {"date": "2025-12-31", "revenue": 24000000000, "netIncome": 8500000000},
            ],
        )
    )
    respx.get(f"{FMP_BASE_URL}/ratios").mock(
        return_value=httpx.Response(
            200, json=[{"date": "2026-03-31", "peRatio": 18.5, "roe": 0.27}]
        )
    )

    fake_llm = _routed_llm()
    fmp = FMPClient(api_key="test")
    news = NewsClient(api_key="test")
    sec = SECClient(user_agent="ITV Test test@example.com")

    graph = build_graph(
        llm=fake_llm,
        fmp=fmp,
        news=news,
        sec=sec,
        models=GraphModels(cheap="claude-haiku-4-5-20251001", validator="claude-opus-4-7"),
    )

    initial = ValidatorState(
        thesis="TSM is undervalued at 18x forward P/E given AI capex tailwind",
        ticker="TSM",
        as_of_date=date(2026, 5, 13),
    )

    final = await graph.ainvoke(initial)
    state = final if isinstance(final, ValidatorState) else ValidatorState.model_validate(final)

    assert state.verdict is not None
    assert state.verdict.stance is Stance.SUPPORTED
    assert state.verdict.summary  # non-empty
    assert len(state.verdict.claim_verdicts) == 2
    assert any(state.verdict.evidence_used)  # >= 1 evidence cited

    # Evidence: profile + quote + income (filtered to date <= as_of) + ratios
    assert len(state.evidence) >= 4
    assert any(ev.id == "fmp.profile.TSM" for ev in state.evidence)
    assert any(ev.id == "fmp.quote.TSM" for ev in state.evidence)

    # Traces: 7 nodes ran (fetch_news + fetch_filings emit "skipped" traces)
    node_names = [t.node for t in state.traces]
    assert node_names == [
        "parse_thesis",
        "plan_evidence",
        "fetch_stock",
        "fetch_news",
        "fetch_filings",
        "contradiction",
        "synthesize",
    ]
    skipped = {t.node for t in state.traces if t.status == "skipped"}
    assert skipped == {"fetch_news", "fetch_filings"}
    await fmp.aclose()
    await news.aclose()
    await sec.aclose()
