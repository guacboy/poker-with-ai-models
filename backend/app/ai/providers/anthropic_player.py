from __future__ import annotations

from anthropic import AsyncAnthropic

from ..base import (
    REACTION_JSON_SCHEMA,
    RESPONSE_JSON_SCHEMA,
    ActionResult,
    build_loss_reaction_prompt,
    build_prompt,
    build_win_reaction_prompt,
)

TOOL_NAME = "poker_action"
WIN_REACTION_TOOL_NAME = "win_reaction"
LOSS_REACTION_TOOL_NAME = "loss_reaction"


class AnthropicPlayer:
    def __init__(self, player_id: str, display_name: str, api_key: str, model: str):
        self.player_id = player_id
        self.display_name = display_name
        self._model = model
        self._client = AsyncAnthropic(api_key=api_key)

    async def decide(self, view: dict) -> ActionResult:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=300,
            messages=[{"role": "user", "content": build_prompt(view)}],
            tools=[
                {
                    "name": TOOL_NAME,
                    "description": "Submit your poker action for this turn.",
                    "input_schema": RESPONSE_JSON_SCHEMA,
                }
            ],
            tool_choice={"type": "tool", "name": TOOL_NAME},
        )
        for block in response.content:
            if block.type == "tool_use":
                data = block.input
                return ActionResult(
                    action=data["action"], amount=data.get("amount"), message=data.get("message")
                )
        raise RuntimeError("Anthropic response did not include a tool_use block")

    async def react_to_win(self, view: dict, hand_label: str | None, amount_won: int) -> str | None:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=150,
            messages=[{"role": "user", "content": build_win_reaction_prompt(view, hand_label, amount_won)}],
            tools=[
                {
                    "name": WIN_REACTION_TOOL_NAME,
                    "description": "React to winning this hand.",
                    "input_schema": REACTION_JSON_SCHEMA,
                }
            ],
            tool_choice={"type": "tool", "name": WIN_REACTION_TOOL_NAME},
        )
        for block in response.content:
            if block.type == "tool_use":
                return block.input.get("message")
        return None

    async def react_to_loss(self, view: dict, hand_label: str, amount_lost: int) -> str | None:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=150,
            messages=[{"role": "user", "content": build_loss_reaction_prompt(view, hand_label, amount_lost)}],
            tools=[
                {
                    "name": LOSS_REACTION_TOOL_NAME,
                    "description": "React to losing this hand.",
                    "input_schema": REACTION_JSON_SCHEMA,
                }
            ],
            tool_choice={"type": "tool", "name": LOSS_REACTION_TOOL_NAME},
        )
        for block in response.content:
            if block.type == "tool_use":
                return block.input.get("message")
        return None
