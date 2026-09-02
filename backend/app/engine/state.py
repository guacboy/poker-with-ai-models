"""Serializes tournament/hand state into JSON-safe dicts.

Two views are needed and must not leak information between them:
- `view_for_actor`: what one AI (or the human) sees when it's their turn to
  decide -- includes THEIR OWN hole cards only.
- `view_public`: what gets broadcast over the WebSocket -- opponents' hole
  cards are hidden unless they were revealed at showdown.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .hand import Hand
    from .tournament import Tournament


def _seat_meta(tournament: "Tournament", hand: "Hand") -> list[dict]:
    button_id = hand.seat_player_ids[-1]
    sb_id = hand.seat_player_ids[0]
    bb_id = hand.seat_player_ids[1] if len(hand.seat_player_ids) > 1 else None
    small_blind, big_blind = tournament.blinds
    seats = []
    for pid in hand.seat_player_ids:
        player = tournament.player(pid)
        mandatory_blind = big_blind if pid == bb_id else small_blind if pid == sb_id else 0
        contributed_this_hand = hand.starting_stacks[pid] - hand.stack_of(pid)
        seats.append(
            {
                "player_id": pid,
                "name": player.name,
                "kind": player.kind,
                "stack": hand.stack_of(pid),
                "bet": hand.bet_of(pid),
                "folded": hand.is_folded(pid),
                "buy_ins_used": player.buy_ins_used,
                "buy_ins_remaining": player.buy_ins_remaining,
                "is_button": pid == button_id,
                "is_small_blind": pid == sb_id,
                "is_big_blind": pid == bb_id,
                "is_to_act": pid == hand.current_actor_id,
                # has this player put in anything beyond a forced blind post,
                # at any point so far this hand -- used to tell a meaningful
                # fold (giving up on a hand they'd actually entered) apart
                # from a cheap one (mucking without ever having acted)
                "voluntarily_invested": contributed_this_hand > mandatory_blind,
            }
        )
    return seats


def view_for_actor(tournament: "Tournament", hand: "Hand", actor_id: str) -> dict:
    legal = hand.legal_actions()
    return {
        "your_player_id": actor_id,
        "your_hole_cards": hand.hole_cards_of(actor_id),
        "board_cards": hand.board_cards,
        "pot_total": hand.pot_total,
        "street_index": hand.street_index,
        "small_blind": tournament.blinds[0],
        "big_blind": tournament.blinds[1],
        "seats": _seat_meta(tournament, hand),
        "legal_actions": {
            "can_fold": legal.can_fold,
            "can_check_or_call": legal.can_check_or_call,
            "can_bet_or_raise": legal.can_bet_or_raise,
            "call_amount": legal.call_amount,
            "min_bet_to": legal.min_bet_to,
            "max_bet_to": legal.max_bet_to,
        },
    }


def view_public(
    tournament: "Tournament",
    hand: "Hand | None",
    viewer_id: str | None = None,
    *,
    board_cards_override: list[str] | None = None,
    reveal_all: bool = False,
) -> dict:
    base = {
        "hand_count": tournament.hand_count,
        "blind_level": tournament.blind_level,
        "small_blind": tournament.blinds[0],
        "big_blind": tournament.blinds[1],
        "hands_until_next_orbit": tournament.hands_until_next_orbit,
        "is_over": tournament.is_over,
        "winner_player_id": tournament.winner.id if tournament.winner else None,
        "players": [
            {
                "player_id": p.id,
                "name": p.name,
                "kind": p.kind,
                "stack": p.stack,
                "status": p.status.value,
                "buy_ins_used": p.buy_ins_used,
                "buy_ins_remaining": p.buy_ins_remaining,
            }
            for p in tournament.players
        ],
    }
    if hand is None:
        base["hand"] = None
        return base

    revealed = hand.revealed_hole_cards()
    seats = []
    for seat in _seat_meta(tournament, hand):
        pid = seat["player_id"]
        if reveal_all:
            # debug-only "always show hands" -- dealt_hole_cards_of (not
            # hole_cards_of) survives folding/mucking, same reasoning as the
            # viewer's-own-cards case below
            hole_cards = hand.dealt_hole_cards_of(pid)
        elif pid == viewer_id:
            # not hand.hole_cards_of(pid) -- pokerkit clears a player's hole
            # cards from its own state once they're mucked (on folding, or at
            # the end of the hand for anyone left unshown), but the viewer
            # should still see their own cards regardless
            hole_cards = hand.dealt_hole_cards_of(pid)
        elif pid in revealed:
            hole_cards = revealed[pid]
        else:
            hole_cards = None  # hidden
        seats.append({**seat, "hole_cards": hole_cards})

    base["hand"] = {
        # lets the caller show fewer cards than pokerkit has actually already
        # dealt internally -- used to stage a multi-street runout (all-in with
        # no more actions left) as a suspenseful street-by-street reveal
        # instead of dumping the whole board on the client at once
        "board_cards": board_cards_override if board_cards_override is not None else hand.board_cards,
        "pot_total": hand.pot_total,
        "street_index": hand.street_index,
        "is_over": hand.is_over,
        "current_actor_id": hand.current_actor_id,
        "seats": seats,
    }
    return base
