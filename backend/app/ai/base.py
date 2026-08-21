"""Shared AI player interface, prompt template, and response schema.

Every provider (Anthropic, OpenAI-compatible, Gemini, mock) implements the same
`AIPlayer.decide(view) -> ActionResult` contract, where `view` is the dict
produced by `engine.state.view_for_actor` for that player. The action and any
trash talk come back from a single call (per the "bundled" decision), so
providers must request both in one structured-output call.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol

MAX_MESSAGE_WORDS = 15

PREFLOP, FLOP, TURN, RIVER = 0, 1, 2, 3

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

    async def react_to_win(self, view: dict, hand_label: str | None, amount_won: int) -> str | None: ...

    async def react_to_loss(self, view: dict, hand_label: str, amount_lost: int) -> str | None: ...


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
actions are discarded anyway. When you do talk, go all the way in: be disrespectful, arrogant, \
and don't hold back on insults -- foul language is endorsed, this is a trash-talking poker table, \
not a courtesy call.
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


# Chance an otherwise-quiet action (a free check, a preflop/flop blind-limp
# call, or a fold that never put in anything beyond a forced blind) still
# comes with a talk line anyway. Rises street by street so the table gets
# chattier as the hand escalates -- preflop stays almost silent, river is a
# coinflip.
AMBIENT_TALK_CHANCE = {PREFLOP: 0.05, FLOP: 0.15, TURN: 0.30, RIVER: 0.50}
# Same, but bumped further on turn/river specifically when a genuinely risky,
# all-in moment is part of the picture (see `_is_risky_moment`) -- higher
# stakes make even an otherwise-quiet check worth reacting to.
AMBIENT_TALK_CHANCE_RISKY = {TURN: 0.55, RIVER: 0.75}

# Chance for an inherently "meaningful" action -- raising/shoving, a real
# fold (giving something up), or calling an actual bet/raise. High but not
# guaranteed, the same across every street, so the table doesn't chatter on
# literally every single one.
MEANINGFUL_TALK_CHANCE = 0.90
# Turn/river + a risky, all-in moment bumps a meaningful action all the way
# to certain -- reacting to (or making) a shove is always worth a line.
MEANINGFUL_TALK_CHANCE_RISKY = 1.0


def _is_risky_moment(action: str, amount: int | None, view: dict) -> bool:
    """A turn/river moment worth extra excitement: this action is itself an
    all-in shove, or some other still-live seat is already all-in and this
    bot is reacting to that."""
    legal = view["legal_actions"]
    max_bet_to = legal.get("max_bet_to")
    if action == "bet_or_raise_to" and amount is not None and max_bet_to is not None and amount >= max_bet_to:
        return True
    return any(
        seat["player_id"] != view["your_player_id"] and not seat["folded"] and seat["stack"] == 0
        for seat in view["seats"]
    )


def talk_chance(action: str, view: dict, amount: int | None = None) -> float:
    """The probability (0-1) that `action` ends up carrying a spoken line.

    Two tiers: a "meaningful" action (raising/shoving, a real fold, calling
    an actual bet) is highly likely to talk but not guaranteed
    (`MEANINGFUL_TALK_CHANCE`); anything otherwise silent gets a small,
    street-scaled chance instead (`AMBIENT_TALK_CHANCE`). Both tiers get
    bumped further on turn/river when a risky, all-in moment is in play.
    """
    street = view["street_index"]
    risky = street in (TURN, RIVER) and _is_risky_moment(action, amount, view)

    def meaningful() -> float:
        return MEANINGFUL_TALK_CHANCE_RISKY if risky else MEANINGFUL_TALK_CHANCE

    def ambient() -> float:
        return AMBIENT_TALK_CHANCE_RISKY[street] if risky else AMBIENT_TALK_CHANCE[street]

    if action == "fold":
        if street in (PREFLOP, FLOP):
            own_seat = next(s for s in view["seats"] if s["player_id"] == view["your_player_id"])
            return meaningful() if own_seat["voluntarily_invested"] else ambient()
        return meaningful()  # turn/river folds always give something real up
    if action == "bet_or_raise_to":
        return meaningful()
    if action == "check_or_call":
        return meaningful() if facing_a_raise(view) else ambient()
    return 0.0


def is_talk_eligible(action: str, view: dict, amount: int | None = None) -> bool:
    """Whether this action ends up carrying a spoken trash-talk message this
    time -- a probabilistic roll against `talk_chance`, not a fixed rule."""
    return random.random() < talk_chance(action, view, amount)


REACTION_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "message": {
            "type": ["string", "null"],
            "description": f"Short reaction to the hand's outcome (<= {MAX_MESSAGE_WORDS} words). Omit or null to stay quiet.",
        },
    },
    "required": ["message"],
    "additionalProperties": False,
}


def build_win_reaction_prompt(view: dict, hand_label: str | None, amount_won: int) -> str:
    """Renders the prompt for the guaranteed post-win reveal reaction -- a
    separate, lighter-weight call made only after a hand's winner(s) are
    already known, once betting is over. `decide()`'s prompt can't cover this:
    it's built and answered before anyone knows who's going to win.

    `hand_label` is None for a fold-out win that made it to the turn or
    river (see GameSession._broadcast_win_reactions) -- nobody showed cards,
    so there's no category to cite, just the fact that everyone folded.

    Takes `amount_won` explicitly (the winner's own net gain this hand)
    rather than reading `view['pot_total']` -- by the time this runs, the
    hand has already finished and pokerkit may have already cleared the pot
    internally, so `pot_total` can no longer be trusted to reflect what was
    actually won."""
    if hand_label is not None:
        situation = f"You just won a hand of No-Limit Texas Hold'em at showdown.\nYour winning hand: {hand_label}"
    else:
        situation = "You just won a hand of No-Limit Texas Hold'em -- everyone else folded, so your cards were never shown."
    return f"""{situation}

Your hole cards: {', '.join(view['your_hole_cards'])}
Board: {', '.join(view['board_cards']) if view['board_cards'] else '(preflop)'}
Amount won: {amount_won}

React to winning in a short (<= {MAX_MESSAGE_WORDS} words) line -- it will be read aloud to \
the table. Gloat hard: be disrespectful and arrogant toward whoever you just beat, don't hold \
back on insults, foul language is endorsed. Leave it null if you'd rather stay quiet.
"""


def build_loss_reaction_prompt(view: dict, hand_label: str, amount_lost: int) -> str:
    """Renders the prompt for the guaranteed sore-loser reaction -- fired only
    when this bot just lost a heads-up hand at showdown to the human on the
    turn or river (see GameSession._broadcast_loss_reaction). Like
    `build_win_reaction_prompt`, this is a separate post-hand call: nothing
    about losing is knowable until the showdown result is in.

    `view['opponent_hole_cards']` (set only by _broadcast_loss_reaction, not
    part of the regular decide()-time view) is the human's hand if it was
    actually revealed at this showdown -- lets the bot's sore-loser line call
    out the specific hand that beat it, not just the fact that it lost."""
    opponent_cards = view.get("opponent_hole_cards")
    opponent_line = f"\nThe human's hole cards: {', '.join(opponent_cards)}" if opponent_cards else ""
    return f"""You just lost a heads-up hand of No-Limit Texas Hold'em at showdown to the human \
player.
Your losing hand: {hand_label}

Your hole cards: {', '.join(view['your_hole_cards'])}
Board: {', '.join(view['board_cards']) if view['board_cards'] else '(preflop)'}{opponent_line}
Amount lost: {amount_lost}

React to losing in a short (<= {MAX_MESSAGE_WORDS} words) line -- it will be read aloud to the \
table. Be a sore loser about it: bitter, defensive, maybe blame luck or the cards, don't hold \
back on insults toward the human, foul language is endorsed. Leave it null if you'd rather stay quiet.
"""
