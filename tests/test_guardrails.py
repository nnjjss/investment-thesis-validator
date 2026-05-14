from __future__ import annotations

from datetime import UTC, date, datetime

from src.agent.state import (
    Citation,
    ClaimVerdict,
    Confidence,
    Evidence,
    SourceType,
    Stance,
    ValidatorState,
    Verdict,
)
from src.guardrails.citation_binding import unsupported_claims
from src.guardrails.numeric_check import numeric_findings


def _ev(eid: str, value: dict) -> Evidence:
    return Evidence(
        id=eid,
        source=SourceType.FMP,
        key=eid,
        value=value,
        citation=Citation(
            source=SourceType.FMP, evidence_id=eid, retrieved_at=datetime.now(UTC)
        ),
    )


def _state_with_summary(summary: str, evidence: list[Evidence]) -> ValidatorState:
    return ValidatorState(
        thesis="t",
        ticker="X",
        as_of_date=date(2026, 5, 13),
        evidence=evidence,
        verdict=Verdict(
            stance=Stance.SUPPORTED,
            confidence=Confidence.MEDIUM,
            summary=summary,
            claim_verdicts=[],
        ),
    )


def test_numeric_findings_flags_uncited_percent() -> None:
    state = _state_with_summary(
        summary="Operating margin reached 42% in the quarter.",
        evidence=[_ev("e1", {"operatingMargin": 0.30})],
    )
    findings = numeric_findings(state)
    flagged = [f.span for f in findings]
    assert any("42%" in span for span in flagged)


def test_numeric_findings_passes_when_value_in_evidence() -> None:
    state = _state_with_summary(
        summary="Operating margin reached 30% in the quarter.",
        evidence=[_ev("e1", {"operatingMargin": "30%"})],
    )
    assert numeric_findings(state) == []


def test_numeric_findings_ignores_years_and_small_ints() -> None:
    state = _state_with_summary(
        summary="Q3 2025 results were reported. There are 4 segments.",
        evidence=[_ev("e1", {})],
    )
    assert numeric_findings(state) == []


def test_numeric_findings_no_verdict() -> None:
    state = ValidatorState(
        thesis="t",
        ticker="X",
        as_of_date=date(2026, 5, 13),
    )
    assert numeric_findings(state) == []


def test_unsupported_claims_flags_committed_no_cite() -> None:
    state = _state_with_summary(summary="x", evidence=[])
    state = state.model_copy(
        update={
            "verdict": Verdict(
                stance=Stance.SUPPORTED,
                confidence=Confidence.MEDIUM,
                summary="x",
                claim_verdicts=[
                    ClaimVerdict(
                        claim_id="c1", stance=Stance.SUPPORTED, rationale="r"
                    ),
                    ClaimVerdict(
                        claim_id="c2",
                        stance=Stance.REFUTED,
                        rationale="r",
                        refuting_evidence_ids=["e1"],
                    ),
                    ClaimVerdict(
                        claim_id="c3", stance=Stance.UNCERTAIN, rationale="r"
                    ),
                ],
            )
        }
    )
    flagged = unsupported_claims(state)
    assert [u.claim_id for u in flagged] == ["c1"]


def test_unsupported_claims_no_verdict() -> None:
    state = ValidatorState(
        thesis="t",
        ticker="X",
        as_of_date=date(2026, 5, 13),
    )
    assert unsupported_claims(state) == []
