"""Citation binding guardrail.

The synthesizer node already drops invalid evidence ids at construction time
(see ``src/agent/nodes/synthesize.py``). This module is the post-hoc audit:
it scans the final Verdict for committed-stance ``ClaimVerdict`` rows that
cite no evidence, and exposes them as ``UnsupportedClaim`` for the API to
surface to the client.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.agent.state import Stance, ValidatorState


@dataclass(frozen=True)
class UnsupportedClaim:
    claim_id: str
    stance: Stance
    rationale: str


def unsupported_claims(state: ValidatorState) -> list[UnsupportedClaim]:
    if state.verdict is None:
        return []
    return [
        UnsupportedClaim(claim_id=cv.claim_id, stance=cv.stance, rationale=cv.rationale)
        for cv in state.verdict.claim_verdicts
        if cv.stance is not Stance.UNCERTAIN
        and not cv.supporting_evidence_ids
        and not cv.refuting_evidence_ids
    ]
