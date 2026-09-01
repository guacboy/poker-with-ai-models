from __future__ import annotations

import json

import pytest

from app.ai.providers import gemini_player as gemini_player_module
from app.ai.providers.gemini_player import GeminiPlayer


class FakeResponse:
    def __init__(self, data: dict):
        self.text = json.dumps(data)


class RecordingModels:
    """Stand-in for genai.Client().aio.models -- records the config it was
    called with instead of making a real API call, and returns a canned
    response shaped like the real API's."""

    def __init__(self, data: dict):
        self._data = data
        self.calls: list[dict] = []

    async def generate_content(self, *, model: str, contents: str, config) -> FakeResponse:
        self.calls.append({"model": model, "contents": contents, "config": config})
        return FakeResponse(self._data)


class FakeAio:
    def __init__(self, models: RecordingModels):
        self.models = models


class FakeClient:
    def __init__(self, models: RecordingModels):
        self.aio = FakeAio(models)


def _decide_view() -> dict:
    return {
        "your_player_id": "gemini",
        "small_blind": 50,
        "big_blind": 100,
        "your_hole_cards": ["Ah", "As"],
        "board_cards": [],
        "pot_total": 150,
        "seats": [
            {
                "player_id": "gemini",
                "name": "Gemini",
                "stack": 1000,
                "bet": 0,
                "is_button": False,
                "is_small_blind": False,
                "is_big_blind": False,
                "folded": False,
                "is_to_act": True,
            }
        ],
        "legal_actions": {
            "can_fold": True,
            "can_check_or_call": True,
            "call_amount": 0,
            "can_bet_or_raise": True,
            "min_bet_to": 200,
            "max_bet_to": 1000,
        },
    }


@pytest.mark.asyncio
async def test_decide_disables_gemini_thinking() -> None:
    """Regression test: Gemini 3's thinking is on by default and burns real
    latency on hidden reasoning tokens before ever emitting the visible reply
    (confirmed live: ~4.25s/314 thoughts tokens unset vs ~1.4s/0 thoughts
    tokens at thinking_level="low") -- every call must explicitly ask for the
    low tier, the same way the OpenAI-compatible providers disable reasoning."""
    models = RecordingModels({"action": "fold", "amount": None, "message": None})
    player = GeminiPlayer("gemini", "Gemini", "fake-key", "gemini-3.6-flash")
    player._client = FakeClient(models)

    await player.decide(_decide_view())

    assert len(models.calls) == 1
    config = models.calls[0]["config"]
    assert config.thinking_config is gemini_player_module.THINKING_CONFIG
    assert config.thinking_config.thinking_level == gemini_player_module.types.ThinkingLevel.LOW


@pytest.mark.asyncio
async def test_react_to_win_disables_gemini_thinking() -> None:
    models = RecordingModels({"message": "gg"})
    player = GeminiPlayer("gemini", "Gemini", "fake-key", "gemini-3.6-flash")
    player._client = FakeClient(models)

    await player.react_to_win(_decide_view(), "One pair", 500)

    config = models.calls[0]["config"]
    assert config.thinking_config.thinking_level == gemini_player_module.types.ThinkingLevel.LOW


@pytest.mark.asyncio
async def test_react_to_loss_disables_gemini_thinking() -> None:
    models = RecordingModels({"message": "rigged"})
    player = GeminiPlayer("gemini", "Gemini", "fake-key", "gemini-3.6-flash")
    player._client = FakeClient(models)

    await player.react_to_loss(_decide_view(), "One pair", 500)

    config = models.calls[0]["config"]
    assert config.thinking_config.thinking_level == gemini_player_module.types.ThinkingLevel.LOW
