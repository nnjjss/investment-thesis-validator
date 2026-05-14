"""Offline DSPy compilation for contradiction + synthesize prompts.

USAGE
-----
1. Confirm baseline numbers exist (run ``eval.cli run`` against full dataset).
2. Set ANTHROPIC_API_KEY.
3. Run::

       uv run python -m eval.dspy_compile \\
           --dataset eval/datasets/golden_v1.jsonl \\
           --target {contradiction|synthesize} \\
           --train-split 0.7

4. Compare compiled metrics against baseline. **Kill criterion (M5
   acceptance):** if final_answer_accuracy on the dev split does not
   improve by **≥3pp** vs baseline, abandon DSPy for this node and
   document the result in ``docs/dspy_postmortem.md``.

Compiled artifact lives at
``src/agent/optimized/compiled/<target>_<git_sha>.json``. The runtime loader
(deferred — TODO see ``src/agent/optimized/__init__.py``) picks it up when
``USE_DSPY_PROMPTS=1``.

Cost estimate per compile: ~$5–15 in tokens at ``max_bootstrapped_demos=4``,
70-item train set, Opus 4.7. Set ``ANTHROPIC_API_KEY`` carefully.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from typing import Any

from eval.runner import load_dataset

TARGETS = {"contradiction", "synthesize"}


def _split(
    items: list[Any], train_frac: float, seed: int
) -> tuple[list[Any], list[Any]]:
    rng = random.Random(seed)
    shuffled = list(items)
    rng.shuffle(shuffled)
    cutoff = int(len(shuffled) * train_frac)
    return shuffled[:cutoff], shuffled[cutoff:]


def main() -> int:
    parser = argparse.ArgumentParser(prog="eval.dspy_compile")
    parser.add_argument("--dataset", default="eval/datasets/golden_v1.jsonl")
    parser.add_argument("--target", choices=sorted(TARGETS), required=True)
    parser.add_argument("--train-split", type=float, default=0.7)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-bootstrapped-demos", type=int, default=4)
    parser.add_argument(
        "--out-dir",
        default="src/agent/optimized/compiled",
        help="where the compiled JSON artifact is written",
    )
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"dataset not found: {dataset_path}", file=sys.stderr)
        return 2

    items = load_dataset(dataset_path)
    train, dev = _split(items, args.train_split, args.seed)
    print(
        f"target={args.target} | train={len(train)} dev={len(dev)} "
        f"max_demos={args.max_bootstrapped_demos}",
        file=sys.stderr,
    )

    print(
        "\nThis script is the scaffold for DSPy compilation against the\n"
        "investment-thesis-validator agent. The actual compile loop is\n"
        "intentionally deferred until baseline metrics from M4 are stable\n"
        "and the user has decided whether to proceed (per M5 kill criterion).\n",
        file=sys.stderr,
    )
    print("To enable, populate the TODO blocks below:", file=sys.stderr)
    print("  1. Configure dspy.settings.configure(lm=dspy.LM('anthropic/...'))", file=sys.stderr)
    print("  2. Wrap the runtime node into a dspy.Module subclass", file=sys.stderr)
    print(
        "  3. Map GoldenItem → dspy.Example with the signature's fields",
        file=sys.stderr,
    )
    print("  4. Run BootstrapFewShot(metric=final_answer_accuracy_dspy)", file=sys.stderr)
    print(f"  5. Persist the compiled module to {args.out_dir}", file=sys.stderr)
    print(
        "\nSee docs/dspy_postmortem.md for the +3pp kill criterion.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
