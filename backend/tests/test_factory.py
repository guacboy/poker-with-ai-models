from __future__ import annotations

import pytest

from app import config
from app.ai.factory import create_ai_player
from app.ai.mock_player import MockPlayer
from app.ai.providers.anthropic_player import AnthropicPlayer


def test_uses_real_provider_when_key_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-fake")

    player = create_ai_player("claude", "Claude")

    assert isinstance(player, AnthropicPlayer)


def test_falls_back_to_mock_when_key_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", None)

    player = create_ai_player("claude", "Claude")

    assert isinstance(player, MockPlayer)
