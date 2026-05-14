from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=(),
    )

    anthropic_api_key: str = Field(..., alias="ANTHROPIC_API_KEY")
    fmp_api_key: str = Field(..., alias="FMP_API_KEY")
    news_api_key: str = Field(..., alias="NEWS_API_KEY")

    max_cost_usd: float = Field(0.50, alias="MAX_COST_USD")
    validator_model: str = Field("claude-opus-4-7", alias="MODEL_VALIDATOR")
    cheap_model: str = Field("claude-haiku-4-5-20251001", alias="MODEL_CHEAP")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
