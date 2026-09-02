from __future__ import annotations

import asyncio

import pytest

from app import config
from app.ai.base import ActionResult
from app.ai.mock_player import MockPlayer
from app.ai.providers.anthropic_player import AnthropicPlayer
from app.api import session as session_module
from app.api.session import DebugOnlyError, GameSession, HumanTurnError


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

    async def react_to_win(self, view: dict, hand_label: str, amount_won: int) -> str | None:
        return "gg"

    async def react_to_loss(self, view: dict, hand_label: str, amount_lost: int) -> str | None:
        return "rigged"


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

    async def react_to_win(self, view: dict, hand_label: str, amount_won: int) -> str | None:
        return "gg"

    async def react_to_loss(self, view: dict, hand_label: str, amount_lost: int) -> str | None:
        return "rigged"


class AlwaysShoveAllInPlayer:
    """Shoves all-in the instant it's legal to raise; otherwise calls (which
    pokerkit automatically caps to the remaining stack, i.e. also an all-in
    once the stack is short); folding is never chosen. Used to deterministically
    get every active seat all-in preflop, so betting closes with nobody left to
    decide anything and pokerkit deals out the rest of the board in one shot."""

    def __init__(self, player_id: str, display_name: str):
        self.player_id = player_id
        self.display_name = display_name

    async def decide(self, view: dict) -> ActionResult:
        legal = view["legal_actions"]
        if legal["can_bet_or_raise"]:
            return ActionResult(action="bet_or_raise_to", amount=legal["max_bet_to"])
        if legal["can_check_or_call"]:
            return ActionResult(action="check_or_call")
        return ActionResult(action="fold")

    async def react_to_win(self, view: dict, hand_label: str, amount_won: int) -> str | None:
        return f"Winning with {hand_label}!"

    async def react_to_loss(self, view: dict, hand_label: str, amount_lost: int) -> str | None:
        return f"Losing with {hand_label}? Rigged."


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

    async def react_to_win(self, view: dict, hand_label: str, amount_won: int) -> str | None:
        return "gg"

    async def react_to_loss(self, view: dict, hand_label: str, amount_lost: int) -> str | None:
        return "rigged"


class CallUntilTurnThenBetAndFoldPlayer:
    """Checks/calls through preflop and flop (never folds, never raises) so
    the hand always reaches the turn with everyone still in. On the turn (or
    later), the first seat asked to act bets; every seat after that folds to
    it -- deterministically produces a fold-out win that made it past the
    flop, for testing the turn/river fold-out reaction rule."""

    def __init__(self, player_id: str, display_name: str, shared: dict):
        self.player_id = player_id
        self.display_name = display_name
        self._shared = shared

    async def decide(self, view: dict) -> ActionResult:
        legal = view["legal_actions"]
        street = view["street_index"]
        if street is not None and street >= 2:  # turn or river
            if not self._shared["bet"] and legal["can_bet_or_raise"]:
                self._shared["bet"] = True
                return ActionResult(action="bet_or_raise_to", amount=legal["min_bet_to"])
            if legal["can_fold"]:
                return ActionResult(action="fold")
            return ActionResult(action="check_or_call")
        if legal["can_check_or_call"]:
            return ActionResult(action="check_or_call")
        return ActionResult(action="fold")

    async def react_to_win(self, view: dict, hand_label: str | None, amount_won: int) -> str | None:
        return "Everyone folded, easy money."

    async def react_to_loss(self, view: dict, hand_label: str, amount_lost: int) -> str | None:
        return "rigged"


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
    for HAND_RESULT_DISPLAY_SECONDS_NO_REVEAL (the shorter, no-cards-to-look-at
    delay -- there's no winning_hand_label here) before dealing the next hand."""
    monkeypatch.setattr(config, "AI_THINKING_DELAY_SECONDS", 0)
    monkeypatch.setattr(config, "HAND_RESULT_DISPLAY_SECONDS", 999)  # would fail the assertion below if used by mistake
    monkeypatch.setattr(config, "HAND_RESULT_DISPLAY_SECONDS_NO_REVEAL", 0.3)

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
        f"expected a sleep call for the no-reveal hand-result display delay, got {requested_sleeps}"
    )

    # a walk never reaches showdown -- there's no hand to name a category for
    assert result["winning_hand_label"] is None


