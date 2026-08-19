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
from ..engine import state as state_mod
from ..engine.tournament import ActionError, Tournament
from ..tts.kokoro_tts import synthesize


class HumanTurnError(Exception):
    pass


# cumulative board size at the end of each street: flop / turn / river
STREET_BOARD_SIZES = (3, 4, 5)


@dataclass
class GameSession:
    tournament_id: str
    tournament: Tournament
    ai_players: dict[str, object]
    human_player_id: str
    websockets: set[WebSocket] = field(default_factory=set)
    pending_human_action: asyncio.Future | None = field(default=None, init=False)
    task: asyncio.Task | None = field(default=None, init=False)

    @classmethod
    def new(cls, human_name: str) -> "GameSession":
        specs = [(config.HUMAN_PLAYER_ID, human_name, "human")] + [
            (pid, name, "ai") for pid, name in config.AI_SEATS
        ]
        tournament = Tournament.new(specs)
        ai_players = {pid: create_ai_player(pid, name) for pid, name in config.AI_SEATS}
        return cls(
            tournament_id=str(uuid.uuid4()),
            tournament=tournament,
            ai_players=ai_players,
            human_player_id=config.HUMAN_PLAYER_ID,
        )

    def start(self) -> None:
        if self.task is None:
            self.task = asyncio.create_task(self._run())

    async def register(self, ws: WebSocket) -> None:
        await ws.accept()
        self.websockets.add(ws)
        await ws.send_json(
            {"type": "snapshot", "state": state_mod.view_public(self.tournament, self.tournament.current_hand, self.human_player_id)}
        )

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
                    "state": state_mod.view_public(
                        self.tournament, hand, self.human_player_id, board_cards_override=board_after[:size]
                    ),
                }
            )
            await asyncio.sleep(config.BOARD_REVEAL_DELAY_SECONDS)

    async def _run(self) -> None:
        try:
            while not self.tournament.is_over:
                hand = self.tournament.start_hand()
                await self.broadcast(
                    {"type": "hand_started", "state": state_mod.view_public(self.tournament, hand, self.human_player_id)}
                )

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

                    if not is_talk_eligible(result.action, view):
                        result.message = None

                    audio = (
                        await synthesize(result.message, config.VOICE_BY_PLAYER_ID.get(actor_id, ""))
                        if result.message
                        else None
                    )
                    audio_base64, audio_duration = audio if audio else (None, None)

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
                            "state": state_mod.view_public(
                                self.tournament,
                                hand,
                                self.human_player_id,
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
                await self.broadcast(
                    {
                        "type": "hand_result",
                        "net_results": net_results,
                        "winners": winners,
                        "bust_events": self.tournament.last_bust_events,
                        "state": state_mod.view_public(self.tournament, None, self.human_player_id),
                    }
                )

                # give the table a beat to see who won (and their hand, if it
                # went to showdown) before the next hand is dealt
                await asyncio.sleep(config.HAND_RESULT_DISPLAY_SECONDS)

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
