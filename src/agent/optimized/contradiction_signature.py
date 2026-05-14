"""DSPy signature for the contradiction node.

Off the hot path — DSPy is a dev/optimization-time dependency. The runtime
agent uses prompt files; if compiled prompts are persisted under
``compiled/contradiction_v1.json`` and ``USE_DSPY_PROMPTS=1`` is set, a future
loader will swap them in. Today this module exists to lock the I/O contract
the optimizer compiles against.
"""

from __future__ import annotations

import dspy


class ContradictionSignature(dspy.Signature):  # type: ignore[misc]
    """Partition evidence into supporting / refuting / neutral for an investment thesis.

    See ``src/agent/prompts/contradiction.md`` for the canonical instructions
    used by the runtime node. DSPy will start from these and bootstrap better
    few-shot demonstrations against the eval harness.
    """

    thesis: str = dspy.InputField(desc="the investment thesis under review")
    claims_jsonl: str = dspy.InputField(
        desc="extracted claims, one JSON object per line"
    )
    evidence_jsonl: str = dspy.InputField(
        desc="evidence bundle as JSON list of {id, source, key, value}"
    )

    supporting_evidence_ids: list[str] = dspy.OutputField(
        desc="evidence ids that strengthen the thesis (must be present in input)"
    )
    refuting_evidence_ids: list[str] = dspy.OutputField(
        desc="evidence ids that directly contradict the thesis"
    )
    rationale: str = dspy.OutputField(
        desc="2-3 sentences naming the most important supporting and refuting items"
    )
