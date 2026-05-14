"""Node: plan_evidence — Haiku-backed planner that decides which tools to fan out to."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.agent.llm import LLMClient
from src.agent.state import NodeTrace, ToolCallPlan, ValidatorState

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "plan_evidence.md"

PLAN_EVIDENCE_TOOL: dict[str, Any] = {
    "name": "plan_evidence_tools",
    "description": "Decide which data sources to query for the given claims.",
    "input_schema": {
        "type": "object",
        "properties": {
            "need_stock_data": {"type": "boolean"},
            "need_news": {"type": "boolean"},
            "need_filings": {"type": "boolean"},
            "news_query": {
                "type": "string",
                "description": "search query if need_news is true",
            },
            "rationale": {"type": "string"},
        },
        "required": ["need_stock_data", "need_news", "need_filings", "rationale"],
    },
}


async def plan_evidence(
    state: ValidatorState,
    llm: LLMClient,
    *,
    model: str,
) -> dict[str, Any]:
    if not state.claims:
        raise ValueError("plan_evidence: state.claims is empty — run parse_thesis first")

    started = datetime.now(UTC)
    claim_lines = "\n".join(
        f"- ({c.claim_type.value}) {c.id}: {c.claim_text}" for c in state.claims
    )
    user_text = (
        f"Ticker: {state.ticker}\nAs of: {state.as_of_date.isoformat()}\n"
        f"Claims:\n{claim_lines}"
    )

    response = await llm.acall(
        model=model,
        system=PROMPT_PATH.read_text(encoding="utf-8"),
        messages=[{"role": "user", "content": user_text}],
        tools=[PLAN_EVIDENCE_TOOL],
        tool_choice={"type": "tool", "name": "plan_evidence_tools"},
        max_tokens=512,
    )
    finished = datetime.now(UTC)

    if not response.tool_uses:
        raise ValueError("plan_evidence: model did not call plan_evidence_tools")

    raw = response.tool_uses[0].input
    plan = ToolCallPlan(
        need_stock_data=bool(raw["need_stock_data"]),
        need_news=bool(raw["need_news"]),
        need_filings=bool(raw["need_filings"]),
        news_query=raw.get("news_query") or None,
        rationale=str(raw.get("rationale", "")),
    )

    trace = NodeTrace(
        node="plan_evidence",
        started_at=started,
        finished_at=finished,
        tokens_in=response.usage.input_tokens,
        tokens_out=response.usage.output_tokens,
        cache_read=response.usage.cache_read_tokens,
        cache_write=response.usage.cache_creation_tokens,
        cost_usd=response.cost_usd,
    )

    return {"tool_plan": plan, "traces": [*state.traces, trace]}
