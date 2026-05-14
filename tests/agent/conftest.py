from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.agent.llm import LLMClient, LLMResponse, LLMToolUse, LLMUsage


class FakeLLMClient(LLMClient):
    """Test double for LLMClient — returns canned LLMResponses without touching Anthropic."""

    def __init__(self, *, response_factory: Callable[[dict[str, Any]], LLMResponse]) -> None:
        # Intentionally skip super().__init__ — we don't want a real AsyncAnthropic.
        self._factory = response_factory
        self.calls: list[dict[str, Any]] = []

    async def acall(self, **kwargs: Any) -> LLMResponse:
        self.calls.append(kwargs)
        return self._factory(kwargs)


def make_tool_response(
    *,
    name: str,
    tool_input: dict[str, Any],
    model: str = "claude-haiku-4-5-20251001",
    input_tokens: int = 100,
    output_tokens: int = 50,
) -> LLMResponse:
    return LLMResponse(
        model=model,
        text="",
        tool_uses=[LLMToolUse(id="tu_test", name=name, input=tool_input)],
        usage=LLMUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_tokens=0,
            cache_read_tokens=0,
        ),
        cost_usd=0.001,
        stop_reason="tool_use",
    )
