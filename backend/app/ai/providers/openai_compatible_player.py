"""Shared player implementation for any OpenAI-compatible chat-completions API.

OpenAI, DeepSeek, and xAI (Grok) all speak this same API shape -- only the
base_url, API key, and model name differ. See ai/factory.py for how each is
configured.
"""

from __future__ import annotations

import json

from openai import AsyncOpenAI

from ..base import (
    REACTION_JSON_SCHEMA,
    RESPONSE_JSON_SCHEMA,
    ActionResult,
    build_loss_reaction_prompt,
    build_prompt,
    build_win_reaction_prompt,
)

# Generous on purpose: several OpenAI-compatible reasoning models (e.g.
# DeepSeek's and xAI's reasoning variants) spend hidden "thinking" tokens out
# of this same budget before ever emitting the visible JSON reply -- at a
# tight budget (previously 300/150) they burn the whole thing reasoning and
# the actual content comes back empty, which silently looked like the model
# just never talking. Both decide() and the reaction calls use the same
# generous budget since even a short reaction prompt can trigger the same
# reasoning burn.
MAX_RESPONSE_TOKENS = 4000

SCHEMA_INSTRUCTIONS = (
    "Respond with ONLY a single JSON object (no markdown, no other text) matching "
    f"this schema:\n{json.dumps(RESPONSE_JSON_SCHEMA)}"
)
REACTION_SCHEMA_INSTRUCTIONS = (
    "Respond with ONLY a single JSON object (no markdown, no other text) matching "
    f"this schema:\n{json.dumps(REACTION_JSON_SCHEMA)}"
)


class OpenAICompatiblePlayer:
    def __init__(
        self,
        player_id: str,
        display_name: str,
        api_key: str,
        model: str,
        base_url: str | None = None,
        max_tokens_param: str = "max_tokens",
    ):
        self.player_id = player_id
        self.display_name = display_name
        self._model = model
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        # Newer OpenAI models (e.g. gpt-5.1) reject the legacy `max_tokens`
        # param outright and require `max_completion_tokens` instead; other
        # OpenAI-compatible providers (DeepSeek, xAI) still expect the legacy
        # name. Configurable per instance since this one class serves all of
        # them -- see ai/factory.py for which seat passes which name.
        self._max_tokens_param = max_tokens_param

    async def decide(self, view: dict) -> ActionResult:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SCHEMA_INSTRUCTIONS},
                {"role": "user", "content": build_prompt(view)},
            ],
            response_format={"type": "json_object"},
            **{self._max_tokens_param: MAX_RESPONSE_TOKENS},
        )
        data = json.loads(response.choices[0].message.content)
        return ActionResult(action=data["action"], amount=data.get("amount"), message=data.get("message"))

    async def react_to_win(self, view: dict, hand_label: str | None, amount_won: int) -> str | None:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": REACTION_SCHEMA_INSTRUCTIONS},
                {"role": "user", "content": build_win_reaction_prompt(view, hand_label, amount_won)},
            ],
            response_format={"type": "json_object"},
            **{self._max_tokens_param: MAX_RESPONSE_TOKENS},
        )
        data = json.loads(response.choices[0].message.content)
        return data.get("message")

    async def react_to_loss(self, view: dict, hand_label: str, amount_lost: int) -> str | None:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": REACTION_SCHEMA_INSTRUCTIONS},
                {"role": "user", "content": build_loss_reaction_prompt(view, hand_label, amount_lost)},
            ],
            response_format={"type": "json_object"},
            **{self._max_tokens_param: MAX_RESPONSE_TOKENS},
        )
        data = json.loads(response.choices[0].message.content)
        return data.get("message")
