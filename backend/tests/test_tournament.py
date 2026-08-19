from __future__ import annotations

import pytest

from app import rules
from app.ai.mock_player import MockPlayer
from app.engine import state as state_mod
from app.engine.tournament import PlayerStatus, Tournament


def make_tournament() -> Tournament:
    specs = [(f"p{i}", f"Player{i}", "ai") for i in range(rules.NUM_SEATS)]
    return Tournament.new(specs)


async def play_one_hand(t: Tournament, players: dict[str, MockPlayer]) -> None:
    hand = t.start_hand()
    while not hand.is_over:
        actor_id = hand.current_actor_id
        view = state_mod.view_for_actor(t, hand, actor_id)
        result = await players[actor_id].decide(view)
        t.apply_action(actor_id, result.action, result.amount)
    t.finish_hand()


def test_new_tournament_has_correct_seats_and_stacks():
    t = make_tournament()
    assert len(t.players) == rules.NUM_SEATS
    assert all(p.stack == rules.STARTING_STACK for p in t.players)
    assert all(p.status is PlayerStatus.ACTIVE for p in t.players)
    assert all(p.buy_ins_used == 1 for p in t.players)
    assert t.blinds == rules.BLIND_SCHEDULE[0]
    assert not t.is_over


@pytest.mark.asyncio
async def test_blind_level_advances_every_n_hands():
    t = make_tournament()
    players = {p.id: MockPlayer(p.id, p.name, seed=i) for i, p in enumerate(t.players)}

    for _ in range(rules.HANDS_PER_BLIND_LEVEL - 1):
        await play_one_hand(t, players)
    assert t.blind_level == 0

    await play_one_hand(t, players)
    assert t.hand_count == rules.HANDS_PER_BLIND_LEVEL
    assert t.blind_level == 1
    assert t.blinds == rules.BLIND_SCHEDULE[1]


def test_rebuy_up_to_max_then_eliminated():
    t = make_tournament()
    player_id = t.players[0].id

    for expected_buy_ins_used in range(2, rules.MAX_BUY_INS + 1):
        t.player(player_id).stack = 0
        t._handle_bust(player_id)
        assert t.player(player_id).status is PlayerStatus.ACTIVE
        assert t.player(player_id).buy_ins_used == expected_buy_ins_used
        assert t.player(player_id).stack == rules.STARTING_STACK

    # one more bust exceeds MAX_BUY_INS -> eliminated, stack stays at 0
    t.player(player_id).stack = 0
    t._handle_bust(player_id)
    assert t.player(player_id).status is PlayerStatus.ELIMINATED
    assert t.player(player_id).buy_ins_remaining == 0


def test_is_over_and_winner_when_one_player_remains():
    t = make_tournament()
    for p in t.players[1:]:
        p.status = PlayerStatus.ELIMINATED

    assert t.is_over
    assert t.winner is not None
    assert t.winner.id == t.players[0].id


@pytest.mark.asyncio
async def test_full_headless_tournament_terminates_with_one_winner():
    t = make_tournament()
    players = {p.id: MockPlayer(p.id, p.name, seed=i) for i, p in enumerate(t.players)}

    hands_played = 0
    max_hands = 3000
    while not t.is_over and hands_played < max_hands:
        await play_one_hand(t, players)
        hands_played += 1

    assert t.is_over, f"tournament did not terminate within {max_hands} hands"
    active = t.active_players()
    assert len(active) == 1
    assert t.winner is not None
    assert t.winner.id == active[0].id

    # nobody should have exceeded the max buy-in count
    for p in t.players:
        assert p.buy_ins_used <= rules.MAX_BUY_INS
        if p.status is PlayerStatus.ELIMINATED:
            assert p.buy_ins_used == rules.MAX_BUY_INS
