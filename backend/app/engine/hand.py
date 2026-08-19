"""Wraps a single pokerkit hand of No-Limit Texas Hold'em.

This is the only module that talks to pokerkit directly. Everything else (the
tournament loop, the AI prompt builder, the WebSocket serializer) goes through
the `Hand` interface below instead of touching `pokerkit.State`.
"""

from __future__ import annotations

from dataclasses import dataclass

from pokerkit import Automation, Card, NoLimitTexasHoldem, State

# Every pokerkit-managed step (dealing, blind posting, showdown, payouts) is
# automated. The only things we drive manually are the three player actions:
# fold / check-or-call / bet-or-raise-to.
ALL_AUTOMATIONS = (
    Automation.ANTE_POSTING,
    Automation.BET_COLLECTION,
    Automation.BLIND_OR_STRADDLE_POSTING,
    Automation.CARD_BURNING,
    Automation.HOLE_DEALING,
    Automation.BOARD_DEALING,
    Automation.HOLE_CARDS_SHOWING_OR_MUCKING,
    Automation.HAND_KILLING,
    Automation.CHIPS_PUSHING,
    Automation.CHIPS_PULLING,
)


def _card_str(card: Card) -> str:
    return repr(card)  # pokerkit's __repr__ is the short "Js"/"Th" form; __str__ is a long description


@dataclass
class LegalActions:
    can_fold: bool
    can_check_or_call: bool
    can_bet_or_raise: bool
    call_amount: int
    min_bet_to: int | None
    max_bet_to: int | None


class Hand:
    """One hand for a fixed seat order.

    `seat_player_ids[i]` is the player id occupying pokerkit index `i` for this
    hand: index 0 is the small blind, index 1 is the big blind, ..., and the
    last index is the button.
    """

    def __init__(self, state: State, seat_player_ids: list[str], starting_stacks: dict[str, int]):
        self.state = state
        self.seat_player_ids = seat_player_ids
        self.starting_stacks = starting_stacks

    @classmethod
    def start(
        cls,
        seat_player_ids: list[str],
        stacks_by_id: dict[str, int],
        small_blind: int,
        big_blind: int,
        ante: int = 0,
    ) -> "Hand":
        raw_starting_stacks = [stacks_by_id[pid] for pid in seat_player_ids]
        state = NoLimitTexasHoldem.create_state(
            ALL_AUTOMATIONS,
            True,  # ante_trimming_status
            ante,
            (small_blind, big_blind),
            big_blind,  # min_bet == min raise increment
            raw_starting_stacks,
            len(seat_player_ids),
        )
        return cls(state, seat_player_ids, dict(zip(seat_player_ids, raw_starting_stacks)))

    @property
    def is_over(self) -> bool:
        return not self.state.status

    @property
    def street_index(self) -> int | None:
        return self.state.street_index

    @property
    def board_cards(self) -> list[str]:
        return [_card_str(card) for group in self.state.board_cards for card in group]

    @property
    def pot_total(self) -> int:
        return self.state.total_pot_amount

    @property
    def current_actor_id(self) -> str | None:
        idx = self.state.actor_index
        return None if idx is None else self.seat_player_ids[idx]

    def hole_cards_of(self, player_id: str) -> list[str]:
        idx = self.seat_player_ids.index(player_id)
        return [_card_str(card) for card in self.state.hole_cards[idx]]

    def stack_of(self, player_id: str) -> int:
        idx = self.seat_player_ids.index(player_id)
        return self.state.stacks[idx]

    def bet_of(self, player_id: str) -> int:
        idx = self.seat_player_ids.index(player_id)
        return self.state.bets[idx]

    def is_folded(self, player_id: str) -> bool:
        idx = self.seat_player_ids.index(player_id)
        return not self.state.statuses[idx]

    def legal_actions(self) -> LegalActions:
        s = self.state
        can_bet = s.can_complete_bet_or_raise_to()
        return LegalActions(
            can_fold=s.can_fold(),
            can_check_or_call=s.can_check_or_call(),
            can_bet_or_raise=can_bet,
            call_amount=s.checking_or_calling_amount or 0,
            min_bet_to=s.min_completion_betting_or_raising_to_amount if can_bet else None,
            max_bet_to=s.max_completion_betting_or_raising_to_amount if can_bet else None,
        )

    def apply_fold(self) -> None:
        self.state.fold()

    def apply_check_or_call(self) -> None:
        self.state.check_or_call()

    def apply_bet_or_raise_to(self, amount: int) -> None:
        self.state.complete_bet_or_raise_to(amount)

    def revealed_hole_cards(self) -> dict[str, list[str]]:
        """Hole cards shown at showdown this hand, keyed by player id. Folded/mucked
        players (and anyone still hidden while the hand is in progress) are absent."""
        revealed: dict[str, list[str]] = {}
        for op in self.state.operations:
            if type(op).__name__ != "HoleCardsShowingOrMucking":
                continue
            cards = getattr(op, "hole_cards", ())
            if not cards:
                continue
            player_id = self.seat_player_ids[op.player_index]
            revealed[player_id] = [_card_str(c) for c in cards]
        return revealed

    def final_stacks(self) -> dict[str, int]:
        return dict(zip(self.seat_player_ids, self.state.stacks))

    def net_results(self) -> dict[str, int]:
        finals = self.final_stacks()
        return {pid: finals[pid] - self.starting_stacks[pid] for pid in self.seat_player_ids}
