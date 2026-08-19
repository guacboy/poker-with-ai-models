"""Shared AI player interface, prompt template, and response schema.

Every provider (Anthropic, OpenAI-compatible, Gemini, mock) implements the same
`AIPlayer.decide(view) -> ActionResult` contract, where `view` is the dict
produced by `engine.state.view_for_actor` for that player. The action and any
trash talk come back from a single call (per the "bundled" decision), so
providers must request both in one structured-output call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

MAX_MESSAGE_WORDS = 15

RESPONSE_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["fold", "check_or_call", "bet_or_raise_to"],
        },
        "amount": {
            "type": ["integer", "null"],
            "description": "Chip total to bet/raise TO. Required and only used when action is bet_or_raise_to.",
        },
        "message": {
            "type": ["string", "null"],
            "description": f"Optional short trash-talk line (<= {MAX_MESSAGE_WORDS} words) reacting to this action. Omit or null for no talk.",
        },
    },
    "required": ["action", "amount", "message"],
    "additionalProperties": False,
}


@dataclass
class ActionResult:
    action: str  # "fold" | "check_or_call" | "bet_or_raise_to"
    amount: int | None = None
    message: str | None = None


class AIPlayer(Protocol):
    player_id: str
    display_name: str

    async def decide(self, view: dict) -> ActionResult: ...


def build_prompt(view: dict) -> str:
    """Renders the shared, persona-neutral prompt from an actor view dict."""
    seats_lines = []
    for seat in view["seats"]:
        tag = []
        if seat["is_button"]:
            tag.append("BTN")
        if seat["is_small_blind"]:
            tag.append("SB")
        if seat["is_big_blind"]:
            tag.append("BB")
        if seat["folded"]:
            tag.append("folded")
        if seat["is_to_act"]:
            tag.append("to act")
        tag_str = f" [{', '.join(tag)}]" if tag else ""
        me = " (you)" if seat["player_id"] == view["your_player_id"] else ""
        seats_lines.append(
            f"- {seat['name']}{me}: stack {seat['stack']}, bet {seat['bet']}{tag_str}"
        )

    legal = view["legal_actions"]
    legal_lines = []
    if legal["can_fold"]:
        legal_lines.append('"fold"')
    if legal["can_check_or_call"]:
        verb = "check" if legal["call_amount"] == 0 else f"call {legal['call_amount']}"
        legal_lines.append(f'"check_or_call" ({verb})')
    if legal["can_bet_or_raise"]:
        legal_lines.append(
            f'"bet_or_raise_to" (amount between {legal["min_bet_to"]} and {legal["max_bet_to"]})'
        )

    return f"""You are playing No-Limit Texas Hold'em against 5 opponents.

Blinds: {view['small_blind']}/{view['big_blind']}
Your hole cards: {', '.join(view['your_hole_cards'])}
Board: {', '.join(view['board_cards']) if view['board_cards'] else '(preflop)'}
Pot: {view['pot_total']}

Seats:
{chr(10).join(seats_lines)}

Legal actions: {', '.join(legal_lines)}

Decide your action. You may only include a short (<= {MAX_MESSAGE_WORDS} words) trash-talk \
message if you end up folding, raising/re-raising (including shoving all-in), or calling an \
opponent's bet or raise -- it will be read aloud to the table. Leave it null for a plain check \
or a call that isn't over a bet/raise (e.g. limping in for just the blind); messages on those \
actions are discarded anyway.
"""


def clamp_amount(view: dict, amount: int | None) -> int | None:
    """Defensively clamp an AI-proposed bet/raise amount into the legal range."""
    legal = view["legal_actions"]
    if amount is None or legal["min_bet_to"] is None or legal["max_bet_to"] is None:
        return amount
    return max(legal["min_bet_to"], min(legal["max_bet_to"], amount))


def facing_a_raise(view: dict) -> bool:
    """Whether calling right now means calling an actual raise, as opposed to
    just matching the unraised big blind (limping in) preflop. Postflop there's
    no blind baseline, so any nonzero call_amount is inherently over a real bet."""
    legal = view["legal_actions"]
    if legal["call_amount"] <= 0:
        return False
    if view["street_index"] != 0:
        return True
    own_bet = next(s["bet"] for s in view["seats"] if s["player_id"] == view["your_player_id"])
    current_bet_level = own_bet + legal["call_amount"]
    return current_bet_level > view["big_blind"]


def is_talk_eligible(action: str, view: dict) -> bool:
    """Whether an action is allowed to carry a spoken trash-talk message.

    Talk is limited to meaningful moments: raising/re-raising (which covers
    shoving all-in -- that's just a bet/raise for the player's whole stack),
    calling an actual raise, and folding -- but only a fold that's actually
    giving something up. A free check, a call that's really just
    posting/limping for the unraised blind, and a preflop/flop fold from a
    player who never put anything beyond a forced blind into this hand all
    stay silent; there's nothing to react to.
    """
    if action == "fold":
        if view["street_index"] in (0, 1):  # preflop, flop
            own_seat = next(s for s in view["seats"] if s["player_id"] == view["your_player_id"])
            return own_seat["voluntarily_invested"]
        return True
    if action == "bet_or_raise_to":
        return True
    if action == "check_or_call":
        return facing_a_raise(view)
    return False
