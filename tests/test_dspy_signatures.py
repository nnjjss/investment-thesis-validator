"""DSPy signature smoke tests.

DSPy is a dev-time dependency; we don't run actual compilation in CI. These
tests just confirm the signature classes load and expose the expected fields.
"""

from __future__ import annotations

import importlib.util

import pytest


@pytest.mark.skipif(
    importlib.util.find_spec("dspy") is None,
    reason="dspy not installed in this env",
)
def test_signatures_have_expected_fields() -> None:
    from src.agent.optimized.contradiction_signature import ContradictionSignature
    from src.agent.optimized.synthesize_signature import SynthesizeSignature

    contradiction_fields = set(ContradictionSignature.model_fields)
    assert {"thesis", "claims_jsonl", "evidence_jsonl"} <= contradiction_fields
    assert {
        "supporting_evidence_ids",
        "refuting_evidence_ids",
        "rationale",
    } <= contradiction_fields

    synth_fields = set(SynthesizeSignature.model_fields)
    assert {"thesis", "claims_jsonl", "contradiction_json", "evidence_jsonl"} <= synth_fields
    assert {
        "stance",
        "confidence",
        "summary",
        "claim_verdicts_json",
        "evidence_used",
    } <= synth_fields
