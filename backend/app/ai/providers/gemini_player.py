from __future__ import annotations

import json

from google import genai
from google.genai import types

from ..base import (
    REACTION_JSON_SCHEMA,
    RESPONSE_JSON_SCHEMA,
    ActionResult,
    build_loss_reaction_prompt,
    build_prompt,
    build_win_reaction_prompt,
)


# Gemini 3's "thinking" is on by default and, like the OpenAI-compatible
# reasoning models (see openai_compatible_player.py), spends real time on
# hidden reasoning before ever emitting the visible reply -- confirmed live:
# unset took 4.25s and 314 hidden "thoughts" tokens for one decide() call,
# thinking_level="low" dropped that to ~1.5s with zero thoughts tokens.
# thinking_budget (the older, raw-token-count knob other Gemini versions use)
# is rejected outright (400) on this model -- thinking_level is what it wants.
THINKING_CONFIG = types.ThinkingConfig(thinking_level="low")


class GeminiPlayer:
    def __init__(self, player_id: str, display_name: str, api_key: str, model: str):
        self.player_id = player_id
        self.display_name = display_name
        self._model = model
        self._client = genai.Client(api_key=api_key)

    async def decide(self, view: dict) -> ActionResult:
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=build_prompt(view),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=RESPONSE_JSON_SCHEMA,
                thinking_config=THINKING_CONFIG,
            ),
        )
        data = json.loads(response.text)
        return ActionResult(action=data["action"], amount=data.get("amount"), message=data.get("message"))

    async def react_to_win(self, view: dict, hand_label: str | None, amount_won: int) -> str | None:
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=build_win_reaction_prompt(view, hand_label, amount_won),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=REACTION_JSON_SCHEMA,
                thinking_config=THINKING_CONFIG,
            ),
        )
        data = json.loads(response.text)
        return data.get("message")

    async def react_to_loss(self, view: dict, hand_label: str, amount_lost: int) -> str | None:
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=build_loss_reaction_prompt(view, hand_label, amount_lost),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=REACTION_JSON_SCHEMA,
                thinking_config=THINKING_CONFIG,
            ),
        )
        data = json.loads(response.text)
        return data.get("message")
