from __future__ import annotations

from datetime import UTC, datetime

from prometheus_client import CollectorRegistry

from src.agent.state import (
    Confidence,
    NodeTrace,
    Stance,
    ValidatorState,
    Verdict,
)
from src.api.metrics import ValidatorMetrics


def _ts() -> datetime:
    return datetime.now(UTC)


def test_emit_completed_increments_all_collectors() -> None:
    reg = CollectorRegistry()
    m = ValidatorMetrics(registry=reg)

    state = ValidatorState(
        thesis="t",
        ticker="X",
        as_of_date=datetime.now(UTC).date(),
        traces=[
            NodeTrace(
                node="parse_thesis",
                started_at=_ts(),
                finished_at=_ts(),
                status="ok",
                tokens_in=120,
                tokens_out=40,
                cache_read=80,
                cache_write=0,
                cost_usd=0.0012,
            ),
            NodeTrace(
                node="synthesize",
                started_at=_ts(),
                finished_at=_ts(),
                status="ok",
                tokens_in=2000,
                tokens_out=600,
                cache_read=4000,
                cache_write=200,
                cost_usd=0.05,
            ),
        ],
        verdict=Verdict(
            stance=Stance.SUPPORTED, confidence=Confidence.MEDIUM, summary="s"
        ),
    )
    m.emit_completed(state, model_for_costs="claude-opus-4-7")

    samples = {
        sample.name: sample.value
        for metric in reg.collect()
        for sample in metric.samples
    }
    assert samples["itv_validation_total"] == 1.0
    assert samples["itv_cost_usd_total"] > 0
    assert samples["itv_tool_call_total"] == 1.0  # at least one outcome bucket non-zero
    # Histogram emits multiple sample names; check one count exists.
    assert any(name.startswith("itv_node_latency_seconds_count") for name in samples)
    # Tokens by kind: each emitted kind shows up.
    by_kind: dict[str, float] = {}
    for metric in reg.collect():
        if metric.name == "itv_tokens":
            for sample in metric.samples:
                if sample.name == "itv_tokens_total":
                    by_kind[sample.labels["kind"]] = sample.value
    # We emitted input + output + cache_read for both nodes, cache_write for one.
    assert by_kind["input"] == 120 + 2000
    assert by_kind["output"] == 40 + 600
    assert by_kind["cache_read"] == 80 + 4000
    assert by_kind["cache_write"] == 200


def test_emit_failed_increments_failure_counter() -> None:
    reg = CollectorRegistry()
    m = ValidatorMetrics(registry=reg)
    m.emit_failed()

    samples = {
        sample.name: (sample.value, sample.labels)
        for metric in reg.collect()
        for sample in metric.samples
        if sample.name == "itv_validation_total"
    }
    assert samples["itv_validation_total"][1]["status"] == "failed"
    assert samples["itv_validation_total"][0] == 1.0
