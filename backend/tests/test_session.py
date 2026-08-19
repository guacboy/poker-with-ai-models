from __future__ import annotations

import asyncio

import pytest

from app import config
from app.ai.base import ActionResult
from app.api.session import GameSession, HumanTurnError


class StubPlayer:
    """A deterministic AI stub sharing one mutable flag across every seat:
    whichever seat is asked to decide first raises to the minimum (if legal),
    and nobody raises after that -- everyone else just calls/checks."""

    def __init__(self, player_id: str, display_name: str, shared: dict):
        self.player_id = player_id
        self.display_name = display_name
        self._shared = shared

    async def decide(self, view: dict) -> ActionResult:
        legal = view["legal_actions"]
        if not self._shared["raised"] and legal["can_bet_or_raise"]:
            self._shared["raised"] = True
            return ActionResult(action="bet_or_raise_to", amount=legal["min_bet_to"])
        if legal["can_check_or_call"]:
            return ActionResult(action="check_or_call")
        return ActionResult(action="fold")


class FakeWebSocket:
    def __init__(self):
        self.events: list[dict] = []

    async def send_json(self, data: dict) -> None:
        self.events.append(data)


@pytest.mark.asyncio
async def test_player_action_events_include_call_amount(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "AI_THINKING_DELAY_SECONDS", 0)

    session = GameSession.new("Dylan")
    shared = {"raised": False}
    session.ai_players = {
        p.id: StubPlayer(p.id, p.name, shared) for p in session.tournament.players if p.kind == "ai"
    }
    ws = FakeWebSocket()
    session.websockets.add(ws)
    session.start()

    for _ in range(200):
        await asyncio.sleep(0.01)
        if session.pending_human_action is not None and not session.pending_human_action.done():
            hand = session.tournament.current_hand
            action = "check_or_call" if hand.legal_actions().can_check_or_call else "fold"
            session.submit_human_action(action, None)
        if session.tournament.hand_count >= 1:
            break

    session.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await session.task

    player_actions = [e for e in ws.events if e["type"] == "player_action"]
    assert player_actions, "expected at least one player_action event"
    for event in player_actions:
        assert "call_amount" in event
        assert isinstance(event["call_amount"], int)
        assert event["call_amount"] >= 0

    # the very first action of the hand always faces exactly the unraised big
    # blind, regardless of who's first to act
    assert player_actions[0]["call_amount"] == 100

    raise_events = [e for e in player_actions if e["action"] == "bet_or_raise_to"]
    assert len(raise_events) == 1, "the shared flag limits this hand to exactly one raise"
    raise_index = player_actions.index(raise_events[0])

    # whoever acts immediately after the raiser is, structurally, also not yet
    # committed anything this street (only the blinds are, and they always act
    # last preflop) -- so calling should cost exactly the raised-to amount
    next_caller = player_actions[raise_index + 1]
    assert next_caller["action"] == "check_or_call"
    assert next_caller["call_amount"] == raise_events[0]["amount"]


@pytest.mark.asyncio
async def test_submit_human_action_rejects_illegal_action_without_consuming_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers the human-facing rejection path after consolidating its
    validation onto Tournament.validate_action: an illegal submission must
    raise (not silently fall back, the way a misbehaving AI does), and must
    leave the pending turn intact so a follow-up legal submission still works."""
    monkeypatch.setattr(config, "AI_THINKING_DELAY_SECONDS", 0)

    session = GameSession.new("Dylan")
    shared = {"raised": False}
    session.ai_players = {
        p.id: StubPlayer(p.id, p.name, shared) for p in session.tournament.players if p.kind == "ai"
    }
    ws = FakeWebSocket()
    session.websockets.add(ws)
    session.start()

    for _ in range(200):
        await asyncio.sleep(0.01)
        if session.pending_human_action is not None and not session.pending_human_action.done():
            break

    assert session.pending_human_action is not None, "expected the human's turn to come up"
    pending = session.pending_human_action
    legal = session.tournament.current_hand.legal_actions()

    with pytest.raises(HumanTurnError):
        session.submit_human_action("bet_or_raise_to", legal.min_bet_to - 1)

    # rejected -- the turn is still open, same future, nothing resolved
    assert session.pending_human_action is pending
    assert not pending.done()

    # a legal follow-up still works normally
    session.submit_human_action("check_or_call", None)
    assert pending.done()

    session.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await session.task
