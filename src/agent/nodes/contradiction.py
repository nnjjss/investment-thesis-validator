"""Node: contradiction_check — Haiku-backed partition of evidence into supporting/refuting."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.agent.llm import LLMClient
from src.agent.state import ContradictionResult, NodeTrace, ValidatorState

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "contradiction.md"

CLASSIFY_EVIDENCE_TOOL: dict[str, Any] = {
    "name": "classify_evidence",
    "description": "Partition the evidence into supporting and refuting groups.",
    "input_schema": {
        "type": "object",
        "properties": {
            "supporting_evidence_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "refuting_evidence_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "rationale": {"type": "string"},
        },
        "required": ["supporting_evidence_ids", "refuting_evidence_ids", "rationale"],
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
    return json.dumps(items, default=str, ensure_ascii=False)[:60_000]


async def contradiction(
    state: ValidatorState,
    llm: LLMClient,
    *,
    model: str,
) -> dict[str, Any]:
    started = datetime.now(UTC)

    if not state.evidence:
        finished = datetime.now(UTC)
        return {
            "contradiction": ContradictionResult(rationale="no evidence to classify"),
            "traces": [
                *state.traces,
                NodeTrace(
                    node="contradiction",
                    started_at=started,
                    finished_at=finished,
                    status="skipped",
                ),
            ],
        }

    claim_lines = "\n".join(f"- {c.id}: {c.claim_text}" for c in state.claims)
    user_text = (
        f"Thesis:\n{state.thesis}\n\n"
        f"Claims:\n{claim_lines}\n\n"
        f"Evidence (JSON):\n{_serialize_evidence(state)}"
    )

    response = await llm.acall(
        model=model,
        system=PROMPT_PATH.read_text(encoding="utf-8"),
        messages=[{"role": "user", "content": user_text}],
        tools=[CLASSIFY_EVIDENCE_TOOL],
        tool_choice={"type": "tool", "name": "classify_evidence"},
        max_tokens=1024,
    )

    if not response.tool_uses:
        raise ValueError("contradiction: model did not call classify_evidence")

    raw = response.tool_uses[0].input
    valid_ids = {ev.id for ev in state.evidence}
    result = ContradictionResult(
        supporting_evidence_ids=[
            eid for eid in raw.get("supporting_evidence_ids", []) if eid in valid_ids
        ],
        refuting_evidence_ids=[
            eid for eid in raw.get("refuting_evidence_ids", []) if eid in valid_ids
        ],
        rationale=str(raw.get("rationale", "")),
    )

    finished = datetime.now(UTC)
    trace = NodeTrace(
        node="contradiction",
        started_at=started,
        finished_at=finished,
        tokens_in=response.usage.input_tokens,
        tokens_out=response.usage.output_tokens,
        cache_read=response.usage.cache_read_tokens,
        cache_write=response.usage.cache_creation_tokens,
        cost_usd=response.cost_usd,
    )
    return {"contradiction": result, "traces": [*state.traces, trace]}