@pytest.mark.asyncio
async def test_showdown_hand_result_names_the_winning_hand_category(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hand that actually reaches showdown (forced here by shoving everyone
    all-in preflop) should report a real pokerkit hand-category label for the
    winning hand, e.g. "Straight flush" -- not just who won -- plus which of
    the board cards were actually part of that hand."""
    monkeypatch.setattr(config, "AI_THINKING_DELAY_SECONDS", 0)
    monkeypatch.setattr(config, "BOARD_REVEAL_DELAY_SECONDS", 0.01)
    monkeypatch.setattr(config, "HAND_RESULT_DISPLAY_SECONDS", 0.01)

    session = GameSession.new("Dylan")
    session.ai_players = {
        p.id: AlwaysShoveAllInPlayer(p.id, p.name) for p in session.tournament.players if p.kind == "ai"
    }
    ws = FakeWebSocket()
    session.websockets.add(ws)
    session.start()

    for _ in range(500):
        await asyncio.sleep(0.01)
        if session.pending_human_action is not None and not session.pending_human_action.done():
            legal = session.tournament.current_hand.legal_actions()
            if legal.can_bet_or_raise:
                session.submit_human_action("bet_or_raise_to", legal.max_bet_to)
            else:
                session.submit_human_action("check_or_call", None)
        if any(e["type"] == "hand_result" for e in ws.events):
            break

    session.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await session.task

    hand_results = [e for e in ws.events if e["type"] == "hand_result"]
    assert hand_results, "expected a hand_result event"
    result = hand_results[0]
    label = result["winning_hand_label"]

    valid_labels = {
        "High card",
        "One pair",
        "Two pair",
        "Three of a kind",
        "Straight",
        "Flush",
        "Full house",
        "Four of a kind",
        "Straight flush",
    }
    assert label in valid_labels, f"expected a real hand category, got {label!r}"

    # winning_board_cards is trimmed to only the cards that actually make the
    # hand that category (see Hand._defining_cards -- e.g. just a pair's 2
    # cards, not unrelated kickers), so it can legitimately be empty (a
    # pocket pair with no matching board card) -- what matters here is that
    # every card it does report is a real card that's actually on the board.
    # result["state"]["hand"] is null post-showdown (the hand's already
    # over), so the board is only visible via the last pre-result broadcast
    # that carried one -- either a player_action or, for an early all-in
    # runout staged street-by-street, a board_dealt event instead.
    hand_result_index = ws.events.index(result)
    board_snapshots = [
        e for e in ws.events[:hand_result_index] if e.get("state", {}).get("hand") is not None
    ]
    board_cards = board_snapshots[-1]["state"]["hand"]["board_cards"]
    winning_board_cards = result["winning_board_cards"]
    assert set(winning_board_cards) <= set(board_cards)


@pytest.mark.asyncio
async def test_showdown_win_triggers_a_guaranteed_win_reaction_for_every_ai_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every other action's talk is a probabilistic roll (see
    is_talk_eligible/talk_chance), but a real showdown win is guaranteed a
    reaction -- a separate call made only once the winner(s) are known, since
    that's not decided until after all betting (and every decide() call) is
    already over."""
    monkeypatch.setattr(config, "AI_THINKING_DELAY_SECONDS", 0)
    monkeypatch.setattr(config, "BOARD_REVEAL_DELAY_SECONDS", 0.01)
    monkeypatch.setattr(config, "HAND_RESULT_DISPLAY_SECONDS", 0.01)

    async def fake_synthesize(text: str, voice: str):
        return "fakebase64", 0.01

    monkeypatch.setattr(session_module, "synthesize", fake_synthesize)

    session = GameSession.new("Dylan")
    session.ai_players = {
        p.id: AlwaysShoveAllInPlayer(p.id, p.name) for p in session.tournament.players if p.kind == "ai"
    }
    ws = FakeWebSocket()
    session.websockets.add(ws)
    session.start()

    for _ in range(500):
        await asyncio.sleep(0.01)
        if session.pending_human_action is not None and not session.pending_human_action.done():
            legal = session.tournament.current_hand.legal_actions()
            if legal.can_bet_or_raise:
                session.submit_human_action("bet_or_raise_to", legal.max_bet_to)
            else:
                session.submit_human_action("check_or_call", None)
        # hand_result now broadcasts BEFORE the win-reaction dialogue (see
        # GameSession._run) rather than after, so its arrival alone no longer
        # means every winner's reaction has already been broadcast too --
        # wait for a win_reaction from each AI winner as well, or cancelling
        # here could race a reaction that just hasn't fired yet.
        hand_results = [e for e in ws.events if e["type"] == "hand_result"]
        if hand_results:
            ai_winners = {pid for pid in hand_results[0]["winners"] if pid != config.HUMAN_PLAYER_ID}
            reacted = {e["player_id"] for e in ws.events if e["type"] == "win_reaction"}
            if ai_winners <= reacted:
                break

    session.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await session.task

    hand_results = [e for e in ws.events if e["type"] == "hand_result"]
    assert hand_results, "expected a hand_result event"
    result = hand_results[0]
    ai_winners = {pid for pid in result["winners"] if pid != config.HUMAN_PLAYER_ID}

    win_reactions = [e for e in ws.events if e["type"] == "win_reaction"]
    assert {e["player_id"] for e in win_reactions} == ai_winners
    for event in win_reactions:
        assert event["message"] == f"Winning with {result['winning_hand_label']}!"
        assert event["audio_base64"] == "fakebase64"


@pytest.mark.asyncio
async def test_long_reveal_dialogue_only_adds_one_second_past_display_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the reveal dialogue itself already runs longer than
    HAND_RESULT_DISPLAY_SECONDS, the next hand shouldn't wait the full
    display delay on top of that -- just one more second once the dialogue's
    actually done, not display_delay + dialogue stacked together."""
    monkeypatch.setattr(config, "AI_THINKING_DELAY_SECONDS", 0)
    monkeypatch.setattr(config, "BOARD_REVEAL_DELAY_SECONDS", 0.01)
    monkeypatch.setattr(config, "HAND_RESULT_DISPLAY_SECONDS", 0.05)
    monkeypatch.setattr(config, "AUDIO_TRAILING_DELAY_SECONDS", 0.1)

    fake_duration = 1.0  # comfortably longer than HAND_RESULT_DISPLAY_SECONDS
    requested_sleeps: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_synthesize(text: str, voice: str):
        return "fakebase64", fake_duration

    async def spying_sleep(delay: float, *args, **kwargs):
        requested_sleeps.append(delay)
        await real_sleep(min(delay, 0.01))

    monkeypatch.setattr(session_module, "synthesize", fake_synthesize)
    monkeypatch.setattr(asyncio, "sleep", spying_sleep)

    session = GameSession.new("Dylan")
    session.ai_players = {
        p.id: AlwaysShoveAllInPlayer(p.id, p.name) for p in session.tournament.players if p.kind == "ai"
    }
    ws = FakeWebSocket()
    session.websockets.add(ws)
    session.start()

    for _ in range(500):
        await real_sleep(0.005)
        if session.pending_human_action is not None and not session.pending_human_action.done():
            legal = session.tournament.current_hand.legal_actions()
            # fold whenever possible -- keeps the human out of the all-in
            # showdown entirely, so the winner is guaranteed to be one of the
            # AlwaysShoveAllInPlayer AI seats and this test isn't flaky on
            # whether the human happens to hold the best hand
            action = "fold" if legal.can_fold else "check_or_call"
            session.submit_human_action(action, None)
        if any(e["type"] == "hand_result" for e in ws.events):
            break

    # give the loop a scheduling turn to actually reach (and record) the
    # post-hand_result delay sleep, the statement right after the broadcast
    await real_sleep(0.05)

    session.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await session.task

    win_reactions = [e for e in ws.events if e["type"] == "win_reaction"]
    assert win_reactions, "expected at least one AI winner to react"

    assert any(delay == pytest.approx(1.0) for delay in requested_sleeps), (
        f"expected a 1-second sleep once the (longer-than-display-delay) reveal "
        f"dialogue finished, got {requested_sleeps}"
    )


@pytest.mark.asyncio
async def test_short_reveal_dialogue_tops_up_to_the_standard_display_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the reveal dialogue finishes well within HAND_RESULT_DISPLAY_SECONDS,
    the next hand should still wait out the rest of the standard delay -- not
    skip straight to the flat 1-second bump meant for the long-dialogue case."""
    monkeypatch.setattr(config, "AI_THINKING_DELAY_SECONDS", 0)
    monkeypatch.setattr(config, "BOARD_REVEAL_DELAY_SECONDS", 0.01)
    monkeypatch.setattr(config, "HAND_RESULT_DISPLAY_SECONDS", 0.5)
    monkeypatch.setattr(config, "AUDIO_TRAILING_DELAY_SECONDS", 0.1)

    fake_duration = 0.05  # comfortably shorter than HAND_RESULT_DISPLAY_SECONDS
    requested_sleeps: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_synthesize(text: str, voice: str):
        return "fakebase64", fake_duration

    async def spying_sleep(delay: float, *args, **kwargs):
        requested_sleeps.append(delay)
        await real_sleep(min(delay, 0.01))

    monkeypatch.setattr(session_module, "synthesize", fake_synthesize)
    monkeypatch.setattr(asyncio, "sleep", spying_sleep)

    session = GameSession.new("Dylan")
    session.ai_players = {
        p.id: AlwaysShoveAllInPlayer(p.id, p.name) for p in session.tournament.players if p.kind == "ai"
    }
    ws = FakeWebSocket()
    session.websockets.add(ws)
    session.start()

    for _ in range(500):
        await real_sleep(0.005)
        if session.pending_human_action is not None and not session.pending_human_action.done():
            legal = session.tournament.current_hand.legal_actions()
            if legal.can_bet_or_raise:
                session.submit_human_action("bet_or_raise_to", legal.max_bet_to)
            else:
                session.submit_human_action("check_or_call", None)
        if any(e["type"] == "hand_result" for e in ws.events):
            break

    await real_sleep(0.05)

    session.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await session.task

    hand_results = [e for e in ws.events if e["type"] == "hand_result"]
    result = hand_results[0]
    ai_winner_count = len([pid for pid in result["winners"] if pid != config.HUMAN_PLAYER_ID])
    win_reactions = [e for e in ws.events if e["type"] == "win_reaction"]

    dialogue_seconds = len(win_reactions) * (fake_duration + 0.1)
    expected_final_sleep = 0.5 - dialogue_seconds if dialogue_seconds <= 0.5 else 1.0

    assert any(delay == pytest.approx(expected_final_sleep, abs=0.02) for delay in requested_sleeps), (
        f"expected a top-up sleep of ~{expected_final_sleep}s "
        f"({len(win_reactions)}/{ai_winner_count} AI winners reacted), got {requested_sleeps}"
    )


@pytest.mark.asyncio
async def test_preflop_fold_out_win_never_triggers_a_win_reaction(monkeypatch: pytest.MonkeyPatch) -> None:
    """A walk that ends before/at the flop (everyone folds around to one
    seat) is too early to be worth bragging about -- no win_reaction should
    fire even though the winner is an AI seat."""
    monkeypatch.setattr(config, "AI_THINKING_DELAY_SECONDS", 0)
    monkeypatch.setattr(config, "HAND_RESULT_DISPLAY_SECONDS", 0.01)

    session = GameSession.new("Dylan")
    session.ai_players = {
        p.id: AlwaysFoldPlayer(p.id, p.name) for p in session.tournament.players if p.kind == "ai"
    }
    ws = FakeWebSocket()
    session.websockets.add(ws)
    session.start()

    for _ in range(500):
        await asyncio.sleep(0.01)
        if session.pending_human_action is not None and not session.pending_human_action.done():
            legal = session.tournament.current_hand.legal_actions()
            action = "fold" if legal.can_fold else "check_or_call"
            session.submit_human_action(action, None)
        if any(e["type"] == "hand_result" for e in ws.events):
            break

    session.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await session.task

    hand_results = [e for e in ws.events if e["type"] == "hand_result"]
    assert hand_results, "expected a hand_result event"
    assert hand_results[0]["winning_hand_label"] is None

    assert not any(e["type"] == "win_reaction" for e in ws.events)


@pytest.mark.asyncio
async def test_turn_or_river_fold_out_win_still_triggers_a_win_reaction(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fold-out win that made it to the turn or river is still worth a
    reaction, even without a hand category to cite (cards were never
    shown) -- only a preflop/flop walk stays silent."""
    monkeypatch.setattr(config, "AI_THINKING_DELAY_SECONDS", 0)
    monkeypatch.setattr(config, "HAND_RESULT_DISPLAY_SECONDS", 0.01)

    async def fake_synthesize(text: str, voice: str):
        return "fakebase64", 0.01

    monkeypatch.setattr(session_module, "synthesize", fake_synthesize)

    session = GameSession.new("Dylan")
    shared = {"bet": False}
    session.ai_players = {
        p.id: CallUntilTurnThenBetAndFoldPlayer(p.id, p.name, shared)
        for p in session.tournament.players
        if p.kind == "ai"
    }
    ws = FakeWebSocket()
    session.websockets.add(ws)
    session.start()

    for _ in range(1000):
        await asyncio.sleep(0.005)
        if session.pending_human_action is not None and not session.pending_human_action.done():
            hand = session.tournament.current_hand
            legal = hand.legal_actions()
            street = hand.street_index
            if street is not None and street >= 2:
                if not shared["bet"] and legal.can_bet_or_raise:
                    shared["bet"] = True
                    session.submit_human_action("bet_or_raise_to", legal.min_bet_to)
                elif legal.can_fold:
                    session.submit_human_action("fold", None)
                else:
                    session.submit_human_action("check_or_call", None)
            elif legal.can_check_or_call:
                session.submit_human_action("check_or_call", None)
            else:
                session.submit_human_action("fold", None)
        if any(e["type"] == "hand_result" for e in ws.events):
            break

    session.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await session.task

    hand_results = [e for e in ws.events if e["type"] == "hand_result"]
    assert hand_results, "expected a hand_result event"
    result = hand_results[0]
    assert result["winning_hand_label"] is None, "a fold-out never reaches a real showdown"
    assert len(result["winners"]) == 1
    winner_id = result["winners"][0]

    win_reactions = [e for e in ws.events if e["type"] == "win_reaction"]
    if winner_id == config.HUMAN_PLAYER_ID:
        assert win_reactions == [], "the human doesn't get an AI reaction call"
    else:
        assert len(win_reactions) == 1
        assert win_reactions[0]["player_id"] == winner_id
        assert win_reactions[0]["message"] == "Everyone folded, easy money."


@pytest.mark.asyncio
async def test_all_in_runout_reveals_streets_one_at_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """When an action closes betting with nobody left to decide anything (e.g.
    everyone still in the hand is all-in preflop), pokerkit deals the rest of
    the board in a single call. The client must never see that as one jump --
    each new street needs its own board_dealt broadcast, paced by
    BOARD_REVEAL_DELAY_SECONDS, ending at the full 5-card board."""
    monkeypatch.setattr(config, "AI_THINKING_DELAY_SECONDS", 0)
    monkeypatch.setattr(config, "BOARD_REVEAL_DELAY_SECONDS", 0.2)

    requested_sleeps: list[float] = []
    real_sleep = asyncio.sleep

    async def spying_sleep(delay: float, *args, **kwargs):
        requested_sleeps.append(delay)
        await real_sleep(min(delay, 0.01))

    monkeypatch.setattr(asyncio, "sleep", spying_sleep)

    session = GameSession.new("Dylan")
    session.ai_players = {
        p.id: AlwaysShoveAllInPlayer(p.id, p.name) for p in session.tournament.players if p.kind == "ai"
    }
    ws = FakeWebSocket()
    session.websockets.add(ws)
    session.start()

    for _ in range(500):
        await real_sleep(0.005)
        if session.pending_human_action is not None and not session.pending_human_action.done():
            legal = session.tournament.current_hand.legal_actions()
            if legal.can_bet_or_raise:
                session.submit_human_action("bet_or_raise_to", legal.max_bet_to)
            else:
                session.submit_human_action("check_or_call", None)
        if any(e["type"] == "hand_result" for e in ws.events):
            break

    # give the loop task a scheduling turn to actually reach (and record) the
    # staged board_dealt sleeps, same reasoning as the hand-result test above
    await real_sleep(0.05)

    session.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await session.task

    board_dealt_events = [e for e in ws.events if e["type"] == "board_dealt"]
    assert board_dealt_events, "expected the all-in runout to be staged"

    board_lengths = [len(e["board_cards"]) for e in board_dealt_events]
    assert board_lengths == sorted(board_lengths), "streets must be revealed in order"
    assert board_lengths[-1] == 5, "the staged runout must end at the full board"
    assert all(n in (3, 4, 5) for n in board_lengths), f"unexpected board sizes: {board_lengths}"

    # every board_dealt event (except possibly the very last, whose trailing
    # sleep may not have been scheduled yet if we caught the loop mid-hand)
    # was followed by the reveal delay
    reveal_sleeps = [d for d in requested_sleeps if d == pytest.approx(0.2)]
    assert len(reveal_sleeps) >= len(board_dealt_events) - 1

    # the *combined* sequence of board sizes across every broadcast (not just
    # board_dealt) must never skip a street -- no single event may jump the
    # board from one size straight to a later, non-adjacent size
    seen_sizes: list[int] = []
    for event in ws.events:
        if event["type"] == "player_action":
            hand = event["state"]["hand"]
            size = len(hand["board_cards"]) if hand else 0
        elif event["type"] == "board_dealt":
            size = len(event["board_cards"])
        else:
            continue
        if not seen_sizes or seen_sizes[-1] != size:
            seen_sizes.append(size)

    allowed_transitions = {(0, 3), (3, 4), (4, 5)}
    for before, after in zip(seen_sizes, seen_sizes[1:]):
        if after > before:
            assert (before, after) in allowed_transitions, (
                f"board jumped from {before} to {after} cards in one broadcast -- "
                f"full sequence was {seen_sizes}"
            )


def test_debug_session_uses_mock_players_regardless_of_configured_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-fake")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-fake")
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "sk-fake")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "sk-fake")
    monkeypatch.setattr(config, "XAI_API_KEY", "sk-fake")

    debug_session = GameSession.new("Dylan", debug=True)
    assert debug_session.is_debug is True
    for pid, _name in config.AI_SEATS:
        assert isinstance(debug_session.ai_players[pid], MockPlayer)

    # sanity check: the same keys DO produce a real provider on a normal
    # session, proving debug mode is what's actually forcing the mock here
    real_session = GameSession.new("Dylan", debug=False)
    assert isinstance(real_session.ai_players["claude"], AnthropicPlayer)


@pytest.mark.asyncio
async def test_debug_only_controls_reject_a_non_debug_session() -> None:
    session = GameSession.new("Dylan", debug=False)

    with pytest.raises(DebugOnlyError):
        session.set_forced_ai_action("fold")
    with pytest.raises(DebugOnlyError):
        session.set_always_show_hands(True)
    with pytest.raises(DebugOnlyError):
        session.set_forced_dialogue(True)
    with pytest.raises(DebugOnlyError):
        await session.force_end_round()


@pytest.mark.asyncio
async def test_forced_fold_makes_every_ai_seat_fold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "AI_THINKING_DELAY_SECONDS", 0)

    session = GameSession.new("Dylan", debug=True)
    session.set_forced_ai_action("fold")
    ws = FakeWebSocket()
    session.websockets.add(ws)
    session.start()

    for _ in range(500):
        await asyncio.sleep(0.005)
        if session.pending_human_action is not None and not session.pending_human_action.done():
            legal = session.tournament.current_hand.legal_actions()
            action = "check_or_call" if legal.can_check_or_call else "fold"
            session.submit_human_action(action, None)
        if any(e["type"] == "hand_result" for e in ws.events):
            break

    session.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await session.task

    ai_actions = [
        e for e in ws.events if e["type"] == "player_action" and e["player_id"] != session.human_player_id
    ]
    assert ai_actions, "expected at least one AI action"
    assert any(e["action"] == "fold" for e in ai_actions), "expected at least one forced fold"
    for e in ai_actions:
        # the lone legal exception: the big blind can't fold when nobody has
        # raised (nothing to fold to) -- it falls back to checking for free
        if e["action"] != "fold":
            assert e["action"] == "check_or_call" and e["call_amount"] == 0


@pytest.mark.asyncio
async def test_forced_all_in_makes_every_ai_seat_shove_or_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every forced-all-in AI either shoves (bet_or_raise_to) or, once it's
    already covered by an earlier shove and can't raise any further, calls --
    either way it should never fold or leave itself with anything left."""
    monkeypatch.setattr(config, "AI_THINKING_DELAY_SECONDS", 0)

    session = GameSession.new("Dylan", debug=True)
    session.set_forced_ai_action("all_in")
    ws = FakeWebSocket()
    session.websockets.add(ws)
    session.start()

    for _ in range(500):
        await asyncio.sleep(0.005)
        if session.pending_human_action is not None and not session.pending_human_action.done():
            legal = session.tournament.current_hand.legal_actions()
            action = "check_or_call" if legal.can_check_or_call else "fold"
            session.submit_human_action(action, None)
        if any(e["type"] == "hand_result" for e in ws.events):
            break

    session.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await session.task

    ai_actions = [
        e for e in ws.events if e["type"] == "player_action" and e["player_id"] != session.human_player_id
    ]
    assert ai_actions, "expected at least one AI action"
    for e in ai_actions:
        assert e["action"] in ("bet_or_raise_to", "check_or_call")


@pytest.mark.asyncio
async def test_always_show_hands_reveals_a_folded_seats_cards(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "AI_THINKING_DELAY_SECONDS", 0)

    session = GameSession.new("Dylan", debug=True)
    session.set_forced_ai_action("fold")
    session.set_always_show_hands(True)
    ws = FakeWebSocket()
    session.websockets.add(ws)
    session.start()

    for _ in range(500):
        await asyncio.sleep(0.005)
        if session.pending_human_action is not None and not session.pending_human_action.done():
            legal = session.tournament.current_hand.legal_actions()
            action = "check_or_call" if legal.can_check_or_call else "fold"
            session.submit_human_action(action, None)
        if any(e["type"] == "hand_result" for e in ws.events):
            break

    session.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await session.task

    player_actions = [e for e in ws.events if e["type"] == "player_action"]
    assert player_actions
    last_hand = player_actions[-1]["state"]["hand"]
    folded_seat = next(s for s in last_hand["seats"] if s["folded"])
    assert folded_seat["hole_cards"] is not None


@pytest.mark.asyncio
async def test_forced_dialogue_guarantees_a_message_on_every_ai_action(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deliberately doesn't combine this with set_forced_ai_action: a forced
    action mode overrides decide() outright (see _forced_action_result),
    never even calling into the MockPlayer that force_dialogue actually
    affects -- this needs MockPlayer's own (still randomized-action) decide()
    to run so its now-guaranteed dialogue has anything to attach to."""
    monkeypatch.setattr(config, "AI_THINKING_DELAY_SECONDS", 0)

    session = GameSession.new("Dylan", debug=True)
    session.set_forced_dialogue(True)
    ws = FakeWebSocket()
    session.websockets.add(ws)
    session.start()

    for _ in range(500):
        await asyncio.sleep(0.005)
        if session.pending_human_action is not None and not session.pending_human_action.done():
            legal = session.tournament.current_hand.legal_actions()
            action = "check_or_call" if legal.can_check_or_call else "fold"
            session.submit_human_action(action, None)
        if any(e["type"] == "hand_result" for e in ws.events):
            break

    session.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await session.task

    ai_actions = [
        e for e in ws.events if e["type"] == "player_action" and e["player_id"] != session.human_player_id
    ]
    assert ai_actions, "expected at least one AI action"
    for event in ai_actions:
        assert event["message"] is not None


@pytest.mark.asyncio
async def test_force_end_round_forfeits_the_hand_and_restarts_the_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "AI_THINKING_DELAY_SECONDS", 0)

    session = GameSession.new("Dylan", debug=True)
    session.set_forced_ai_action("call")  # keeps chips flowing into the pot
    ws = FakeWebSocket()
    session.websockets.add(ws)
    session.start()

    # give the loop a chance to actually deal into hand #1 -- force_end_round
    # should work regardless of exactly where mid-hand this lands
    for _ in range(200):
        await asyncio.sleep(0.005)
        if session.tournament.current_hand is not None:
            break
    assert session.tournament.current_hand is not None

    hand_count_before = session.tournament.hand_count
    await session.force_end_round()

    assert session.tournament.hand_count >= hand_count_before + 1
    assert session.task is not None, "the loop should have restarted itself for the next hand"
    hand_results = [e for e in ws.events if e["type"] == "hand_result"]
    assert hand_results, "expected the forfeited hand to be broadcast as a hand_result"
    assert hand_results[-1]["winners"] == []  # nobody is awarded a forfeited pot

    session.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await session.task


@pytest.mark.asyncio
async def test_force_end_round_is_a_noop_between_hands(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling end round when no hand is actually in progress (e.g. before
    the loop has even started, or during the post-result display pause)
    shouldn't fabricate a hand_result, but should still leave the loop able
    to keep going."""
    monkeypatch.setattr(config, "AI_THINKING_DELAY_SECONDS", 0)

    session = GameSession.new("Dylan", debug=True)
    assert session.tournament.current_hand is None  # no hand dealt yet at all
    ws = FakeWebSocket()
    session.websockets.add(ws)

    await session.force_end_round()

    assert ws.events == [], "nothing was in progress, so nothing should have been broadcast"
    assert session.task is not None, "the loop should have started for the first hand"

    session.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await session.task


class FakeHandForSoreLoser:
    """Duck-typed stand-in for engine.hand.Hand -- covers what
    _sore_loser_target reads, plus (for the broadcast test) everything
    engine.state.view_for_actor needs to build a prompt view. Lets these be
    tested directly against hand-crafted showdown scenarios instead of
    fighting real card RNG."""

    def __init__(self, seat_player_ids: list[str], folded_ids: set[str], revealed: dict[str, list[str]]):
        self.seat_player_ids = seat_player_ids
        self._folded_ids = folded_ids
        self._revealed = revealed
        self.board_cards = ["Ah", "2c", "9d", "Kh", "3s"]
        self.pot_total = 1000
        self.street_index = 3
        self.starting_stacks = dict.fromkeys(seat_player_ids, 10000)
        self.current_actor_id = None

    def is_folded(self, player_id: str) -> bool:
        return player_id in self._folded_ids

    def revealed_hole_cards(self) -> dict[str, list[str]]:
        return self._revealed

    def winning_hand_label(self, player_id: str) -> str:
        return "One pair"

    def hole_cards_of(self, player_id: str) -> list[str]:
        return self._revealed.get(player_id, ["??", "??"])

    def stack_of(self, player_id: str) -> int:
        return 5000

    def bet_of(self, player_id: str) -> int:
        return 0

    def legal_actions(self):
        from app.engine.hand import LegalActions

        return LegalActions(
            can_fold=False, can_check_or_call=False, can_bet_or_raise=False,
            call_amount=0, min_bet_to=None, max_bet_to=None,
        )


AI_ID = config.AI_SEATS[0][0]
OTHER_AI_ID = config.AI_SEATS[1][0]


def test_sore_loser_target_fires_when_ai_loses_heads_up_to_human_on_the_river() -> None:
    session = GameSession.new("Dylan", debug=True)
    hand = FakeHandForSoreLoser(
        seat_player_ids=[config.HUMAN_PLAYER_ID, AI_ID],
        folded_ids=set(),
        revealed={config.HUMAN_PLAYER_ID: ["Ah", "Kh"], AI_ID: ["2c", "7d"]},
    )
    net_results = {config.HUMAN_PLAYER_ID: 500, AI_ID: -500}

    target = session._sore_loser_target(hand, winners=[config.HUMAN_PLAYER_ID], net_results=net_results, board_len_at_end=5)

    assert target == AI_ID


def test_sore_loser_target_is_none_with_a_third_player_still_live() -> None:
    session = GameSession.new("Dylan", debug=True)
    hand = FakeHandForSoreLoser(
        seat_player_ids=[config.HUMAN_PLAYER_ID, AI_ID, OTHER_AI_ID],
        folded_ids=set(),
        revealed={config.HUMAN_PLAYER_ID: ["Ah", "Kh"], AI_ID: ["2c", "7d"], OTHER_AI_ID: ["3c", "8d"]},
    )
    net_results = {config.HUMAN_PLAYER_ID: 500, AI_ID: -250, OTHER_AI_ID: -250}

    target = session._sore_loser_target(hand, winners=[config.HUMAN_PLAYER_ID], net_results=net_results, board_len_at_end=5)

    assert target is None


def test_sore_loser_target_is_none_on_a_fold_out() -> None:
    session = GameSession.new("Dylan", debug=True)
    hand = FakeHandForSoreLoser(
        seat_player_ids=[config.HUMAN_PLAYER_ID, AI_ID],
        folded_ids={AI_ID},
        revealed={},
    )
    net_results = {config.HUMAN_PLAYER_ID: 500, AI_ID: -500}

    target = session._sore_loser_target(hand, winners=[config.HUMAN_PLAYER_ID], net_results=net_results, board_len_at_end=5)

    assert target is None


def test_sore_loser_target_is_none_when_it_never_reached_the_turn() -> None:
    session = GameSession.new("Dylan", debug=True)
    hand = FakeHandForSoreLoser(
        seat_player_ids=[config.HUMAN_PLAYER_ID, AI_ID],
        folded_ids=set(),
        revealed={config.HUMAN_PLAYER_ID: ["Ah", "Kh"], AI_ID: ["2c", "7d"]},
    )
    net_results = {config.HUMAN_PLAYER_ID: 500, AI_ID: -500}

    target = session._sore_loser_target(hand, winners=[config.HUMAN_PLAYER_ID], net_results=net_results, board_len_at_end=3)

    assert target is None


def test_sore_loser_target_is_none_when_the_ai_actually_won() -> None:
    session = GameSession.new("Dylan", debug=True)
    hand = FakeHandForSoreLoser(
        seat_player_ids=[config.HUMAN_PLAYER_ID, AI_ID],
        folded_ids=set(),
        revealed={config.HUMAN_PLAYER_ID: ["2c", "7d"], AI_ID: ["Ah", "Kh"]},
    )
    net_results = {config.HUMAN_PLAYER_ID: -500, AI_ID: 500}

    target = session._sore_loser_target(hand, winners=[AI_ID], net_results=net_results, board_len_at_end=5)

    assert target is None


def test_sore_loser_target_is_none_on_a_chopped_pot() -> None:
    session = GameSession.new("Dylan", debug=True)
    hand = FakeHandForSoreLoser(
        seat_player_ids=[config.HUMAN_PLAYER_ID, AI_ID],
        folded_ids=set(),
        revealed={config.HUMAN_PLAYER_ID: ["Ah", "Kh"], AI_ID: ["Ac", "Kc"]},
    )
    net_results = {config.HUMAN_PLAYER_ID: 0, AI_ID: 0}

    target = session._sore_loser_target(hand, winners=[], net_results=net_results, board_len_at_end=5)

    assert target is None


def test_sore_loser_target_is_none_when_the_ai_mucked_without_showing() -> None:
    session = GameSession.new("Dylan", debug=True)
    hand = FakeHandForSoreLoser(
        seat_player_ids=[config.HUMAN_PLAYER_ID, AI_ID],
        folded_ids=set(),
        revealed={config.HUMAN_PLAYER_ID: ["Ah", "Kh"]},  # AI mucked face down, never shown
    )
    net_results = {config.HUMAN_PLAYER_ID: 500, AI_ID: -500}

    target = session._sore_loser_target(hand, winners=[config.HUMAN_PLAYER_ID], net_results=net_results, board_len_at_end=5)

    assert target is None


@pytest.mark.asyncio
async def test_broadcast_loss_reaction_fires_and_returns_pacing_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "AUDIO_TRAILING_DELAY_SECONDS", 0.1)

    async def fake_synthesize(text: str, voice: str):
        return "fakebase64", 0.02

    monkeypatch.setattr(session_module, "synthesize", fake_synthesize)

    session = GameSession.new("Dylan", debug=True)
    session.ai_players[AI_ID] = AlwaysShoveAllInPlayer(AI_ID, "Claude")
    ws = FakeWebSocket()
    session.websockets.add(ws)

    hand = FakeHandForSoreLoser(
        seat_player_ids=[config.HUMAN_PLAYER_ID, AI_ID],
        folded_ids=set(),
        revealed={config.HUMAN_PLAYER_ID: ["Ah", "Kh"], AI_ID: ["2c", "7d"]},
    )
    net_results = {config.HUMAN_PLAYER_ID: 500, AI_ID: -500}

    wait = await session._broadcast_loss_reaction(
        hand, winners=[config.HUMAN_PLAYER_ID], net_results=net_results, board_len_at_end=5
    )

    assert wait == pytest.approx(0.12)
    loss_reactions = [e for e in ws.events if e["type"] == "loss_reaction"]
    assert len(loss_reactions) == 1
    assert loss_reactions[0]["player_id"] == AI_ID
    assert loss_reactions[0]["message"] == "Losing with One pair? Rigged."
    assert loss_reactions[0]["audio_base64"] == "fakebase64"


class ViewCapturingLossPlayer:
    """Records the `view` it's asked to react to, so a test can inspect what
    the sore-loser reaction call actually saw (e.g. whether the human's
    revealed cards were threaded through) without depending on message text."""

    def __init__(self, player_id: str, display_name: str):
        self.player_id = player_id
        self.display_name = display_name
        self.seen_views: list[dict] = []

    async def decide(self, view: dict) -> ActionResult:
        return ActionResult(action="fold")

    async def react_to_win(self, view: dict, hand_label: str | None, amount_won: int) -> str | None:
        return None

    async def react_to_loss(self, view: dict, hand_label: str, amount_lost: int) -> str | None:
        self.seen_views.append(view)
        return "rigged"


@pytest.mark.asyncio
async def test_broadcast_loss_reaction_shares_the_humans_revealed_hand_with_the_bot() -> None:
    session = GameSession.new("Dylan", debug=True)
    capturing_player = ViewCapturingLossPlayer(AI_ID, "Claude")
    session.ai_players[AI_ID] = capturing_player
    ws = FakeWebSocket()
    session.websockets.add(ws)

    hand = FakeHandForSoreLoser(
        seat_player_ids=[config.HUMAN_PLAYER_ID, AI_ID],
        folded_ids=set(),
        revealed={config.HUMAN_PLAYER_ID: ["Ah", "Kh"], AI_ID: ["2c", "7d"]},
    )
    net_results = {config.HUMAN_PLAYER_ID: 500, AI_ID: -500}

    await session._broadcast_loss_reaction(
        hand, winners=[config.HUMAN_PLAYER_ID], net_results=net_results, board_len_at_end=5
    )

    assert len(capturing_player.seen_views) == 1
    assert capturing_player.seen_views[0]["opponent_hole_cards"] == ["Ah", "Kh"]
