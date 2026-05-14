"""CLI for the eval harness.

Usage:
    uv run python -m eval.cli run \\
        --dataset eval/datasets/golden_v1_seed.jsonl \\
        --sample 5

The CLI builds a real graph (real LLMClient + real ingestion clients) using
``ANTHROPIC_API_KEY``, ``FMP_API_KEY``, ``NEWS_API_KEY`` from the environment.
For mock-backed eval (CI / unit tests) call ``run_eval()`` directly.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
from pathlib import Path

from anthropic import AsyncAnthropic

from eval.report import write_html_report
from eval.runner import load_dataset, persist_run, run_eval
from src.agent.graph import GraphModels, build_graph
from src.agent.llm import LLMClient
from src.config import get_settings
from src.ingestion.fmp import FMPClient
from src.ingestion.news import NewsClient
from src.ingestion.sec import SECClient


async def _amain(args: argparse.Namespace) -> int:
    settings = get_settings()
    items = load_dataset(Path(args.dataset))
    if args.sample > 0 and args.sample < len(items):
        if args.seed is not None:
            random.seed(args.seed)
        items = random.sample(items, args.sample)

    user_agent = os.environ.get(
        "SEC_USER_AGENT", "investment-thesis-validator eval@example.com"
    )

    anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    llm = LLMClient(anthropic_client)
    fmp = FMPClient(api_key=settings.fmp_api_key)
    news = NewsClient(api_key=settings.news_api_key)
    sec = SECClient(user_agent=user_agent)

    try:
        graph = build_graph(
            llm=llm,
            fmp=fmp,
            news=news,
            sec=sec,
            models=GraphModels(
                cheap=settings.cheap_model,
                validator=settings.validator_model,
            ),
        )

        result = await run_eval(items, graph, concurrency=args.concurrency)
        run_dir = persist_run(
            result,
            out_root=Path(args.out),
            dataset_name=Path(args.dataset).name,
            label=args.label,
        )

        report_path = write_html_report(result, run_dir, dataset_name=Path(args.dataset).name)

        agg = result.aggregate
        print(f"\nrun_dir = {run_dir}", file=sys.stderr)
        print(f"report  = {report_path}", file=sys.stderr)
        print(
            f"\nn={agg.n} | "
            f"final_acc={agg.final_answer_accuracy:.3f} | "
            f"tool_acc={agg.tool_call_accuracy:.3f} | "
            f"retr_prec={agg.retrieval_precision:.3f} | "
            f"halluc={agg.hallucination_rate:.3f} | "
            f"cost_total=${agg.cost_usd_total:.4f} | "
            f"cost_mean=${agg.cost_usd_mean:.4f}"
        )
        return 0 if not result.failures else 1
    finally:
        await fmp.aclose()
        await news.aclose()
        await sec.aclose()


def main() -> int:
    parser = argparse.ArgumentParser(prog="eval.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Execute the agent over a dataset")
    run.add_argument("--dataset", default="eval/datasets/golden_v1_seed.jsonl")
    run.add_argument("--out", default="eval/runs")
    run.add_argument("--sample", type=int, default=0, help="0 = full dataset")
    run.add_argument("--seed", type=int, default=None)
    run.add_argument("--concurrency", type=int, default=4)
    run.add_argument("--label", default=None, help="suffix appended to run_dir name")

    args = parser.parse_args()
    if args.cmd == "run":
        return asyncio.run(_amain(args))
    return 2


if __name__ == "__main__":
    sys.exit(main())
