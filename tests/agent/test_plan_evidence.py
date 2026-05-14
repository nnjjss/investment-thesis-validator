from __future__ import annotations

from datetime import date

import pytest

from src.agent.nodes.plan_evidence import plan_evidence
from src.agent.state import ClaimType, ThesisClaim, ValidatorState
from tests.agent.conftest import FakeLLMClient, make_tool_response


def _state_with_claims() -> ValidatorState:
    return ValidatorState(
        thesis="...",
        ticker="NVDA",
        as_of_date=date(2026, 5, 13),
        claims=[
            ThesisClaim(
                id="c1",
                subject="NVDA",
                claim_text="Q3 revenue grew >40% YoY",
                claim_type=ClaimType.FUNDAMENTAL,
            ),
            ThesisClaim(
                id="c2",
                subject="NVDA",
                claim_text="Sentiment positive after analyst upgrade",
                claim_type=ClaimType.SENTIMENT,
            ),
        ],
    )


@pytest.mark.asyncio
async def test_plan_evidence_returns_typed_plan() -> None:
    state = _state_with_claims()
    fake = FakeLLMClient(
        response_factory=lambda _: make_tool_response(
            name="plan_evidence_tools",
            tool_input={
                "need_stock_data": True,
                "need_news": True,
                "need_filings": False,
                "news_query": "NVDA Q3 earnings",
                "rationale": "c1 needs FMP fundamentals; c2 needs news.",
            },
        )
    )

    result = await plan_evidence(state, fake, model="claude-haiku-4-5-20251001")

    plan = result["tool_plan"]
    assert plan.need_stock_data is True
    assert plan.need_news is True
    assert plan.need_filings is False
    assert plan.news_query == "NVDA Q3 earnings"
    assert "c1 needs FMP" in plan.rationale
    assert result["traces"][0].node == "plan_evidence"


@pytest.mark.asyncio
async def test_plan_evidence_rejects_empty_claims() -> None:
    empty_state = ValidatorState(thesis="x", ticker="X", as_of_date=date(2026, 5, 13))
    fake = FakeLLMClient(
        response_factory=lambda _: make_tool_response(
            name="plan_evidence_tools", tool_input={}
        )
    )
    with pytest.raises(ValueError, match="state.claims is empty"):
        await plan_evidence(empty_state, fake, model="claude-haiku-4-5-20251001")
