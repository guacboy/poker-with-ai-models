"""Multi-hand tournament state: buy-ins, blind levels, elimination, button rotation.

pokerkit (via `hand.py`) only knows about a single hand at a time. Everything a
tournament needs beyond that -- who's still in, how many buy-ins they have left,
which blind level we're at, whose button is it -- lives here, driven entirely by
the constants in `rules.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from . import hand as hand_module
from .. import rules


class PlayerStatus(Enum):
    ACTIVE = "active"
    ELIMINATED = "eliminated"


class ActionError(Exception):
    pass


@dataclass
class Player:
    id: str
    name: str
    kind: str  # "human" | "ai"
    stack: int
    buy_ins_used: int = 1
    status: PlayerStatus = PlayerStatus.ACTIVE

    @property
    def buy_ins_remaining(self) -> int:
        return rules.MAX_BUY_INS - self.buy_ins_used


@dataclass
class Tournament:
    players: list[Player]  # fixed physical seat order, persists all tournament
    hand_count: int = 0
    button_index: int = 0
    blind_level: int = 0
    current_hand: hand_module.Hand | None = None
    last_bust_events: list[dict] = field(default_factory=list)

    @classmethod
    def new(cls, player_specs: list[tuple[str, str, str]]) -> "Tournament":
        """player_specs: list of (id, name, kind) in seat order, kind is "human" or "ai"."""
        if len(player_specs) != rules.NUM_SEATS:
            raise ValueError(f"expected {rules.NUM_SEATS} players, got {len(player_specs)}")
        players = [
            Player(id=pid, name=name, kind=kind, stack=rules.STARTING_STACK)
            for pid, name, kind in player_specs
        ]
        return cls(players=players)

    # -- table state -----------------------------------------------------

    def active_players(self) -> list[Player]:
        return [p for p in self.players if p.status is PlayerStatus.ACTIVE]

    def player(self, player_id: str) -> Player:
        return next(p for p in self.players if p.id == player_id)

    @property
    def is_over(self) -> bool:
        return len(self.active_players()) <= 1

    @property
    def winner(self) -> Player | None:
        active = self.active_players()
        return active[0] if self.is_over and active else None

    @property
    def blinds(self) -> tuple[int, int]:
        return rules.blinds_for_level(self.blind_level)

    @property
    def hands_until_next_level(self) -> int:
        return rules.HANDS_PER_BLIND_LEVEL - (self.hand_count % rules.HANDS_PER_BLIND_LEVEL)

    # -- hand lifecycle -----------------------------------------------------

    def start_hand(self) -> hand_module.Hand:
        if self.is_over:
            raise RuntimeError("tournament is over")
        active = self.active_players()
        if len(active) < 2:
            raise RuntimeError("need at least 2 active players to start a hand")

        ordered = self._seat_order_from_button(active)
        seat_player_ids = [p.id for p in ordered]
        stacks_by_id = {p.id: p.stack for p in ordered}
        small_blind, big_blind = self.blinds
        ante = rules.ante_for_level(self.blind_level)

        self.current_hand = hand_module.Hand.start(
            seat_player_ids, stacks_by_id, small_blind, big_blind, ante
        )
        self.last_bust_events = []
        return self.current_hand

    def _seat_order_from_button(self, active: list[Player]) -> list[Player]:
        """Active players ordered [SB, BB, ..., BTN] for pokerkit. Resolves
        `self.button_index` to the next active seat if the prior button holder
        has since been eliminated, and persists that resolution."""
        button_player = self.players[self.button_index]
        if button_player.status is not PlayerStatus.ACTIVE:
            button_player = self._next_active_from(self.button_index)
        self.button_index = self.players.index(button_player)

        btn_pos = active.index(button_player)
        return active[btn_pos + 1 :] + active[: btn_pos + 1]

    def _next_active_from(self, start_index: int) -> Player:
        n = len(self.players)
        for offset in range(1, n + 1):
            candidate = self.players[(start_index + offset) % n]
            if candidate.status is PlayerStatus.ACTIVE:
                return candidate
        raise RuntimeError("no active players left")

    def validate_action(self, player_id: str, action: str, amount: int | None = None) -> hand_module.Hand:
        """Check whether `action` is legal for `player_id` right now, without
        applying it. Raises ActionError if not; otherwise returns the current
        hand, so callers who only want to validate (e.g. the API layer, before
        committing to resolving a pending human turn) can reuse this directly
        instead of re-deriving the same rules."""
        hand = self.current_hand
        if hand is None or hand.is_over:
            raise ActionError("no hand in progress")
        if hand.current_actor_id != player_id:
            raise ActionError(f"it is not {player_id}'s turn")

        legal = hand.legal_actions()
        if action == "fold":
            if not legal.can_fold:
                raise ActionError("fold is not legal here")
        elif action == "check_or_call":
            if not legal.can_check_or_call:
                raise ActionError("check/call is not legal here")
        elif action == "bet_or_raise_to":
            if not legal.can_bet_or_raise:
                raise ActionError("bet/raise is not legal here")
            if amount is None:
                raise ActionError("bet/raise requires an amount")
            lo, hi = legal.min_bet_to, legal.max_bet_to
            if lo is not None and hi is not None and not (lo <= amount <= hi):
                raise ActionError(f"amount {amount} outside legal range [{lo}, {hi}]")
        else:
            raise ActionError(f"unknown action {action!r}")
        return hand

    def apply_action(self, player_id: str, action: str, amount: int | None = None) -> None:
        """Validate and apply one action to the in-progress hand."""
        hand = self.validate_action(player_id, action, amount)
        if action == "fold":
            hand.apply_fold()
        elif action == "check_or_call":
            hand.apply_check_or_call()
        elif action == "bet_or_raise_to":
            hand.apply_bet_or_raise_to(amount)

    def finish_hand(self) -> dict[str, int]:
        """Apply the completed hand's results, handle busts/rebuys/elimination,
        advance the button and blind level. Returns net chip change per player id."""
        hand = self.current_hand
        if hand is None or not hand.is_over:
            raise RuntimeError("no completed hand to finish")

        finals = hand.final_stacks()
        for pid, stack in finals.items():
            self.player(pid).stack = stack

        self._end_of_hand_bookkeeping(hand)
        net_results = hand.net_results()
        self.current_hand = None
        return net_results

    def forfeit_current_hand(self) -> dict[str, int]:
        """Debug-only escape hatch: immediately end the in-progress hand
        regardless of its state (mid betting round, mid all-in runout,
        whatever), instead of letting it play out through pokerkit. Whatever
        chips are already committed this hand stay committed -- forfeited,
        not returned to their owner or awarded to anyone -- only each
        player's live remaining stack survives. No-op if no hand is in
        progress. Returns net chip change per player id, same shape as
        `finish_hand`."""
        hand = self.current_hand
        if hand is None:
            return {}

        for pid in hand.seat_player_ids:
            self.player(pid).stack = hand.stack_of(pid)

        self._end_of_hand_bookkeeping(hand)
        net_results = hand.net_results()
        self.current_hand = None
        return net_results

    def _end_of_hand_bookkeeping(self, hand: hand_module.Hand) -> None:
        """Shared by a normal `finish_hand` and a debug `forfeit_current_hand`:
        bust/rebuy/elimination checks against whatever each player's stack
        ended up at, plus advancing the button and blind level."""
        for pid in hand.seat_player_ids:
            if self.player(pid).stack == 0:
                self._handle_bust(pid)

        self.button_index = (self.button_index + 1) % len(self.players)

        self.hand_count += 1
        if self.hand_count % rules.HANDS_PER_BLIND_LEVEL == 0:
            self.blind_level += 1

    def _handle_bust(self, player_id: str) -> None:
        player = self.player(player_id)
        if player.buy_ins_remaining > 0:
            player.buy_ins_used += 1
            player.stack = self._rebuy_stack_size()
            self.last_bust_events.append({"player_id": player_id, "eliminated": False})
        else:
            player.status = PlayerStatus.ELIMINATED
            self.last_bust_events.append({"player_id": player_id, "eliminated": True})

    def _rebuy_stack_size(self) -> int:
        if not rules.REBUY_SCALES_WITH_BLINDS:
            return rules.STARTING_STACK
        _, big_blind = self.blinds
        return 100 * big_blind
