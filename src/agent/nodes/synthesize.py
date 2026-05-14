"""Node: synthesize — Opus 4.7 produces the final Verdict via tool_use."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.agent.llm import LLMClient
from src.agent.state import (
    ClaimVerdict,
    Confidence,
    NodeTrace,
    Stance,
    ValidatorState,
    Verdict,
)

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "synthesizer_system.md"

PRODUCE_VERDICT_TOOL: dict[str, Any] = {
    "name": "produce_verdict",
    "description": "Return the structured verdict for the investment thesis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "stance": {"type": "string", "enum": [s.value for s in Stance]},
            "confidence": {"type": "string", "enum": [c.value for c in Confidence]},
            "summary": {"type": "string"},
            "claim_verdicts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim_id": {"type": "string"},
                        "stance": {"type": "string", "enum": [s.value for s in Stance]},
                        "rationale": {"type": "string"},
                        "supporting_evidence_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "refuting_evidence_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["claim_id", "stance", "rationale"],
                },
            },
            "evidence_used": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "stance",
            "confidence",
            "summary",
            "claim_verdicts",
            "evidence_used",
        ],
    },
}


def _serialize_evidence(state: ValidatorState) -> str:
    items = [
        {
            "id": ev.id,
            "source": ev.source.value,
            "key": ev.key,
            "value": ev.value,
        }
        for ev in state.evidence
    ]
    return json.dumps(items, default=str, ensure_ascii=False)[:80_000]


async def synthesize(
    state: ValidatorState,
    llm: LLMClient,
    *,
    model: str,
) -> dict[str, Any]:
    started = datetime.now(UTC)

    contradiction_block = (
        json.dumps(
            {
                "supporting_evidence_ids": state.contradiction.supporting_evidence_ids,
                "refuting_evidence_ids": state.contradiction.refuting_evidence_ids,
                "rationale": state.contradiction.rationale,
            },
            ensure_ascii=False,
        )
        if state.contradiction is not None
        else "{}"
    )

    claim_lines = "\n".join(f"- {c.id}: {c.claim_text}" for c in state.claims)
    user_text = (
        f"Thesis:\n{state.thesis}\n\n"
        f"As of: {state.as_of_date.isoformat()}\nTicker: {state.ticker}\n\n"
        f"Claims:\n{claim_lines}\n\n"
        f"Contradiction analysis:\n{contradiction_block}\n\n"
        f"Evidence (JSON):\n{_serialize_evidence(state)}"
    )

    response = await llm.acall(
        model=model,
        system=PROMPT_PATH.read_text(encoding="utf-8"),
        messages=[{"role": "user", "content": user_text}],
        tools=[PRODUCE_VERDICT_TOOL],
        tool_choice={"type": "tool", "name": "produce_verdict"},
        max_tokens=4096,
    )

    if not response.tool_uses:
        raise ValueError("synthesize: model did not call produce_verdict")

    raw = response.tool_uses[0].input
    valid_ids = {ev.id for ev in state.evidence}
    valid_claim_ids = {c.id for c in state.claims}

    raw_claim_verdicts = raw.get("claim_verdicts", [])
    claim_verdicts = []
    for cv in raw_claim_verdicts:
        if cv.get("claim_id") not in valid_claim_ids:
            continue
        claim_verdicts.append(
            ClaimVerdict(
                claim_id=cv["claim_id"],
                stance=Stance(cv["stance"]),
                rationale=str(cv.get("rationale", "")),
                supporting_evidence_ids=[
                    eid for eid in cv.get("supporting_evidence_ids", []) if eid in valid_ids
                ],
                refuting_evidence_ids=[
                    eid for eid in cv.get("refuting_evidence_ids", []) if eid in valid_ids
                ],
            )
        )

    verdict = Verdict(
        stance=Stance(raw["stance"]),
        confidence=Confidence(raw["confidence"]),
        summary=str(raw.get("summary", "")),
        claim_verdicts=claim_verdicts,
        evidence_used=[eid for eid in raw.get("evidence_used", []) if eid in valid_ids],
        cost_usd=response.cost_usd,
    )

    finished = datetime.now(UTC)
    trace = NodeTrace(
        node="synthesize",
        started_at=started,
        finished_at=finished,
        tokens_in=response.usage.input_tokens,
        tokens_out=response.usage.output_tokens,
        cache_read=response.usage.cache_read_tokens,
        cache_write=response.usage.cache_creation_tokens,
        cost_usd=response.cost_usd,
    )
    return {"verdict": verdict, "traces": [*state.traces, trace]}
