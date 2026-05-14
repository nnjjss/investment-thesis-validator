"""LangGraph wiring for the thesis validator.

v1: sequential graph (parse → plan → fetch_stock → fetch_news → fetch_filings →
contradiction → synthesize). Parallel evidence fan-out is M2c work — the design
is sequential-first because each fetch node already short-circuits via
``state.tool_plan``, so the latency cost of sequential execution is small until
all three sources are consistently needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.graph import END, StateGraph

from src.agent.llm import LLMClient
from src.agent.nodes.contradiction import contradiction
from src.agent.nodes.fetch_filings import fetch_filings
from src.agent.nodes.fetch_news import fetch_news
from src.agent.nodes.fetch_stock import fetch_stock
from src.agent.nodes.parse_thesis import parse_thesis
from src.agent.nodes.plan_evidence import plan_evidence
from src.agent.nodes.synthesize import synthesize
from src.agent.state import ValidatorState
from src.ingestion.fmp import FMPClient
from src.ingestion.news import NewsClient
from src.ingestion.sec import SECClient


@dataclass(frozen=True)
class GraphModels:
    cheap: str  # parse_thesis, plan_evidence, contradiction
    validator: str  # synthesize


def build_graph(
    *,
    llm: LLMClient,
    fmp: FMPClient,
    news: NewsClient,
    sec: SECClient,
    models: GraphModels,
) -> Any:
    """Compile a sequential StateGraph and return the compiled runnable."""

    async def _parse(state: ValidatorState) -> dict[str, Any]:
        return await parse_thesis(state, llm, model=models.cheap)

    async def _plan(state: ValidatorState) -> dict[str, Any]:
        return await plan_evidence(state, llm, model=models.cheap)

    async def _fetch_stock(state: ValidatorState) -> dict[str, Any]:
        return await fetch_stock(state, fmp)

    async def _fetch_news(state: ValidatorState) -> dict[str, Any]:
        return await fetch_news(state, news)

    async def _fetch_filings(state: ValidatorState) -> dict[str, Any]:
        return await fetch_filings(state, sec)

    async def _contradiction(state: ValidatorState) -> dict[str, Any]:
        return await contradiction(state, llm, model=models.cheap)

    async def _synthesize(state: ValidatorState) -> dict[str, Any]:
        return await synthesize(state, llm, model=models.validator)

    g: Any = StateGraph(ValidatorState)
    g.add_node("parse", _parse)
    g.add_node("plan", _plan)
    g.add_node("fetch_stock", _fetch_stock)
    g.add_node("fetch_news", _fetch_news)
    g.add_node("fetch_filings", _fetch_filings)
    g.add_node("contradiction", _contradiction)
    g.add_node("synthesize", _synthesize)

    g.set_entry_point("parse")
    g.add_edge("parse", "plan")
    g.add_edge("plan", "fetch_stock")
    g.add_edge("fetch_stock", "fetch_news")
    g.add_edge("fetch_news", "fetch_filings")
    g.add_edge("fetch_filings", "contradiction")
    g.add_edge("contradiction", "synthesize")
    g.add_edge("synthesize", END)

    return g.compile()
