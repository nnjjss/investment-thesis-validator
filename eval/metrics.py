"""Pure metric functions over a (GoldenItem, agent ValidatorState result) pair.

All metrics return floats in [0, 1] except cost_per_item_usd. Each metric is a
pure function — easy to unit-test, reuse in CI, and aggregate across runs.
"""

from __future__ import annotations

from dataclasses import dataclass

from eval.schema import GoldenItem
from src.agent.state import Stance, ValidatorState


def tool_call_accuracy(item: GoldenItem, result: ValidatorState) -> float:
    """Recall over ``item.min_tools_called``: fraction of required tools that ran."""
    required = set(item.min_tools_called)
    if not required:
        return 1.0
    actual_ok = {
        trace.node
        for trace in result.traces
        if trace.status == "ok" and trace.node in required
    }
    return len(actual_ok) / len(required)


def retrieval_precision(item: GoldenItem, result: ValidatorState) -> float:
    """Precision: fraction of returned evidence whose key ∈ expected_evidence_keys.

    Key matching is prefix-based — an expected key like ``fmp.income_statement.AAPL``
    matches any actual key starting with that prefix (e.g. with a date suffix).
    """
    actual_keys = [ev.key for ev in result.evidence]
    if not actual_keys:
        # Vacuous precision — if expected was empty too, full credit; else zero.
        return 1.0 if not item.expected_evidence_keys else 0.0
    if not item.expected_evidence_keys:
        return 1.0  # no expectation declared → don't penalize
    matched = sum(
        1
        for k in actual_keys
        if any(k.startswith(prefix) for prefix in item.expected_evidence_keys)
    )
    return matched / len(actual_keys)


def final_answer_accuracy(item: GoldenItem, result: ValidatorState) -> float:
    """1.0 if predicted stance matches expected; 0.0 otherwise."""
    if result.verdict is None:
        return 0.0
    return 1.0 if result.verdict.stance == item.expected_stance else 0.0


def hallucination_rate(_item: GoldenItem, result: ValidatorState) -> float:
    """Fraction of non-UNCERTAIN claim_verdicts that cite NO evidence.

    The synthesizer node already drops invalid evidence ids; this metric catches
    the residual case where the model committed to a stance with no citations.
    Lower is better.
    """
    if result.verdict is None or not result.verdict.claim_verdicts:
        return 0.0
    committed = [
        cv for cv in result.verdict.claim_verdicts if cv.stance is not Stance.UNCERTAIN
    ]
    if not committed:
        return 0.0
    uncited = sum(
        1
        for cv in committed
        if not cv.supporting_evidence_ids and not cv.refuting_evidence_ids
    )
    return uncited / len(committed)


def cost_per_item_usd(_item: GoldenItem, result: ValidatorState) -> float:
    """Sum of trace.cost_usd across all node traces for this item."""
    return sum(trace.cost_usd for trace in result.traces)


@dataclass(frozen=True)
class ItemScores:
    item_id: str
    tool_call_accuracy: float
    retrieval_precision: float
    final_answer_accuracy: float
    hallucination_rate: float
    cost_usd: float


def score_item(item: GoldenItem, result: ValidatorState) -> ItemScores:
    return ItemScores(
        item_id=item.id,
        tool_call_accuracy=tool_call_accuracy(item, result),
        retrieval_precision=retrieval_precision(item, result),
        final_answer_accuracy=final_answer_accuracy(item, result),
        hallucination_rate=hallucination_rate(item, result),
        cost_usd=cost_per_item_usd(item, result),
    )


@dataclass(frozen=True)
class AggregateScores:
    n: int
    tool_call_accuracy: float
    retrieval_precision: float
    final_answer_accuracy: float
    hallucination_rate: float
    cost_usd_total: float
    cost_usd_mean: float


def aggregate(scores: list[ItemScores]) -> AggregateScores:
    if not scores:
        return AggregateScores(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    n = len(scores)
    total_cost = sum(s.cost_usd for s in scores)
    return AggregateScores(
        n=n,
        tool_call_accuracy=sum(s.tool_call_accuracy for s in scores) / n,
        retrieval_precision=sum(s.retrieval_precision for s in scores) / n,
        final_answer_accuracy=sum(s.final_answer_accuracy for s in scores) / n,
        hallucination_rate=sum(s.hallucination_rate for s in scores) / n,
        cost_usd_total=total_cost,
        cost_usd_mean=total_cost / n,
    )
