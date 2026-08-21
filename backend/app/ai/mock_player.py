"""Randomized fallback AI player -- no API key required.

Lets the whole app (engine, WebSocket server, frontend, TTS) be built and played
end-to-end before any real provider keys exist. Real providers implement the
exact same `decide(view) -> ActionResult` contract and are dropped in later.
"""

from __future__ import annotations

import random

from .base import ActionResult, clamp_amount

TRASH_TALK_LINES = [
    "Is that really the best you've got?",
    "I'll take that pot, thanks.",
    "Careful, you're on thin ice.",
    "This one's mine.",
    "You really want to do that?",
    None,  # stay quiet most of the time
    None,
    None,
]

WIN_REACTION_LINES = [
    "That's how it's done.",
    "Run it again, I'll take it again.",
    "Chip up!",
    "Never doubted it for a second.",
    "Thanks for the donation.",
    None,  # even a guaranteed reaction slot can choose to stay quiet
]

LOSS_REACTION_LINES = [
    "Unbelievable. Absolutely rigged.",
    "You got lucky, that's all.",
    "I had that pot won, this game is a joke.",
    "Whatever, run it back.",
    None,  # even a guaranteed reaction slot can choose to stay quiet
]


class MockPlayer:
    def __init__(self, player_id: str, display_name: str, seed: int | None = None):
        self.player_id = player_id
        self.display_name = display_name
        self._rng = random.Random(seed)

    async def decide(self, view: dict) -> ActionResult:
        legal = view["legal_actions"]
        options: list[str] = []
        if legal["can_check_or_call"]:
            options += ["check_or_call"] * 3  # weight towards calling/checking
        if legal["can_bet_or_raise"]:
            options += ["bet_or_raise_to"]
        if legal["can_fold"] and legal["call_amount"] > 0:
            options += ["fold"]
        if not options:
            options = ["fold"] if legal["can_fold"] else ["check_or_call"]

        action = self._rng.choice(options)
        amount = None
        if action == "bet_or_raise_to":
            lo, hi = legal["min_bet_to"], legal["max_bet_to"]
            # bias towards smaller, more realistic raises rather than shoving
            span = hi - lo
            amount = clamp_amount(view, lo + int(span * self._rng.random() * 0.35))

        message = self._rng.choice(TRASH_TALK_LINES)
        return ActionResult(action=action, amount=amount, message=message)

    async def react_to_win(self, view: dict, hand_label: str | None, amount_won: int) -> str | None:
        return self._rng.choice(WIN_REACTION_LINES)

    async def react_to_loss(self, view: dict, hand_label: str, amount_lost: int) -> str | None:
        return self._rng.choice(LOSS_REACTION_LINES)
