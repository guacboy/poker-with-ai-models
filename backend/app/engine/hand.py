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
# HOLE_CARDS_SHOWING_OR_MUCKING is deliberately excluded: pokerkit's own
# automatic version only shows a showdown participant's cards if they still
# have a chance to win the pot, so an outright loser (in a non-all-in pot who
# isn't first in showdown order) mucks WITHOUT ever showing -- leaving
# revealed_hole_cards blind to their hand entirely. Hand._force_full_showdown_reveal
# drives this manually instead, forcing every remaining showdown participant to
# show regardless of whether they could still win, so a real showdown is always
# fully visible.
ALL_AUTOMATIONS = (
    Automation.ANTE_POSTING,
    Automation.BET_COLLECTION,
    Automation.BLIND_OR_STRADDLE_POSTING,
    Automation.CARD_BURNING,
    Automation.HOLE_DEALING,
    Automation.BOARD_DEALING,
    Automation.HAND_KILLING,
    Automation.CHIPS_PUSHING,
    Automation.CHIPS_PULLING,
)


def _card_str(card: Card) -> str:
    return repr(card)  # pokerkit's __repr__ is the short "Js"/"Th" form; __str__ is a long description


_RANK_ORDER = "23456789TJQKA"

# categories where the whole 5-card hand IS the pattern (a straight/flush is
# already exactly 5 specific cards) -- no kickers to trim out
_NO_KICKER_LABELS = {"Straight", "Flush", "Full house", "Straight flush"}
# how many cards of a matching rank the category actually needs -- the rest
# of the 5-card hand is just kickers pulled in to fill out the comparison
_MATCH_SIZE_BY_LABEL = {"Four of a kind": 4, "Three of a kind": 3, "Two pair": 2, "One pair": 2}


