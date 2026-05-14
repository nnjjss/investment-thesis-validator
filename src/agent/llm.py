"""Anthropic SDK wrapper with prompt caching, tool-use structured output, and cost tracking.

Conventions:
- Cheap nodes use ``claude-haiku-4-5-20251001`` (parse/plan/contradiction).
- Synthesizer uses ``claude-opus-4-7`` with adaptive thinking opt-in.
- System prompts ≥ 4096 tokens get cached automatically when ``cache=True``.
- Sampling parameters (``temperature``, ``top_p``, ``top_k``) are NOT supported on
  Opus 4.7 and would 400. We do not expose them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

logger = structlog.get_logger(__name__)

# USD per 1M tokens. Cache write = 1.25× input, cache read = 0.10× input.
PRICING_USD_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-opus-4-7": {
        "input": 5.00,
        "output": 25.00,
        "cache_write": 6.25,
        "cache_read": 0.50,
    },
    "claude-haiku-4-5": {
        "input": 1.00,
        "output": 5.00,
        "cache_write": 1.25,
        "cache_read": 0.10,
    },
    "claude-haiku-4-5-20251001": {
        "input": 1.00,
        "output": 5.00,
        "cache_write": 1.25,
        "cache_read": 0.10,
    },
}


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int


@dataclass(frozen=True)
class LLMToolUse:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class LLMResponse:
    model: str
    text: str
    tool_uses: list[LLMToolUse]
    usage: LLMUsage
    cost_usd: float
    stop_reason: str


def cost_usd(model: str, usage: LLMUsage) -> float:
    pricing = PRICING_USD_PER_MTOK.get(model)
    if pricing is None:
        logger.warning("unknown_model_pricing", model=model)
        return 0.0
    return (
        usage.input_tokens * pricing["input"]
        + usage.output_tokens * pricing["output"]
        + usage.cache_creation_tokens * pricing["cache_write"]
        + usage.cache_read_tokens * pricing["cache_read"]
    ) / 1_000_000


class LLMClient:
    """Sole entry point for Claude API calls in the agent."""

    def __init__(self, anthropic: AsyncAnthropic) -> None:
        self._anthropic = anthropic

    async def acall(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        max_tokens: int = 4096,
        cache: bool = True,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }

        if system is not None:
            kwargs["system"] = (
                [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
                if cache
                else system
            )

        if tools:
            if cache:
                annotated = [dict(t) for t in tools]
                annotated[-1]["cache_control"] = {"type": "ephemeral"}
                kwargs["tools"] = annotated
            else:
                kwargs["tools"] = tools

        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice

        response = await self._anthropic.messages.create(**kwargs)

        text_parts: list[str] = []
        tool_uses: list[LLMToolUse] = []
        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(block.text)
            elif block_type == "tool_use":
                raw_input = block.input
                tool_uses.append(
                    LLMToolUse(
                        id=block.id,
                        name=block.name,
                        input=dict(raw_input) if isinstance(raw_input, dict) else {},
                    )
                )

        usage = LLMUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_creation_tokens=response.usage.cache_creation_input_tokens or 0,
            cache_read_tokens=response.usage.cache_read_input_tokens or 0,
        )

        return LLMResponse(
            model=model,
            text="\n".join(text_parts),
            tool_uses=tool_uses,
            usage=usage,
            cost_usd=cost_usd(model, usage),
            stop_reason=response.stop_reason or "unknown",
        )
