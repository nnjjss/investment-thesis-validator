"""Node: parse_thesis — Haiku-backed extraction of ThesisClaims via tool-use.

Returns a partial state dict (LangGraph merge-style) containing ``claims`` and
an appended ``traces`` entry. Pure function over (state, llm) for testability.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.agent.llm import LLMClient
from src.agent.state import ClaimType, NodeTrace, ThesisClaim, ValidatorState

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "parse_thesis.md"

EXTRACT_CLAIMS_TOOL: dict[str, Any] = {
    "name": "extract_claims",
    "description": "Return the atomic claims found in the user's thesis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "subject": {"type": "string"},
                        "claim_text": {"type": "string"},
                        "claim_type": {
                            "type": "string",
                            "enum": [t.value for t in ClaimType],
                        },
                    },
                    "required": ["id", "subject", "claim_text", "claim_type"],
                },
            }
        },
        "required": ["claims"],
    },
}


async def parse_thesis(
    state: ValidatorState,
    llm: LLMClient,
    *,
    model: str,
) -> dict[str, Any]:
    started = datetime.now(UTC)
    user_text = (
        f"Ticker: {state.ticker}\n"
        f"As of: {state.as_of_date.isoformat()}\n"
        f"Thesis:\n{state.thesis}"
    )

    response = await llm.acall(
        model=model,
        system=PROMPT_PATH.read_text(encoding="utf-8"),
        messages=[{"role": "user", "content": user_text}],
        tools=[EXTRACT_CLAIMS_TOOL],
        tool_choice={"type": "tool", "name": "extract_claims"},
        max_tokens=2048,
    )
    finished = datetime.now(UTC)

    if not response.tool_uses:
        raise ValueError("parse_thesis: model did not call extract_claims")

    raw_claims = response.tool_uses[0].input.get("claims", [])
    claims = [
        ThesisClaim(
            id=row["id"],
            subject=row["subject"],
            claim_text=row["claim_text"],
            claim_type=ClaimType(row["claim_type"]),
        )
        for row in raw_claims
    ]

    trace = NodeTrace(
        node="parse_thesis",
        started_at=started,
        finished_at=finished,
        tokens_in=response.usage.input_tokens,
        tokens_out=response.usage.output_tokens,
        cache_read=response.usage.cache_read_tokens,
        cache_write=response.usage.cache_creation_tokens,
        cost_usd=response.cost_usd,
    )

    return {"claims": claims, "traces": [*state.traces, trace]}
