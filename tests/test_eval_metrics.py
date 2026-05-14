from __future__ import annotations

from datetime import UTC, date, datetime

from eval.metrics import (
    aggregate,
    final_answer_accuracy,
    hallucination_rate,
    retrieval_precision,
    score_item,
    tool_call_accuracy,
)
from eval.schema import GoldenItem
from src.agent.state import (
    Citation,
    ClaimVerdict,
    Confidence,
    Evidence,
    NodeTrace,
    SourceType,
    Stance,
    ValidatorState,
    Verdict,
)


def _state(
    *,
    evidence: list[Evidence] | None = None,
    verdict: Verdict | None = None,
    traces: list[NodeTrace] | None = None,
) -> ValidatorState:
    return ValidatorState(
        thesis="t",
        ticker="X",
        as_of_date=date(2026, 5, 13),
        evidence=evidence or [],
        verdict=verdict,
        traces=traces or [],
    )


def _item(
    *,
    expected_stance: Stance = Stance.SUPPORTED,
    expected_evidence_keys: list[str] | None = None,
    min_tools_called: list[str] | None = None,
) -> GoldenItem:
    return GoldenItem(
        id="t01",
        category="fundamentals",
        thesis="t",
        ticker="X",
        as_of_date=date(2026, 5, 13),
        expected_stance=expected_stance,
        expected_evidence_keys=expected_evidence_keys or [],
        min_tools_called=min_tools_called or [],
    )


def _trace(node: str, status: str = "ok") -> NodeTrace:
    now = datetime.now(UTC)
    return NodeTrace(node=node, started_at=now, finished_at=now, status=status)


def _evidence(eid: str, key: str) -> Evidence:
    return Evidence(
        id=eid,
        source=SourceType.FMP,
        key=key,
        value={},
        citation=Citation(source=SourceType.FMP, evidence_id=eid, retrieved_at=datetime.now(UTC)),
    )


def test_tool_call_accuracy_full() -> None:
    item = _item(min_tools_called=["fetch_stock", "fetch_news"])
    state = _state(traces=[_trace("fetch_stock"), _trace("fetch_news")])
    assert tool_call_accuracy(item, state) == 1.0


def test_tool_call_accuracy_partial_and_skipped() -> None:
    item = _item(min_tools_called=["fetch_stock", "fetch_news"])
    state = _state(traces=[_trace("fetch_stock"), _trace("fetch_news", status="skipped")])
    assert tool_call_accuracy(item, state) == 0.5


def test_tool_call_accuracy_no_requirement() -> None:
    assert tool_call_accuracy(_item(), _state()) == 1.0


def test_retrieval_precision_prefix_match() -> None:
    item = _item(expected_evidence_keys=["fmp.income_statement.AAPL"])
    state = _state(
        evidence=[
            _evidence("a", "fmp.income_statement.AAPL.2025-12-31"),
            _evidence("b", "fmp.income_statement.AAPL.2025-09-30"),
            _evidence("c", "news.AAPL.2025-12-01.0"),
        ]
    )
    # 2 of 3 keys match the expected prefix.
    assert retrieval_precision(item, state) == 2 / 3


def test_retrieval_precision_no_actual_no_expected() -> None:
    assert retrieval_precision(_item(), _state()) == 1.0


def test_retrieval_precision_no_actual_some_expected() -> None:
    item = _item(expected_evidence_keys=["fmp.profile.X"])
    assert retrieval_precision(item, _state()) == 0.0


def test_final_answer_accuracy_match() -> None:
    item = _item(expected_stance=Stance.REFUTED)
    state = _state(
        verdict=Verdict(stance=Stance.REFUTED, confidence=Confidence.MEDIUM, summary="x")
    )
    assert final_answer_accuracy(item, state) == 1.0


def test_final_answer_accuracy_no_verdict() -> None:
    assert final_answer_accuracy(_item(), _state()) == 0.0


def test_hallucination_rate_uncited_committed_claim() -> None:
    item = _item()
    cv_supported_no_cite = ClaimVerdict(
        claim_id="c1", stance=Stance.SUPPORTED, rationale="r"
    )
    cv_supported_cited = ClaimVerdict(
        claim_id="c2", stance=Stance.SUPPORTED, rationale="r", supporting_evidence_ids=["e1"]
    )
    cv_uncertain = ClaimVerdict(claim_id="c3", stance=Stance.UNCERTAIN, rationale="r")
    state = _state(
        verdict=Verdict(
            stance=Stance.SUPPORTED,
            confidence=Confidence.MEDIUM,
            summary="x",
            claim_verdicts=[cv_supported_no_cite, cv_supported_cited, cv_uncertain],
        )
    )
    # 2 committed claims; 1 uncited → 0.5
    assert hallucination_rate(item, state) == 0.5


def test_hallucination_rate_no_committed_claims() -> None:
    state = _state(
        verdict=Verdict(
            stance=Stance.UNCERTAIN,
            confidence=Confidence.LOW,
            summary="x",
            claim_verdicts=[ClaimVerdict(claim_id="c1", stance=Stance.UNCERTAIN, rationale="r")],
        )
    )
    assert hallucination_rate(_item(), state) == 0.0


def test_score_item_and_aggregate() -> None:
    item = _item(
        expected_stance=Stance.SUPPORTED,
        min_tools_called=["fetch_stock"],
        expected_evidence_keys=["fmp.profile.X"],
    )
    cost_trace = NodeTrace(
        node="fetch_stock",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        cost_usd=0.10,
    )
    state = _state(
        evidence=[_evidence("e1", "fmp.profile.X")],
        verdict=Verdict(stance=Stance.SUPPORTED, confidence=Confidence.HIGH, summary="x"),
        traces=[cost_trace],
    )
    s = score_item(item, state)
    assert s.tool_call_accuracy == 1.0
    assert s.retrieval_precision == 1.0
    assert s.final_answer_accuracy == 1.0
    assert s.hallucination_rate == 0.0
    assert s.cost_usd == 0.10

    agg = aggregate([s, s])
    assert agg.n == 2
    assert agg.cost_usd_total == 0.20
    assert agg.final_answer_accuracy == 1.0
