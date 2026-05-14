from __future__ import annotations

from pathlib import Path

from eval.schema import GoldenItem
from src.agent.state import Stance


def test_seed_dataset_loads_and_meets_diversity() -> None:
    seed_path = (
        Path(__file__).resolve().parent.parent
        / "eval"
        / "datasets"
        / "golden_v1_seed.jsonl"
    )
    items = [
        GoldenItem.model_validate_json(line)
        for line in seed_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(items) >= 20

    # All five categories represented.
    categories = {item.category for item in items}
    assert categories == {
        "fundamentals",
        "sentiment",
        "contradiction",
        "edge_case",
        "multi_claim",
    }

    # Anti-sycophancy: ≥30% should be REFUTED or UNCERTAIN.
    non_supported = [
        i for i in items if i.expected_stance in (Stance.REFUTED, Stance.UNCERTAIN)
    ]
    assert len(non_supported) / len(items) >= 0.30

    # No duplicate IDs.
    ids = [i.id for i in items]
    assert len(ids) == len(set(ids))

    # Every item has a non-empty thesis and ticker.
    for item in items:
        assert item.thesis.strip()
        assert item.ticker.strip()
