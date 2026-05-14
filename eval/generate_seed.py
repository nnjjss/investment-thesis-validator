"""Expand the 20-pair seed dataset to 100 candidates using Claude Opus 4.7.

Usage:
    uv run python -m eval.generate_seed \
        --seed eval/datasets/golden_v1_seed.jsonl \
        --out eval/datasets/golden_v1_candidates.jsonl \
        --target-per-category 20

Reads the seed file, calls Opus 4.7 ONCE per category to generate
``target-per-category - len(seed_in_category)`` new items in the same
schema, validates each candidate via ``GoldenItem.model_validate``, and
writes the merged output to ``--out``.

This script is **NOT** the answer — every generated candidate must pass the
human review checklist in ``eval/REVIEW_CHECKLIST.md`` before promotion to
``golden_v1.jsonl``. The script exists to scaffold candidates, not to
replace human judgment.

Cost (rough): one Opus 4.7 call per category × 5 categories × ~2K input,
~3K output → ~$0.50 per full run. Set ``ANTHROPIC_API_KEY`` first.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic
from pydantic import ValidationError

from eval.schema import GoldenItem
from src.agent.llm import LLMClient

CATEGORIES = ["fundamentals", "sentiment", "contradiction", "edge_case", "multi_claim"]
GENERATOR_MODEL = "claude-opus-4-7"

EXPAND_TOOL: dict[str, Any] = {
    "name": "emit_candidates",
    "description": "Emit new GoldenItem candidates in the same shape as the seeds.",
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "category": {"type": "string"},
                        "thesis": {"type": "string"},
                        "ticker": {"type": "string"},
                        "as_of_date": {"type": "string", "description": "ISO date"},
                        "expected_stance": {
                            "type": "string",
                            "enum": ["SUPPORTED", "REFUTED", "UNCERTAIN"],
                        },
                        "expected_evidence_keys": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "min_tools_called": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "notes": {"type": "string"},
                    },
                    "required": [
                        "id",
                        "category",
                        "thesis",
                        "ticker",
                        "as_of_date",
                        "expected_stance",
                    ],
                },
            }
        },
        "required": ["items"],
    },
}

GENERATOR_SYSTEM_PATH = Path(__file__).resolve().parent / "generator_system.md"


def _read_seeds(path: Path) -> list[GoldenItem]:
    seeds: list[GoldenItem] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        seeds.append(GoldenItem.model_validate_json(line))
    return seeds


def _format_seeds_for_prompt(seeds: Iterable[GoldenItem]) -> str:
    return "\n".join(item.model_dump_json() for item in seeds)


async def _expand_category(
    llm: LLMClient,
    *,
    category: str,
    seeds: list[GoldenItem],
    n_additional: int,
) -> list[dict[str, Any]]:
    if n_additional <= 0:
        return []

    user = (
        f"Category: {category}\n"
        f"Seeds (jsonl):\n{_format_seeds_for_prompt(seeds)}\n\n"
        f"Generate exactly {n_additional} new items in category '{category}'."
    )

    response = await llm.acall(
        model=GENERATOR_MODEL,
        system=GENERATOR_SYSTEM_PATH.read_text(encoding="utf-8"),
        messages=[{"role": "user", "content": user}],
        tools=[EXPAND_TOOL],
        tool_choice={"type": "tool", "name": "emit_candidates"},
        max_tokens=8192,
    )
    if not response.tool_uses:
        raise RuntimeError(f"generator did not call emit_candidates for {category}")
    items = response.tool_uses[0].input.get("items", [])
    print(
        f"  category={category} requested={n_additional} got={len(items)} "
        f"cost=${response.cost_usd:.4f}",
        file=sys.stderr,
    )
    return list(items)


def _validate(rows: list[dict[str, Any]]) -> list[GoldenItem]:
    valid: list[GoldenItem] = []
    for row in rows:
        try:
            valid.append(GoldenItem.model_validate(row))
        except ValidationError as exc:
            print(f"  rejected: {row.get('id', '?')} — {exc.errors()[0]['msg']}", file=sys.stderr)
    return valid


async def _amain(args: argparse.Namespace) -> int:
    seeds = _read_seeds(Path(args.seed))
    by_category: dict[str, list[GoldenItem]] = defaultdict(list)
    for s in seeds:
        by_category[s.category].append(s)

    anthropic = AsyncAnthropic()
    llm = LLMClient(anthropic)

    all_items: list[GoldenItem] = list(seeds)

    for category in CATEGORIES:
        existing = by_category.get(category, [])
        n_additional = max(0, args.target_per_category - len(existing))
        if not existing:
            print(f"  warning: no seeds for category '{category}'; skipping", file=sys.stderr)
            continue
        candidates_raw = await _expand_category(
            llm,
            category=category,
            seeds=existing,
            n_additional=n_additional,
        )
        all_items.extend(_validate(candidates_raw))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for item in all_items:
            fh.write(item.model_dump_json() + "\n")

    by_cat_count: dict[str, int] = defaultdict(int)
    for item in all_items:
        by_cat_count[item.category] += 1
    print(f"\nwrote {len(all_items)} items to {out_path}", file=sys.stderr)
    for category in CATEGORIES:
        print(f"  {category}: {by_cat_count[category]}", file=sys.stderr)
    print("\nNEXT: walk every NEW item through eval/REVIEW_CHECKLIST.md before", file=sys.stderr)
    print("promoting to eval/datasets/golden_v1.jsonl.", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", default="eval/datasets/golden_v1_seed.jsonl")
    parser.add_argument("--out", default="eval/datasets/golden_v1_candidates.jsonl")
    parser.add_argument("--target-per-category", type=int, default=20)
    args = parser.parse_args()
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    sys.exit(main())
