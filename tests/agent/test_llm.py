from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agent.llm import LLMClient, LLMUsage, cost_usd


def _fake_response(
    *,
    text: str = "",
    tool_use: dict | None = None,
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_creation: int = 0,
    cache_read: int = 0,
    stop_reason: str = "end_turn",
) -> SimpleNamespace:
    content: list[SimpleNamespace] = []
    if text:
        content.append(SimpleNamespace(type="text", text=text))
    if tool_use is not None:
        content.append(
            SimpleNamespace(
                type="tool_use",
                id=tool_use["id"],
                name=tool_use["name"],
                input=tool_use["input"],
            )
        )
    return SimpleNamespace(
        content=content,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=cache_creation,
            cache_read_input_tokens=cache_read,
        ),
        stop_reason=stop_reason,
    )


@pytest.mark.asyncio
async def test_acall_caches_system_and_last_tool() -> None:
    fake_anthropic = SimpleNamespace(
        messages=SimpleNamespace(create=AsyncMock(return_value=_fake_response(text="hi")))
    )
    client = LLMClient(fake_anthropic)

    await client.acall(
        model="claude-haiku-4-5-20251001",
        system="You are X",
        messages=[{"role": "user", "content": "hello"}],
        tools=[
            {"name": "tool_a", "description": "", "input_schema": {"type": "object"}},
            {"name": "tool_b", "description": "", "input_schema": {"type": "object"}},
        ],
    )

    sent = fake_anthropic.messages.create.await_args.kwargs
    assert sent["system"] == [
        {"type": "text", "text": "You are X", "cache_control": {"type": "ephemeral"}}
    ]
    assert sent["tools"][0].get("cache_control") is None
    assert sent["tools"][1]["cache_control"] == {"type": "ephemeral"}


@pytest.mark.asyncio
async def test_acall_parses_tool_use_and_cost() -> None:
    fake_anthropic = SimpleNamespace(
        messages=SimpleNamespace(
            create=AsyncMock(
                return_value=_fake_response(
                    tool_use={"id": "tu_1", "name": "extract", "input": {"x": 1}},
                    input_tokens=1_000_000,  # exactly 1M for easy cost math
                    output_tokens=0,
                    stop_reason="tool_use",
                )
            )
        )
    )
    client = LLMClient(fake_anthropic)

    response = await client.acall(
        model="claude-haiku-4-5-20251001",
        messages=[{"role": "user", "content": "go"}],
    )

    assert response.tool_uses[0].name == "extract"
    assert response.tool_uses[0].input == {"x": 1}
    assert response.stop_reason == "tool_use"
    # Haiku 4.5 input pricing = $1.00 per 1M tokens, no output → exactly $1.00.
    assert response.cost_usd == pytest.approx(1.00)


def test_cost_usd_unknown_model_returns_zero() -> None:
    assert cost_usd("unknown-model", LLMUsage(1, 1, 0, 0)) == 0.0
