"""One GameSession per tournament: owns the game loop task, connected
WebSocket clients, and the human-action handoff between the REST endpoint and
the loop coroutine waiting on it.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field

from fastapi import WebSocket

from .. import config
from ..ai.base import ActionResult, clamp_amount, is_talk_eligible
from ..ai.factory import create_ai_player
from ..ai.mock_player import MockPlayer
from ..engine import state as state_mod
from ..engine.tournament import ActionError, Tournament
from ..tts.kokoro_tts import synthesize


class HumanTurnError(Exception):
    pass


class DebugOnlyError(Exception):
    """Raised when a debug-only control is used on a non-debug session."""


# cumulative board size at the end of each street: flop / turn / river
STREET_BOARD_SIZES = (3, 4, 5)

# every AI seat is forced onto this single action (still clamped to whatever
# is actually legal) instead of its own decide() -- see _forced_action_result
FORCED_ACTION_MODES = ("all_in", "call", "check", "fold")


@dataclass
class GameSession:
    tournament_id: str
    tournament: Tournament
    ai_players: dict[str, object]
    human_player_id: str
    # debug sessions never touch ai/factory.py -- ai_players is built entirely
    # from MockPlayer in GameSession.new, so a debug game can never make a
    # real provider API call no matter what's configured
    is_debug: bool = False
    always_show_hands: bool = False
    forced_ai_action: str | None = None
    websockets: set[WebSocket] = field(default_factory=set)
    pending_human_action: asyncio.Future | None = field(default=None, init=False)
    task: asyncio.Task | None = field(default=None, init=False)

    @classmethod
    def new(cls, human_name: str, *, debug: bool = False) -> "GameSession":
        specs = [(config.HUMAN_PLAYER_ID, human_name, "human")] + [
            (pid, name, "ai") for pid, name in config.AI_SEATS
        ]
        tournament = Tournament.new(specs)
        ai_players: dict[str, object] = (
            {pid: MockPlayer(pid, name) for pid, name in config.AI_SEATS}
            if debug
            else {pid: create_ai_player(pid, name) for pid, name in config.AI_SEATS}
        )
        return cls(
            tournament_id=str(uuid.uuid4()),
            tournament=tournament,
            ai_players=ai_players,
            human_player_id=config.HUMAN_PLAYER_ID,
            is_debug=debug,
        )

    def start(self) -> None:
        if self.task is None:
            self.task = asyncio.create_task(self._run())

    def _view_public(self, hand, *, board_cards_override: list[str] | None = None) -> dict:
        return state_mod.view_public(
            self.tournament,
            hand,
            self.human_player_id,
            board_cards_override=board_cards_override,
            reveal_all=self.always_show_hands,
        )

    async def register(self, ws: WebSocket) -> None:
        await ws.accept()
        self.websockets.add(ws)
        await ws.send_json({"type": "snapshot", "state": self._view_public(self.tournament.current_hand)})

    def unregister(self, ws: WebSocket) -> None:
        self.websockets.discard(ws)

    async def broadcast(self, event: dict) -> None:
        dead = []
        for ws in self.websockets:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.websockets.discard(ws)

    def submit_human_action(self, action: str, amount: int | None) -> None:
        # this check is irreducibly session-specific -- Tournament has no notion
        # of a "pending future" to resolve, only of whose turn it is
        if self.pending_human_action is None or self.pending_human_action.done():
            raise HumanTurnError("not currently awaiting an action")

        try:
            self.tournament.validate_action(self.human_player_id, action, amount)
        except ActionError as exc:
            raise HumanTurnError(str(exc)) from exc

        self.pending_human_action.set_result(ActionResult(action=action, amount=amount))

    def set_forced_ai_action(self, mode: str | None) -> None:
        if not self.is_debug:
            raise DebugOnlyError("forced actions are a debug-only control")
        if mode is not None and mode not in FORCED_ACTION_MODES:
            raise ValueError(f"unknown forced action mode {mode!r}")
        self.forced_ai_action = mode

    def set_always_show_hands(self, enabled: bool) -> None:
        if not self.is_debug:
            raise DebugOnlyError("always-show-hands is a debug-only control")
        self.always_show_hands = enabled

    async def broadcast_snapshot(self) -> None:
        """Nudges connected clients with a fresh state snapshot immediately,
        rather than waiting for the next natural game event to reflect a
        debug-only change (e.g. toggling always_show_hands)."""
        await self.broadcast({"type": "snapshot", "state": self._view_public(self.tournament.current_hand)})

    def _forced_action_result(self, legal) -> ActionResult | None:
        """Overrides an AI's decide() with a single fixed action, still
        clamped to whatever's actually legal for it right now (e.g. "force
        fold" can't fold when there's nothing to fold to). None means no
        override is active -- fall through to the AI's own decision."""
        mode = self.forced_ai_action
        if mode == "all_in":
            if legal.can_bet_or_raise:
                return ActionResult(action="bet_or_raise_to", amount=legal.max_bet_to)
            if legal.can_check_or_call:
                return ActionResult(action="check_or_call")
            return ActionResult(action="fold")
        if mode == "call":
            if legal.can_check_or_call:
                return ActionResult(action="check_or_call")
            return ActionResult(action="fold")
        if mode == "check":
            if legal.can_check_or_call and legal.call_amount == 0:
                return ActionResult(action="check_or_call")
            if legal.can_fold:
                return ActionResult(action="fold")
            return ActionResult(action="check_or_call")
        if mode == "fold":
            if legal.can_fold:
                return ActionResult(action="fold")
            return ActionResult(action="check_or_call")
        return None

    async def force_end_round(self) -> None:
        """Debug-only: immediately end the in-progress hand no matter what
        it's doing, forfeiting whatever's already committed this hand. Stops
        and restarts the game loop task so the next hand deals cleanly."""
        if not self.is_debug:
            raise DebugOnlyError("end round is a debug-only control")

        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        self.pending_human_action = None

        net_results = self.tournament.forfeit_current_hand()
        if net_results:
            # only broadcast a hand_result if a hand was actually in progress
            # to forfeit -- e.g. clicking this between hands (during the
            # normal result-display pause) has nothing to report, but still
            # skips straight to dealing the next hand via self.start() below
            await self.broadcast(
                {
                    "type": "hand_result",
                    "net_results": net_results,
                    "winners": [],
                    "winning_hand_label": None,
                    "winning_board_cards": [],
                    "bust_events": self.tournament.last_bust_events,
                    "state": self._view_public(None),
                }
            )

        if self.tournament.is_over:
            await self.broadcast(
                {
                    "type": "tournament_over",
                    "winner_player_id": self.tournament.winner.id if self.tournament.winner else None,
                }
            )
        else:
            self.start()

    async def _synthesize_for(self, pid: str, message: str | None) -> tuple[str | None, float | None]:
        """Synthesizes `message` in `pid`'s voice, tolerating both a null
        message (nothing to say) and a null synthesis result (TTS model not
        downloaded yet) -- either way collapses to (None, None)."""
        if not message:
            return None, None
        audio = await synthesize(message, config.VOICE_BY_PLAYER_ID.get(pid, ""))
        return audio if audio else (None, None)

    def _crossed_street_sizes(self, hand, board_before_len: int) -> list[int]:
        """Which cumulative board sizes (flop/turn/river) this action revealed,
        in order. Empty if the board didn't change; a single entry for a normal
        one-street reveal; more than one only when nobody was left to act and
        pokerkit dealt multiple remaining streets in this single call."""
        new_len = len(hand.board_cards)
        return [size for size in STREET_BOARD_SIZES if board_before_len < size <= new_len]

    async def _reveal_board_in_stages(self, hand, crossed_sizes: list[int]) -> None:
        """Broadcast each street this action revealed one at a time with a pause
        between them, instead of the client seeing the whole runout at once.
        Only called when more than one street was crossed by a single action
        (see `_crossed_street_sizes`) -- the normal single-street case is
        already shown by the caller's own `player_action` broadcast."""
        board_after = hand.board_cards
        for size in crossed_sizes:
            await self.broadcast(
                {
                    "type": "board_dealt",
                    "board_cards": board_after[:size],
                    "state": self._view_public(hand, board_cards_override=board_after[:size]),
                }
            )
            await asyncio.sleep(config.BOARD_REVEAL_DELAY_SECONDS)

    async def _broadcast_win_reactions(
        self, hand, winners: list[str], net_results: dict[str, int], board_len_at_end: int
    ) -> float:
        """Guarantees a reaction line from each AI winner -- every other
        action's talk is a probabilistic roll (see is_talk_eligible/talk_chance),
        but the winner isn't known until betting is fully over, so this can't
        be folded into any action's own decide() call; it's a separate call
        made only now.

        Always reacts on a real showdown (with the actual hand category to
        cite), and also reacts on a fold-out win once it's made it to the
        turn or river (no hand category to cite there -- cards were never
        shown, just "everyone folded to you"). A fold-out win on preflop or
        the flop stays silent -- too early to be worth bragging about.

        Returns the total real seconds spent pacing around reaction audio, so
        the caller can factor that into the post-hand display delay (see
        _run's HAND_RESULT_DISPLAY_SECONDS handling)."""
        revealed = hand.revealed_hole_cards()
        is_showdown = bool(revealed)
        if not is_showdown and board_len_at_end < 4:  # fold-out, preflop or flop
            return 0.0

        total_dialogue_seconds = 0.0
        for pid in winners:
            if self.tournament.player(pid).kind != "ai":
                continue
            hand_label = hand.winning_hand_label(pid) if pid in revealed else None
            view = state_mod.view_for_actor(self.tournament, hand, pid)
            try:
                # provider APIs are flaky by nature -- a failed reaction just
                # means silence, never a crashed tournament loop
                message = await self.ai_players[pid].react_to_win(view, hand_label, net_results[pid])
            except Exception:
                message = None
            if not message:
                continue
            audio_base64, audio_duration = await self._synthesize_for(pid, message)
            await self.broadcast(
                {
                    "type": "win_reaction",
                    "player_id": pid,
                    "message": message,
                    "audio_base64": audio_base64,
                    "audio_duration": audio_duration,
                }
            )
            if audio_duration is not None:
                wait = audio_duration + config.AUDIO_TRAILING_DELAY_SECONDS
                await asyncio.sleep(wait)
                total_dialogue_seconds += wait
        return total_dialogue_seconds

    def _sore_loser_target(
        self, hand, winners: list[str], net_results: dict[str, int], board_len_at_end: int
    ) -> str | None:
        """The AI seat (if any) that should get a guaranteed sore-loser
        reaction this hand: the hand reached a real showdown on the turn or
        river, exactly two seats were still live when it was decided, one of
        them is the human, and the AI lost (not a chop) with its cards shown.
        Anything short of that -- a 3-way pot, a fold-out, a preflop/flop-only
        board, a split, or a mucked-without-showing loss -- returns None."""
        revealed = hand.revealed_hole_cards()
        if not revealed or board_len_at_end < 4:
            return None
        live = [pid for pid in hand.seat_player_ids if not hand.is_folded(pid)]
        if len(live) != 2 or self.human_player_id not in live:
            return None
        ai_pid = next(pid for pid in live if pid != self.human_player_id)
        if ai_pid in winners or net_results.get(ai_pid, 0) >= 0 or ai_pid not in revealed:
            return None
        return ai_pid

    async def _broadcast_loss_reaction(
        self, hand, winners: list[str], net_results: dict[str, int], board_len_at_end: int
    ) -> float:
        """Mirrors _broadcast_win_reactions for the losing side of a heads-up
        showdown: when an AI just lost a 1-on-1 pot to the human on the turn
        or river, it's guaranteed a sore-loser reaction instead of the usual
        probabilistic action talk. Returns the dialogue seconds spent, same
        as _broadcast_win_reactions, to fold into the post-hand pacing."""
        ai_pid = self._sore_loser_target(hand, winners, net_results, board_len_at_end)
        if ai_pid is None:
            return 0.0

        hand_label = hand.winning_hand_label(ai_pid)
        view = state_mod.view_for_actor(self.tournament, hand, ai_pid)
        # the human's hand is only knowable here because this is a post-showdown
        # reaction call, not the regular decide()-time view -- and only when it
        # was actually revealed (see _sore_loser_target: the human, as the
        # winner of a 2-way pot, always ends up shown, but this stays defensive)
        revealed = hand.revealed_hole_cards()
        view = {**view, "opponent_hole_cards": revealed.get(self.human_player_id)}
        try:
            message = await self.ai_players[ai_pid].react_to_loss(view, hand_label, -net_results[ai_pid])
        except Exception:
            message = None
        if not message:
            return 0.0

        audio_base64, audio_duration = await self._synthesize_for(ai_pid, message)
        await self.broadcast(
            {
                "type": "loss_reaction",
                "player_id": ai_pid,
                "message": message,
                "audio_base64": audio_base64,
                "audio_duration": audio_duration,
            }
        )
        if audio_duration is None:
            return 0.0
        wait = audio_duration + config.AUDIO_TRAILING_DELAY_SECONDS
        await asyncio.sleep(wait)
        return wait

    async def _run(self) -> None:
        try:
            while not self.tournament.is_over:
                hand = self.tournament.start_hand()
                await self.broadcast({"type": "hand_started", "state": self._view_public(hand)})

                while not hand.is_over:
                    actor_id = hand.current_actor_id
                    if actor_id == self.human_player_id:
                        view = state_mod.view_for_actor(self.tournament, hand, actor_id)
                        await self.broadcast({"type": "awaiting_action", "view": view})
                        loop = asyncio.get_event_loop()
                        self.pending_human_action = loop.create_future()
                        result = await self.pending_human_action
                        self.pending_human_action = None
                    else:
                        view = state_mod.view_for_actor(self.tournament, hand, actor_id)
                        await asyncio.sleep(config.AI_THINKING_DELAY_SECONDS)
                        forced = self._forced_action_result(hand.legal_actions()) if self.is_debug else None
                        if forced is not None:
                            result = forced
                        else:
                            try:
                                # provider APIs are flaky by nature (timeouts, rate limits,
                                # occasional malformed JSON) -- never let one bad call kill
                                # the whole tournament loop.
                                result = await self.ai_players[actor_id].decide(view)
                                result.amount = clamp_amount(view, result.amount)
                            except Exception:
                                result = ActionResult(action="fold", amount=None, message=None)

                    board_before_len = len(hand.board_cards)
                    try:
                        self.tournament.apply_action(actor_id, result.action, result.amount)
                    except ActionError:
                        # a misbehaving AI response falls back to the safest legal action
                        legal = hand.legal_actions()
                        fallback = "check_or_call" if legal.can_check_or_call else "fold"
                        self.tournament.apply_action(actor_id, fallback, None)
                        result = ActionResult(action=fallback, amount=None, message=None)

                    if not is_talk_eligible(result.action, view, result.amount):
                        result.message = None

                    audio_base64, audio_duration = await self._synthesize_for(actor_id, result.message)

                    # if this action left nobody to decide anything (e.g.
                    # everyone remaining is all-in), pokerkit deals every
                    # remaining street in this single call -- don't show any of
                    # those extra streets in this broadcast yet; they get
                    # revealed one at a time below instead
                    crossed_sizes = self._crossed_street_sizes(hand, board_before_len)
                    board_override = board_before_len if len(crossed_sizes) > 1 else None

                    await self.broadcast(
                        {
                            "type": "player_action",
                            "player_id": actor_id,
                            "action": result.action,
                            "amount": result.amount,
                            # call_amount as of the decision (before this action was applied)
                            # -- lets the frontend tell a check apart from a call, and an
                            # opening bet apart from a raise, since `amount` alone can't.
                            "call_amount": view["legal_actions"]["call_amount"],
                            "message": result.message,
                            "audio_base64": audio_base64,
                            "audio_duration": audio_duration,
                            "state": self._view_public(
                                hand,
                                board_cards_override=hand.board_cards[:board_override]
                                if board_override is not None
                                else None,
                            ),
                        }
                    )

                    # hold on this turn until the line has actually finished
                    # playing (plus a beat), so the next action doesn't step on it
                    if audio_duration is not None:
                        await asyncio.sleep(audio_duration + config.AUDIO_TRAILING_DELAY_SECONDS)

                    if len(crossed_sizes) > 1:
                        await self._reveal_board_in_stages(hand, crossed_sizes)

                net_results = self.tournament.finish_hand()
                winners = [pid for pid, net in net_results.items() if net > 0]
                board_len_at_end = len(hand.board_cards)

                reveal_dialogue_seconds = await self._broadcast_win_reactions(
                    hand, winners, net_results, board_len_at_end
                )
                reveal_dialogue_seconds += await self._broadcast_loss_reaction(
                    hand, winners, net_results, board_len_at_end
                )

                # only a real showdown has a "type of hand" worth announcing --
                # a fold-out win never reveals cards, so there's nothing to
                # evaluate (revealed_hole_cards is the same signal the client
                # already uses to decide whether cards were shown at all)
                revealed = hand.revealed_hole_cards()
                labeled_winner_id = next((pid for pid in winners if pid in revealed), None)
                winning_hand_label = (
                    hand.winning_hand_label(labeled_winner_id) if labeled_winner_id else None
                )
                # which of the board cards specifically were part of that best
                # 5-card hand (as opposed to hole cards) -- lets the client
                # visually call out e.g. the 4 board cards that make a
                # straight, instead of just naming the category in text
                winning_board_cards: list[str] = []
                if labeled_winner_id:
                    best_cards = hand.winning_hand_cards(labeled_winner_id) or []
                    winning_board_cards = [c for c in hand.board_cards if c in best_cards]

                await self.broadcast(
                    {
                        "type": "hand_result",
                        "net_results": net_results,
                        "winners": winners,
                        "winning_hand_label": winning_hand_label,
                        "winning_board_cards": winning_board_cards,
                        "bust_events": self.tournament.last_bust_events,
                        "state": self._view_public(None),
                    }
                )

                # give the table a beat to see who won (and their hand, if it
                # went to showdown) before the next hand is dealt -- but if the
                # reveal dialogue itself already ran longer than that beat,
                # don't stack the full delay on top of it: just add one more
                # second once the dialogue's done instead. A fold-out win (no
                # winning_hand_label) has less to actually look at, so it gets
                # the shorter display window.
                display_seconds = (
                    config.HAND_RESULT_DISPLAY_SECONDS_NO_REVEAL
                    if winning_hand_label is None
                    else config.HAND_RESULT_DISPLAY_SECONDS
                )
                if reveal_dialogue_seconds > display_seconds:
                    await asyncio.sleep(1.0)
                else:
                    await asyncio.sleep(display_seconds - reveal_dialogue_seconds)

            await self.broadcast(
                {
                    "type": "tournament_over",
                    "winner_player_id": self.tournament.winner.id if self.tournament.winner else None,
                }
            )
        except Exception as exc:  # surfaces loop crashes to connected clients instead of failing silently
            await self.broadcast({"type": "error", "message": str(exc)})
            raise


SESSIONS: dict[str, GameSession] = {}
