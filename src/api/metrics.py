"""Prometheus collectors for the validate endpoint.

Five labeled metrics — emitted after job completion by walking ``state.traces``
and ``state.verdict``. Live cost computation already lives in ``llm.py``; the
tokens + cost counters here just rebroadcast what each node trace records.
"""

from __future__ import annotations

from prometheus_client import REGISTRY, CollectorRegistry, Counter, Histogram

from src.agent.state import ValidatorState

_NODE_LATENCY_BUCKETS = (
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
    120.0,
)


class ValidatorMetrics:
    """Collector bundle. Pass a custom registry in tests for isolation."""

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        reg = registry or REGISTRY
        self.node_latency = Histogram(
            "itv_node_latency_seconds",
            "Per-node latency in seconds.",
            ("node", "status"),
            buckets=_NODE_LATENCY_BUCKETS,
            registry=reg,
        )
        self.validation_total = Counter(
            "itv_validation_total",
            "Validations completed by stance and overall status.",
            ("stance", "status"),
            registry=reg,
        )
        self.tokens_total = Counter(
            "itv_tokens_total",
            "Token counts by model and kind.",
            ("model", "kind"),
            registry=reg,
        )
        self.cost_usd_total = Counter(
            "itv_cost_usd_total",
            "Cumulative USD cost by model.",
            ("model",),
            registry=reg,
        )
        self.tool_call_total = Counter(
            "itv_tool_call_total",
            "Tool / node invocations by outcome.",
            ("tool", "outcome"),
            registry=reg,
        )

    def emit_completed(self, state: ValidatorState, *, model_for_costs: str) -> None:
        """Walk a completed ValidatorState and emit all metrics for it."""
        for trace in state.traces:
            duration = (trace.finished_at - trace.started_at).total_seconds()
            self.node_latency.labels(node=trace.node, status=trace.status).observe(duration)
            self.tool_call_total.labels(tool=trace.node, outcome=trace.status).inc()

            if trace.tokens_in:
                self.tokens_total.labels(model=model_for_costs, kind="input").inc(trace.tokens_in)
            if trace.tokens_out:
                self.tokens_total.labels(model=model_for_costs, kind="output").inc(trace.tokens_out)
            if trace.cache_read:
                self.tokens_total.labels(model=model_for_costs, kind="cache_read").inc(
                    trace.cache_read
                )
            if trace.cache_write:
                self.tokens_total.labels(model=model_for_costs, kind="cache_write").inc(
                    trace.cache_write
                )
            if trace.cost_usd:
                self.cost_usd_total.labels(model=model_for_costs).inc(trace.cost_usd)

        if state.verdict is not None:
            self.validation_total.labels(
                stance=state.verdict.stance.value, status="completed"
            ).inc()

    def emit_failed(self, state: ValidatorState | None = None) -> None:
        if state is not None:
            for trace in state.traces:
                duration = (trace.finished_at - trace.started_at).total_seconds()
                self.node_latency.labels(node=trace.node, status=trace.status).observe(duration)
        self.validation_total.labels(stance="UNKNOWN", status="failed").inc()
