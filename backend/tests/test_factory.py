from __future__ import annotations

import pytest

from app import config
from app.ai.factory import create_ai_player
from app.ai.mock_player import MockPlayer
from app.ai.providers.anthropic_player import AnthropicPlayer
from app.ai.providers.openai_compatible_player import OpenAICompatiblePlayer


def test_uses_real_provider_when_key_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-fake")

    player = create_ai_player("claude", "Claude")

    assert isinstance(player, AnthropicPlayer)


def test_falls_back_to_mock_when_key_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", None)

    player = create_ai_player("claude", "Claude")

    assert isinstance(player, MockPlayer)


def test_openai_seat_uses_max_completion_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test: newer OpenAI models (e.g. gpt-5.1) reject the legacy
    `max_tokens` param outright with a 400 -- every real decide()/reaction call
    was failing until this was wired to `max_completion_tokens` specifically
    for the openai seat (see OpenAICompatiblePlayer.__init__)."""
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-fake")

    player = create_ai_player("openai", "OpenAI")

    assert isinstance(player, OpenAICompatiblePlayer)
    assert player._max_tokens_param == "max_completion_tokens"


def test_deepseek_seat_uses_legacy_max_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    """DeepSeek's OpenAI-compatible endpoint still expects the legacy
    `max_tokens` name (unlike OpenAI itself) -- must not be switched over
    alongside the openai seat."""
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "sk-fake")

    player = create_ai_player("deepseek", "DeepSeek")

    assert isinstance(player, OpenAICompatiblePlayer)
    assert player._max_tokens_param == "max_tokens"


def test_openai_and_deepseek_seats_disable_reasoning_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test: left unset, DeepSeek's reasoning burned an entire
    decide() call on hidden "thinking" tokens (32s, 3326 reasoning tokens)
    without ever producing a reply -- reasoning_effort="none" dropped that to
    ~1s. OpenAI's gpt-5.1 shows the same pattern. Both support "none"."""
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-fake")
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "sk-fake")

    assert create_ai_player("openai", "OpenAI")._reasoning_effort == "none"
    assert create_ai_player("deepseek", "DeepSeek")._reasoning_effort == "none"


def test_grok_seat_uses_low_reasoning_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    """grok-4.6 rejects reasoning_effort="none" outright with a 400 -- "low"
    is its minimum supported tier."""
    monkeypatch.setattr(config, "XAI_API_KEY", "sk-fake")

    assert create_ai_player("grok", "Grok")._reasoning_effort == "low"
