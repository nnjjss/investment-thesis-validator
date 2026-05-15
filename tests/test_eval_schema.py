from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from eval.schema import GoldenItem
from src.agent.state import Stance

DATASETS_DIR = Path(__file__).resolve().parent.parent / "eval" / "datasets"


def _load(path: Path) -> list[GoldenItem]:
    return [
        GoldenItem.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _validate_dataset(items: list[GoldenItem], *, min_size: int) -> None:
    assert len(items) >= min_size, f"expected at least {min_size} items, got {len(items)}"

    categories = {item.category for item in items}
    assert categories == {
        "fundamentals",
        "sentiment",
        "contradiction",
        "edge_case",
        "multi_claim",
    }

    non_supported = sum(
        1 for i in items if i.expected_stance in (Stance.REFUTED, Stance.UNCERTAIN)
    )
    assert non_supported / len(items) >= 0.30, (
        f"anti-sycophancy bar — REFUTED+UNCERTAIN must be ≥30%, "
        f"got {100 * non_supported / len(items):.0f}%"
    )

    ids = [i.id for i in items]
    assert len(ids) == len(set(ids)), "duplicate ids present"

    for item in items:
        assert item.thesis.strip(), f"empty thesis on {item.id}"
        assert item.ticker.strip(), f"empty ticker on {item.id}"


def test_seed_dataset_loads_and_meets_diversity() -> None:
    items = _load(DATASETS_DIR / "golden_v1_seed.jsonl")
    _validate_dataset(items, min_size=20)


@pytest.mark.skipif(
    not (DATASETS_DIR / "golden_v1_candidates.jsonl").exists(),
    reason="candidates not generated — run `uv run python -m eval.generate_seed`",
)
def test_candidates_dataset_balanced() -> None:
    items = _load(DATASETS_DIR / "golden_v1_candidates.jsonl")
    _validate_dataset(items, min_size=100)

    by_category = Counter(item.category for item in items)
    # Generator targets 20 per category; tolerate small variance.
    for category, count in by_category.items():
        assert count >= 18, f"category {category} underfilled: {count}"


@pytest.mark.skipif(
    not (DATASETS_DIR / "golden_v1.jsonl").exists(),
    reason="golden_v1.jsonl not promoted yet",
)
def test_golden_v1_promoted_dataset() -> None:
    items = _load(DATASETS_DIR / "golden_v1.jsonl")
    _validate_dataset(items, min_size=100)

    # Every evidence key must use a prefix the runtime can actually emit.
    valid_prefixes = (
        "fmp.profile.",
        "fmp.quote.",
        "fmp.income_statement.",
        "fmp.ratios.",
        "sec.10-K.",
        "sec.10-Q.",
        "sec.8-K.",
        "sec.10K.",
        "sec.10Q.",
        "news.",
    )
    for item in items:
        for key in item.expected_evidence_keys:
            assert any(key.startswith(p) for p in valid_prefixes), (
                f"item {item.id}: invalid evidence key prefix: {key}"
            )
