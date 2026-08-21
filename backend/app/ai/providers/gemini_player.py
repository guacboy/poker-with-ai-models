from __future__ import annotations

import json

from google import genai
from google.genai import types

from ..base import (
    RESPONSE_JSON_SCHEMA,
    WIN_REACTION_JSON_SCHEMA,
    ActionResult,
    build_prompt,
    build_win_reaction_prompt,
)


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
                response_json_schema=WIN_REACTION_JSON_SCHEMA,
            ),
        )
        data = json.loads(response.text)
        return data.get("message")
