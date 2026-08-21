"""Shared player implementation for any OpenAI-compatible chat-completions API.

OpenAI, DeepSeek, and xAI (Grok) all speak this same API shape -- only the
base_url, API key, and model name differ. See ai/factory.py for how each is
configured.
"""

from __future__ import annotations

import json

from openai import AsyncOpenAI

from ..base import (
    RESPONSE_JSON_SCHEMA,
    WIN_REACTION_JSON_SCHEMA,
    ActionResult,
    build_prompt,
    build_win_reaction_prompt,
)

SCHEMA_INSTRUCTIONS = (
    "Respond with ONLY a single JSON object (no markdown, no other text) matching "
    f"this schema:\n{json.dumps(RESPONSE_JSON_SCHEMA)}"
)
WIN_REACTION_SCHEMA_INSTRUCTIONS = (
    "Respond with ONLY a single JSON object (no markdown, no other text) matching "
    f"this schema:\n{json.dumps(WIN_REACTION_JSON_SCHEMA)}"
)


class OpenAICompatiblePlayer:
    def __init__(
        self,
        player_id: str,
        display_name: str,
        api_key: str,
        model: str,
        base_url: str | None = None,
    ):
        self.player_id = player_id
        self.display_name = display_name
        self._model = model
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def decide(self, view: dict) -> ActionResult:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SCHEMA_INSTRUCTIONS},
                {"role": "user", "content": build_prompt(view)},
            ],
            response_format={"type": "json_object"},
            max_tokens=300,
        )
        data = json.loads(response.choices[0].message.content)
        return ActionResult(action=data["action"], amount=data.get("amount"), message=data.get("message"))

    async def react_to_win(self, view: dict, hand_label: str | None, amount_won: int) -> str | None:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": WIN_REACTION_SCHEMA_INSTRUCTIONS},
                {"role": "user", "content": build_win_reaction_prompt(view, hand_label, amount_won)},
            ],
            response_format={"type": "json_object"},
            max_tokens=150,
        )
        data = json.loads(response.choices[0].message.content)
        return data.get("message")
