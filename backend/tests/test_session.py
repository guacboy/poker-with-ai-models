from __future__ import annotations

import asyncio

import pytest

from app import config
from app.ai.base import ActionResult
from app.api import session as session_module
from app.api.session import GameSession, HumanTurnError


class AlwaysRaiseWithMessagePlayer:
    """Every AI seat raises (or calls, if raising isn't legal) and always
    attaches a message -- raising is always talk-eligible, so this reliably
    triggers the post-dialog pacing delay without depending on randomness."""

    def __init__(self, player_id: str, display_name: str):
        self.player_id = player_id
        self.display_name = display_name

    async def decide(self, view: dict) -> ActionResult:
        legal = view["legal_actions"]
        if legal["can_bet_or_raise"]:
            return ActionResult(action="bet_or_raise_to", amount=legal["min_bet_to"], message="hi")
        if legal["can_check_or_call"]:
            return ActionResult(action="check_or_call", message="hi")
        return ActionResult(action="fold", message="hi")


class AlwaysFoldPlayer:
    """Folds whenever folding is actually legal (i.e. there's a real bet to
    get away from); checks otherwise, since pokerkit disallows folding when
    there's nothing to call. Used to deterministically drive a hand to a
    fold-out win with no showdown."""

    def __init__(self, player_id: str, display_name: str):
        self.player_id = player_id
        self.display_name = display_name

    async def decide(self, view: dict) -> ActionResult:
        legal = view["legal_actions"]
        action = "fold" if legal["can_fold"] else "check_or_call"
        return ActionResult(action=action)


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


@pytest.mark.asyncio
async def test_pacing_waits_for_audio_duration_plus_trailing_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a spoken line, the loop should sleep for (audio duration +
    AUDIO_TRAILING_DELAY_SECONDS) before moving to the next actor, not just
    the flat AI_THINKING_DELAY_SECONDS pacing used before every decision."""
    monkeypatch.setattr(config, "AI_THINKING_DELAY_SECONDS", 0)
    monkeypatch.setattr(config, "AUDIO_TRAILING_DELAY_SECONDS", 0.4)

    fake_duration = 0.3
    requested_sleeps: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_synthesize(text: str, voice: str):
        return "fakebase64", fake_duration

    async def spying_sleep(delay: float, *args, **kwargs):
        requested_sleeps.append(delay)
        # cap the actual wait so the test doesn't really sit through 0.7s+ per action
        await real_sleep(min(delay, 0.01))

    monkeypatch.setattr(session_module, "synthesize", fake_synthesize)
    monkeypatch.setattr(asyncio, "sleep", spying_sleep)

    session = GameSession.new("Dylan")
    session.ai_players = {
        p.id: AlwaysRaiseWithMessagePlayer(p.id, p.name)
        for p in session.tournament.players
        if p.kind == "ai"
    }
    ws = FakeWebSocket()
    session.websockets.add(ws)
    session.start()

    for _ in range(500):
        await real_sleep(0.005)
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
    talking_actions = [e for e in player_actions if e["message"] is not None]
    assert talking_actions, "expected at least one AI action to carry a message"
    for event in talking_actions:
        assert event["audio_duration"] == pytest.approx(fake_duration)

    expected_wait = fake_duration + 0.4
    assert any(delay == pytest.approx(expected_wait) for delay in requested_sleeps), (
        f"expected a sleep call for ~{expected_wait}s (audio + trailing delay), "
        f"got {requested_sleeps}"
    )


@pytest.mark.asyncio
async def test_fold_out_hand_result_reports_winner_hides_cards_and_waits_for_display_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hand everyone folds out of (a walk) should: name exactly one winner
    in the hand_result event, never reveal that winner's (or anyone else's)
    hole cards since there was no showdown, and hold the table on the result
    for HAND_RESULT_DISPLAY_SECONDS before the loop would deal the next hand."""
    monkeypatch.setattr(config, "AI_THINKING_DELAY_SECONDS", 0)
    monkeypatch.setattr(config, "HAND_RESULT_DISPLAY_SECONDS", 0.3)

    requested_sleeps: list[float] = []
    real_sleep = asyncio.sleep

    async def spying_sleep(delay: float, *args, **kwargs):
        requested_sleeps.append(delay)
        # cap the actual wait so the test doesn't really sit through 0.3s+
        await real_sleep(min(delay, 0.01))

    monkeypatch.setattr(asyncio, "sleep", spying_sleep)

    session = GameSession.new("Dylan")
    session.ai_players = {
        p.id: AlwaysFoldPlayer(p.id, p.name) for p in session.tournament.players if p.kind == "ai"
    }
    ws = FakeWebSocket()
    session.websockets.add(ws)
    session.start()

    for _ in range(500):
        await real_sleep(0.005)
        if session.pending_human_action is not None and not session.pending_human_action.done():
            legal = session.tournament.current_hand.legal_actions()
            action = "fold" if legal.can_fold else "check_or_call"
            session.submit_human_action(action, None)
        if any(e["type"] == "hand_result" for e in ws.events):
            break

    # give the loop task a scheduling turn to actually reach (and record) the
    # post-result sleep, which is the very next statement after the broadcast
    await real_sleep(0.05)

    session.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await session.task

    hand_results = [e for e in ws.events if e["type"] == "hand_result"]
    assert hand_results, "expected a hand_result event"
    result = hand_results[0]

    assert len(result["winners"]) == 1
    winner_id = result["winners"][0]
    assert result["net_results"][winner_id] > 0
    assert winner_id != config.HUMAN_PLAYER_ID, "everyone else folded around to a single AI seat"

    # a walk never reaches showdown -- the winner's cards stay hidden, same as
    # everyone else's, in the last broadcast before the hand ended
    player_actions = [e for e in ws.events if e["type"] == "player_action"]
    last_state_hand = player_actions[-1]["state"]["hand"]
    winner_seat = next(s for s in last_state_hand["seats"] if s["player_id"] == winner_id)
    assert winner_seat["hole_cards"] is None

    assert any(delay == pytest.approx(0.3) for delay in requested_sleeps), (
        f"expected a sleep call for the hand-result display delay, got {requested_sleeps}"
    )
