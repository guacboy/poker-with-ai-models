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
                            "state": state_mod.view_public(self.tournament, hand, self.human_player_id),
                        }
                    )

                    # hold on this turn until the line has actually finished
                    # playing (plus a beat), so the next action doesn't step on it
                    if audio_duration is not None:
                        await asyncio.sleep(audio_duration + config.AUDIO_TRAILING_DELAY_SECONDS)

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