def _defining_cards(cards: list[str], label: str) -> list[str]:
    """Narrows pokerkit's full 5-card best hand down to just the cards that
    actually make it that category -- e.g. only the 2 cards forming a pair,
    not the 3 unrelated kicker cards also included to complete the 5-card
    comparison. Without this, a board card that's merely the best available
    kicker (and had nothing to do with the pair itself) would get highlighted
    right alongside the card that actually paired up."""
    if label in _NO_KICKER_LABELS:
        return cards
    match_size = _MATCH_SIZE_BY_LABEL.get(label)
    if match_size is None:  # "High card" -- no pattern at all, just the top card
        return [max(cards, key=lambda c: _RANK_ORDER.index(c[0]))]
    counts: dict[str, int] = {}
    for card in cards:
        counts[card[0]] = counts.get(card[0], 0) + 1
    return [card for card in cards if counts[card[0]] == match_size]


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
        # pokerkit clears a player's hole cards from state the moment they're
        # mucked -- on folding, and again for anyone left unshown once the hand
        # ends -- so `hole_cards_of` goes empty for them from that point on.
        # A viewer should still see their OWN hand after folding or losing an
        # unshown showdown, so snapshot what was actually dealt up front.
        self._dealt_hole_cards = {
            pid: [_card_str(c) for c in state.hole_cards[i]] for i, pid in enumerate(seat_player_ids)
        }
        # pokerkit also flips a player's live status (the same flag folding
        # uses) once their hand is killed/mucked at the end of an all-in
        # showdown -- and it does this the instant the last action closes
        # betting, before any of the remaining board is even dealt. Tracking
        # real folds ourselves keeps `is_folded` meaning "actually folded"
        # instead of "no longer in contention", so a losing (but never
        # folded) hand doesn't dim out and spoil the result mid-runout.
        self._explicitly_folded_ids: set[str] = set()

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

    def _index_of(self, player_id: str) -> int:
        return self.seat_player_ids.index(player_id)

    def hole_cards_of(self, player_id: str) -> list[str]:
        idx = self._index_of(player_id)
        return [_card_str(card) for card in self.state.hole_cards[idx]]

    def dealt_hole_cards_of(self, player_id: str) -> list[str]:
        """The two cards originally dealt to `player_id` this hand, unaffected
        by folding or end-of-hand mucking (unlike `hole_cards_of`, which goes
        empty for a player the moment their cards are mucked). Use this for
        showing a viewer their own hand -- they should still see it even after
        folding or losing an unshown hand at showdown."""
        return self._dealt_hole_cards[player_id]

    def stack_of(self, player_id: str) -> int:
        return self.state.stacks[self._index_of(player_id)]

    def bet_of(self, player_id: str) -> int:
        return self.state.bets[self._index_of(player_id)]

    def is_folded(self, player_id: str) -> bool:
        return player_id in self._explicitly_folded_ids

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
        folding_player_id = self.current_actor_id
        self.state.fold()
        self._explicitly_folded_ids.add(folding_player_id)
        self._force_full_showdown_reveal()

    def apply_check_or_call(self) -> None:
        self.state.check_or_call()
        self._force_full_showdown_reveal()

    def apply_bet_or_raise_to(self, amount: int) -> None:
        self.state.complete_bet_or_raise_to(amount)
        self._force_full_showdown_reveal()

    def _force_full_showdown_reveal(self) -> None:
        """A no-op unless this action just closed betting on a real showdown
        (see ALL_AUTOMATIONS above for why HOLE_CARDS_SHOWING_OR_MUCKING isn't
        automated) -- otherwise can_show_or_muck_hole_cards() is False and the
        loop never runs. Forces every remaining showdown participant to show,
        win or lose, so revealed_hole_cards/winning_hand_label never go blind
        for a real loss the way pokerkit's own default automation would."""
        while self.state.can_show_or_muck_hole_cards():
            self.state.show_or_muck_hole_cards(True)

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

    def _evaluate_hand(self, player_id: str):
        """pokerkit's own get_hand() goes blind (returns None) not just for a
        real fold, but also for a showdown LOSER once HAND_KILLING clears
        their hole cards from live state -- it does this even after
        _force_full_showdown_reveal made them show, since "in contention" and
        "shown" are tracked separately. Falls back to evaluating their
        revealed cards directly (independent of pokerkit's live contention
        bookkeeping) so a shown loss still resolves to a real hand instead of
        None."""
        idx = self._index_of(player_id)
        hand = self.state.get_hand(idx, 0, 0)
        if hand is not None:
            return hand
        revealed = self.revealed_hole_cards().get(player_id)
        if not revealed or not self.board_cards:
            return None
        try:
            return self.state.hand_types[0].from_game("".join(revealed), "".join(self.board_cards))
        except (KeyError, ValueError):
            return None

    def winning_hand_label(self, player_id: str) -> str | None:
        """The pokerkit hand-category label (e.g. "Straight flush", "Two
        pair") for `player_id`'s best 5-card hand this hand, using their hole
        cards plus the current board. None if it can't be evaluated (not
        enough board cards yet, or they never showed at showdown -- e.g. a
        real fold)."""
        hand = self._evaluate_hand(player_id)
        return hand.entry.label.value if hand is not None else None

    def winning_hand_cards(self, player_id: str) -> list[str] | None:
        """The cards (a mix of hole cards and/or board cards) that actually
        make `player_id`'s best hand the category it is this hand -- e.g.
        `["As", "2s", "3s", "4s", "5s"]` for a wheel straight flush (all 5
        cards are the pattern), but only `["As", "Ah"]` for one pair of aces
        even though the full 5-card comparison hand also pulled in 3 kicker
        cards (see _defining_cards). None under the same conditions as
        winning_hand_label."""
        hand = self._evaluate_hand(player_id)
        if hand is None:
            return None
        return _defining_cards([_card_str(c) for c in hand.cards], hand.entry.label.value)

    def final_stacks(self) -> dict[str, int]:
        return dict(zip(self.seat_player_ids, self.state.stacks))

    def net_results(self) -> dict[str, int]:
        finals = self.final_stacks()
        return {pid: finals[pid] - self.starting_stacks[pid] for pid in self.seat_player_ids}
