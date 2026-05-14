from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from eval.report import write_html_report
from eval.runner import persist_run, run_eval
from eval.schema import GoldenItem
from src.agent.graph import GraphModels, build_graph
from src.agent.llm import LLMResponse, LLMToolUse, LLMUsage
from src.agent.state import Stance
from src.ingestion.fmp import FMP_BASE_URL, FMPClient
from src.ingestion.news import NewsClient
from src.ingestion.sec import SECClient
from tests.agent.conftest import FakeLLMClient


def _routed_llm() -> FakeLLMClient:
    by_name: dict[str, LLMResponse] = {
        "extract_claims": _resp(
            "extract_claims",
            {
                "claims": [
                    {
                        "id": "c1",
                        "subject": "AAPL",
                        "claim_text": "AAPL has positive operating margin",
                        "claim_type": "fundamental",
                    }
                ]
            },
        ),
        "plan_evidence_tools": _resp(
            "plan_evidence_tools",
            {
                "need_stock_data": True,
                "need_news": False,
                "need_filings": False,
                "rationale": "fundamentals only",
            },
        ),
        "classify_evidence": _resp(
            "classify_evidence",
            {
                "supporting_evidence_ids": ["fmp.income_statement.AAPL.2025-12-31"],
                "refuting_evidence_ids": [],
                "rationale": "income statement supports",
            },
        ),
        "produce_verdict": _resp(
            "produce_verdict",
            {
                "stance": "SUPPORTED",
                "confidence": "HIGH",
                "summary": "Margins are positive.",
                "claim_verdicts": [
                    {
                        "claim_id": "c1",
                        "stance": "SUPPORTED",
                        "rationale": "income statement",
                        "supporting_evidence_ids": ["fmp.income_statement.AAPL.2025-12-31"],
                        "refuting_evidence_ids": [],
                    }
                ],
                "evidence_used": ["fmp.income_statement.AAPL.2025-12-31"],
            },
        ),
    }

    def factory(kwargs: dict[str, Any]) -> LLMResponse:
        name = (kwargs.get("tool_choice") or {}).get("name")
        return by_name[name]

    return FakeLLMClient(response_factory=factory)


def _resp(name: str, tool_input: dict[str, Any]) -> LLMResponse:
    return LLMResponse(
        model="fake",
        text="",
        tool_uses=[LLMToolUse(id=f"tu_{name}", name=name, input=tool_input)],
        usage=LLMUsage(input_tokens=10, output_tokens=5, cache_creation_tokens=0, cache_read_tokens=0),
        cost_usd=0.0001,
        stop_reason="tool_use",
    )


@pytest.mark.asyncio
@respx.mock
async def test_run_eval_persists_results_and_html(tmp_path: Path) -> None:
    respx.get(f"{FMP_BASE_URL}/profile").mock(
        return_value=httpx.Response(200, json=[{"symbol": "AAPL", "sector": "Tech"}])
    )
    respx.get(f"{FMP_BASE_URL}/quote").mock(
        return_value=httpx.Response(200, json=[{"symbol": "AAPL", "price": 200.0}])
    )
    respx.get(f"{FMP_BASE_URL}/income-statement").mock(
        return_value=httpx.Response(
            200, json=[{"date": "2025-12-31", "revenue": 100, "operatingIncome": 30}]
        )
    )
    respx.get(f"{FMP_BASE_URL}/ratios").mock(
        return_value=httpx.Response(200, json=[{"date": "2025-12-31", "operatingMargin": 0.30}])
    )

    fmp = FMPClient(api_key="test")
    news = NewsClient(api_key="test")
    sec = SECClient(user_agent="ITV Test test@example.com")

    graph = build_graph(
        llm=_routed_llm(),
        fmp=fmp,
        news=news,
        sec=sec,
        models=GraphModels(cheap="fake-cheap", validator="fake-validator"),
    )

    items = [
        GoldenItem(
            id="t01",
            category="fundamentals",
            thesis="AAPL has positive operating margin",
            ticker="AAPL",
            as_of_date=date(2026, 5, 13),
            expected_stance=Stance.SUPPORTED,
            expected_evidence_keys=[
                "fmp.income_statement.AAPL",
                "fmp.profile.AAPL",
                "fmp.quote.AAPL",
                "fmp.ratios.AAPL",
            ],
            min_tools_called=["fetch_stock"],
        )
    ]

    result = await run_eval(items, graph, concurrency=1)

    assert result.aggregate.n == 1
    assert result.aggregate.final_answer_accuracy == 1.0
    assert result.aggregate.tool_call_accuracy == 1.0
    assert result.aggregate.retrieval_precision == 1.0
    assert not result.failures

    run_dir = persist_run(result, out_root=tmp_path, dataset_name="seed_test")
    assert (run_dir / "results.jsonl").exists()
    assert (run_dir / "per_node.jsonl").exists()
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["n_items_succeeded"] == 1

    html_path = write_html_report(result, run_dir, dataset_name="seed_test")
    assert html_path.exists()
    body = html_path.read_text()
    assert "final_answer_accuracy" in body
    assert "t01" in body

    await fmp.aclose()
    await news.aclose()
    await sec.aclose()
