from __future__ import annotations

from datetime import date

import pytest

from src.agent.nodes.parse_thesis import parse_thesis
from src.agent.state import ClaimType, ValidatorState
from tests.agent.conftest import FakeLLMClient, make_tool_response


@pytest.mark.asyncio
async def test_parse_thesis_extracts_claims_and_appends_trace() -> None:
    state = ValidatorState(
        thesis="TSM is undervalued at 18x forward P/E given AI capex tailwind.",
        ticker="tsm",  # exercise auto-uppercase
        as_of_date=date(2026, 5, 13),
    )

    fake = FakeLLMClient(
        response_factory=lambda _: make_tool_response(
            name="extract_claims",
            tool_input={
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
                        "claim_text": "AI capex is a tailwind for TSM revenue",
                        "claim_type": "fundamental",
                    },
                ]
            },
        )
    )

    result = await parse_thesis(state, fake, model="claude-haiku-4-5-20251001")

    assert state.ticker == "TSM"  # auto-upper
    assert len(result["claims"]) == 2
    assert result["claims"][0].id == "c1"
    assert result["claims"][1].claim_type is ClaimType.FUNDAMENTAL
    assert len(result["traces"]) == 1
    assert result["traces"][0].node == "parse_thesis"


@pytest.mark.asyncio
async def test_parse_thesis_raises_when_tool_not_called() -> None:
    state = ValidatorState(thesis="x", ticker="X", as_of_date=date(2026, 5, 13))
    fake = FakeLLMClient(
        response_factory=lambda _: make_tool_response(
            name="extract_claims", tool_input={}
        )._replace_tool_uses_empty()  # type: ignore[attr-defined]
    )

    # Use a simpler approach: factory returns a response with no tool_uses
    from src.agent.llm import LLMResponse, LLMUsage

    fake = FakeLLMClient(
        response_factory=lambda _: LLMResponse(
            model="claude-haiku-4-5-20251001",
            text="oops plain text",
            tool_uses=[],
            usage=LLMUsage(0, 0, 0, 0),
            cost_usd=0.0,
            stop_reason="end_turn",
        )
    )

    with pytest.raises(ValueError, match="did not call extract_claims"):
        await parse_thesis(state, fake, model="claude-haiku-4-5-20251001")


@pytest.mark.asyncio
async def test_parse_thesis_passes_tool_choice_and_caching() -> None:
    state = ValidatorState(thesis="x", ticker="X", as_of_date=date(2026, 5, 13))
    fake = FakeLLMClient(
        response_factory=lambda _: make_tool_response(
            name="extract_claims", tool_input={"claims": []}
        )
    )
    await parse_thesis(state, fake, model="claude-haiku-4-5-20251001")

    sent = fake.calls[0]
    assert sent["tool_choice"] == {"type": "tool", "name": "extract_claims"}
    assert sent["model"] == "claude-haiku-4-5-20251001"
    assert isinstance(sent["system"], str) and "atomic" in sent["system"]
