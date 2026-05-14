"""FastAPI app entry point.

Lifespan-scoped: builds the LangGraph and ingestion clients once on startup,
shares them across requests via ``app.state``. The job store is also
app-scoped — single-process, in-memory, no Redis. Document the upgrade path
in docs/RUNBOOK.md.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from anthropic import AsyncAnthropic
from fastapi import FastAPI
from prometheus_client import make_asgi_app

from src.agent.graph import GraphModels, build_graph
from src.agent.llm import LLMClient
from src.api.jobs import JobStore
from src.api.metrics import ValidatorMetrics
from src.api.routes import health, validate
from src.config import get_settings
from src.ingestion.fmp import FMPClient
from src.ingestion.news import NewsClient
from src.ingestion.sec import SECClient


def _build_state(settings: Any) -> dict[str, Any]:
    user_agent = os.environ.get(
        "SEC_USER_AGENT", "investment-thesis-validator api@example.com"
    )
    anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    llm = LLMClient(anthropic_client)
    fmp = FMPClient(api_key=settings.fmp_api_key)
    news = NewsClient(api_key=settings.news_api_key)
    sec = SECClient(user_agent=user_agent)
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
    return {
        "anthropic": anthropic_client,
        "fmp": fmp,
        "news": news,
        "sec": sec,
        "graph": graph,
        "job_store": JobStore(),
        "metrics": ValidatorMetrics(),
        "metrics_model_label": settings.validator_model,
        "cost_cap_usd": settings.max_cost_usd,
    }


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    state = _build_state(settings)
    for key, value in state.items():
        setattr(app.state, key, value)
    try:
        yield
    finally:
        await app.state.fmp.aclose()
        await app.state.news.aclose()
        await app.state.sec.aclose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Investment Thesis Validator",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(validate.router)
    app.mount("/metrics", make_asgi_app())
    return app


app = create_app()
