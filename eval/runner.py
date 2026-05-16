"""Async eval runner: invoke the agent over a golden dataset and persist results.

Outputs:
- ``eval/runs/<ts>/results.jsonl`` — one row per (item, item-level scores).
- ``eval/runs/<ts>/per_node.jsonl`` — one row per (item, node trace).
- ``eval/runs/<ts>/verdicts.jsonl`` — one row per (item, full verdict) for
  failure-mode diagnosis (what stance the agent picked, summary, claim
  breakdown). Kept separate from results.jsonl so the metrics file stays
  small + tabular.
- ``eval/runs/<ts>/summary.json`` — aggregate scores + run metadata.

Designed to be importable: ``run_eval(items, graph)`` returns the same data
that gets persisted, for unit tests and CI deltas.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.metrics import AggregateScores, ItemScores, aggregate, score_item
from eval.schema import GoldenItem
from src.agent.state import ValidatorState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvalResult:
    item_scores: list[ItemScores]
    aggregate: AggregateScores
    per_node_rows: list[dict[str, Any]]
    verdict_rows: list[dict[str, Any]]
    failures: list[dict[str, Any]]


def _verdict_row(item: GoldenItem, state: ValidatorState) -> dict[str, Any]:
    verdict = state.verdict
    return {
        "item_id": item.id,
        "category": item.category,
        "expected_stance": item.expected_stance.value,
        "predicted_stance": verdict.stance.value if verdict else None,
        "predicted_confidence": verdict.confidence.value if verdict else None,
        "summary": verdict.summary if verdict else "",
        "claim_verdicts": [
            {
                "claim_id": cv.claim_id,
                "stance": cv.stance.value,
                "rationale": cv.rationale,
                "supporting_evidence_ids": list(cv.supporting_evidence_ids),
                "refuting_evidence_ids": list(cv.refuting_evidence_ids),
            }
            for cv in (verdict.claim_verdicts if verdict else [])
        ],
        "evidence_used": list(verdict.evidence_used) if verdict else [],
        "evidence_keys_fetched": [ev.key for ev in state.evidence],
    }


async def _run_one(
    item: GoldenItem,
    graph: Any,
) -> tuple[
    ItemScores | None,
    list[dict[str, Any]],
    dict[str, Any] | None,
    dict[str, Any] | None,
]:
    initial = ValidatorState(
        thesis=item.thesis,
        ticker=item.ticker,
        as_of_date=item.as_of_date,
    )
    try:
        raw = await graph.ainvoke(initial)
        state = raw if isinstance(raw, ValidatorState) else ValidatorState.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 — eval surface, must not propagate
        logger.warning("eval_item_failed", extra={"item_id": item.id, "error": str(exc)})
        return None, [], None, {"item_id": item.id, "error": str(exc), "stage": "ainvoke"}

    scores = score_item(item, state)
    per_node = [
        {
            "item_id": item.id,
            "node": trace.node,
            "status": trace.status,
            "tokens_in": trace.tokens_in,
            "tokens_out": trace.tokens_out,
            "cache_read": trace.cache_read,
            "cache_write": trace.cache_write,
            "cost_usd": trace.cost_usd,
            "duration_s": (trace.finished_at - trace.started_at).total_seconds(),
            "error": trace.error,
        }
        for trace in state.traces
    ]
    verdict = _verdict_row(item, state)
    return scores, per_node, verdict, None


async def run_eval(
    items: Iterable[GoldenItem],
    graph: Any,
    *,
    concurrency: int = 4,
) -> EvalResult:
    items_list = list(items)
    semaphore = asyncio.Semaphore(concurrency)

    async def _bounded(
        item: GoldenItem,
    ) -> tuple[
        ItemScores | None,
        list[dict[str, Any]],
        dict[str, Any] | None,
        dict[str, Any] | None,
    ]:
        async with semaphore:
            return await _run_one(item, graph)

    results = await asyncio.gather(*(_bounded(it) for it in items_list))

    item_scores: list[ItemScores] = []
    per_node_rows: list[dict[str, Any]] = []
    verdict_rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for scores, rows, verdict, fail in results:
        if scores is not None:
            item_scores.append(scores)
        per_node_rows.extend(rows)
        if verdict is not None:
            verdict_rows.append(verdict)
        if fail is not None:
            failures.append(fail)

    return EvalResult(
        item_scores=item_scores,
        aggregate=aggregate(item_scores),
        per_node_rows=per_node_rows,
        verdict_rows=verdict_rows,
        failures=failures,
    )


def persist_run(
    result: EvalResult,
    *,
    out_root: Path,
    dataset_name: str,
    label: str | None = None,
) -> Path:
    """Write results.jsonl + per_node.jsonl + summary.json under out_root/<ts>/."""
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = f"_{label}" if label else ""
    run_dir = out_root / f"{ts}{suffix}"
    run_dir.mkdir(parents=True, exist_ok=True)

    with (run_dir / "results.jsonl").open("w", encoding="utf-8") as fh:
        for s in result.item_scores:
            fh.write(json.dumps(asdict(s)) + "\n")

    with (run_dir / "per_node.jsonl").open("w", encoding="utf-8") as fh:
        for row in result.per_node_rows:
            fh.write(json.dumps(row) + "\n")

    with (run_dir / "verdicts.jsonl").open("w", encoding="utf-8") as fh:
        for row in result.verdict_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "ts": ts,
        "dataset": dataset_name,
        "label": label,
        "aggregate": asdict(result.aggregate),
        "n_items_succeeded": len(result.item_scores),
        "n_items_failed": len(result.failures),
        "failures": result.failures,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return run_dir


def load_dataset(path: Path) -> list[GoldenItem]:
    items: list[GoldenItem] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        items.append(GoldenItem.model_validate_json(line))
    return items
