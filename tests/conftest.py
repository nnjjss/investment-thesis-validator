from collections.abc import Iterator

import pytest

from src.config import Settings, get_settings


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def frozen_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("FMP_API_KEY", "fmp-test")
    monkeypatch.setenv("NEWS_API_KEY", "news-test")
    monkeypatch.setenv("MAX_COST_USD", "0.50")
    get_settings.cache_clear()
    try:
        yield get_settings()
    finally:
        get_settings.cache_clear()
