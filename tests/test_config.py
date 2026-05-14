from src.config import Settings


def test_frozen_settings_loads(frozen_settings: Settings) -> None:
    assert frozen_settings.anthropic_api_key == "sk-ant-test"
    assert frozen_settings.fmp_api_key == "fmp-test"
    assert frozen_settings.news_api_key == "news-test"
    assert frozen_settings.max_cost_usd == 0.50
    assert frozen_settings.validator_model == "claude-opus-4-7"
    assert frozen_settings.cheap_model == "claude-haiku-4-5-20251001"
