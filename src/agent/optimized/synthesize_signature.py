"""DSPy signature for the synthesizer node."""

from __future__ import annotations

import dspy


class SynthesizeSignature(dspy.Signature):  # type: ignore[misc]
    """Produce the structured Verdict for an investment thesis.

    See ``src/agent/prompts/synthesizer_system.md`` for canonical instructions.
    The runtime model is Opus 4.7; DSPy compile against the same model so
    bootstrapped demonstrations reflect realistic behavior.
    """

    thesis: str = dspy.InputField(desc="the investment thesis under review")
    claims_jsonl: str = dspy.InputField(desc="atomic claims, one JSON object per line")
    contradiction_json: str = dspy.InputField(
        desc="contradiction analysis json with supporting_evidence_ids, "
        "refuting_evidence_ids, rationale"
    )
    evidence_jsonl: str = dspy.InputField(desc="evidence bundle as JSON")

    stance: str = dspy.OutputField(desc="SUPPORTED | REFUTED | UNCERTAIN")
    confidence: str = dspy.OutputField(desc="LOW | MEDIUM | HIGH")
    summary: str = dspy.OutputField(desc="3-6 sentence summary for a portfolio manager")
    claim_verdicts_json: str = dspy.OutputField(
        desc="JSON array of {claim_id, stance, rationale, supporting_evidence_ids, "
        "refuting_evidence_ids}"
    )
    evidence_used: list[str] = dspy.OutputField(
        desc="evidence ids actually relied on for the verdict"
    )
