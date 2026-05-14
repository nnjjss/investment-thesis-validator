"""Numeric guardrail: every financial-looking number in the verdict text must
appear somewhere in the evidence values.

This is *post-hoc* detection, not enforcement — we return a list of suspicious
spans rather than mutating the verdict. The eval harness exposes
``hallucination_rate``; this module gives the API a hook to flag specific
numeric claims for client-side highlighting.

Heuristic: only consider numbers that look financial — those with one of
``%``, ``$``, ``B``, ``M``, ``bn``, ``mn``, ``x`` (multiple) suffixes, or with
a decimal point. Bare small ints (years, counts, claim ids) are ignored to
keep false positives low.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from src.agent.state import ValidatorState

# Match patterns like "25%", "$1.2B", "18.5x", "0.27", "12,500", "150 million".
_FINANCIAL_NUMBER_RE = re.compile(
    r"""
    \$?                              # optional leading $
    \d{1,3}(?:,\d{3})*               # integer with thousands separators
    (?:\.\d+)?                       # optional decimal
    \s*
    (?:%|x|bn|mn|million|billion|B|M)?  # optional unit
    """,
    re.IGNORECASE | re.VERBOSE,
)

_FINANCIAL_INT_BLACKLIST = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10"}


@dataclass(frozen=True)
class NumericFinding:
    span: str
    found_in_evidence: bool


def _looks_financial(span: str) -> bool:
    """Filter out bare years and small ints."""
    stripped = span.strip().rstrip(".,;)").lstrip("(")
    if stripped in _FINANCIAL_INT_BLACKLIST:
        return False
    if re.fullmatch(r"\d{4}", stripped):  # year
        return False
    if not any(c.isdigit() for c in stripped):
        return False
    has_unit = any(
        unit in stripped.lower() for unit in ("%", "x", "bn", "mn", "million", "billion")
    )
    has_decimal = "." in stripped
    has_dollar = "$" in stripped
    has_thousands = "," in stripped
    return has_unit or has_decimal or has_dollar or has_thousands


def _evidence_corpus(state: ValidatorState) -> str:
    """Flatten all evidence values to a single search string."""
    return json.dumps(
        [{"value": ev.value, "raw": ev.raw} for ev in state.evidence],
        default=str,
        ensure_ascii=False,
    )


def numeric_findings(state: ValidatorState) -> list[NumericFinding]:
    """Return numeric spans in verdict.summary (and per-claim rationales) that
    don't appear verbatim in any evidence value. Empty list = clean.
    """
    if state.verdict is None:
        return []

    text_parts: list[str] = [state.verdict.summary]
    text_parts.extend(cv.rationale for cv in state.verdict.claim_verdicts)
    text = " ".join(text_parts)

    corpus = _evidence_corpus(state)

    findings: list[NumericFinding] = []
    seen: set[str] = set()
    for match in _FINANCIAL_NUMBER_RE.finditer(text):
        span = match.group(0).strip()
        if not span or span in seen:
            continue
        if not _looks_financial(span):
            continue
        seen.add(span)
        # Strip $ and unit suffixes for fuzzier matching against evidence.
        normalized = re.sub(r"[\$,%xXbBmMnN\s]+$", "", span).rstrip()
        normalized = normalized.lstrip("$").replace(",", "")
        found = normalized in corpus or span in corpus
        findings.append(NumericFinding(span=span, found_in_evidence=found))

    return [f for f in findings if not f.found_in_evidence]
