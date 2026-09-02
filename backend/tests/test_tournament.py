from __future__ import annotations

import pytest

from app import rules
from app.ai.mock_player import MockPlayer
from app.engine import state as state_mod
from app.engine.tournament import ActionError, PlayerStatus, Tournament


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
    assert t.blinds == rules.blinds_for_level(0)
    assert not t.is_over


def _play_and_forfeit_hand(t: Tournament) -> None:
    """Drives the button/orbit/blind-level machinery deterministically,
    without depending on MockPlayer's randomness (or risking a bust changing
    who's still active mid-test) -- only blinds get posted before the hand is
    immediately forfeited."""
    t.start_hand()
    t.forfeit_current_hand()


def test_blind_level_advances_every_orbit():
    t = make_tournament()

    # button_index starts at 0 and increments by 1/hand regardless of table
    # size, so a repeat isn't detected until the button wraps back around --
    # the very first orbit (starting from an empty seen-set) takes
    # NUM_SEATS + 1 hands to register. Nobody busts here, so every seat's
    # original occupant keeps holding the button in turn. At
    # ORBITS_PER_BLIND_LEVEL == 1, that single completed orbit is itself the
    # blind-level bump.
    assert rules.ORBITS_PER_BLIND_LEVEL == 1, "this test assumes one orbit per level"
    hands_for_one_orbit = rules.NUM_SEATS + 1
    for _ in range(hands_for_one_orbit - 1):
        _play_and_forfeit_hand(t)
    assert t.blind_level == 0

    _play_and_forfeit_hand(t)
    assert t.hand_count == hands_for_one_orbit
    assert t.blind_level == 1
    assert t.blinds == rules.blinds_for_level(1)


def test_orbit_completes_when_button_returns_to_a_repeat_holder():
    t = make_tournament()
    assert rules.ORBITS_PER_BLIND_LEVEL == 1, "this test assumes one orbit per level"
    assert t.orbits_until_next_level == rules.ORBITS_PER_BLIND_LEVEL

    # walk the button around the full table once -- everyone gets a first,
    # distinct turn, so no repeat yet (see the note above on the +1)
    for _ in range(rules.NUM_SEATS):
        _play_and_forfeit_hand(t)
    assert t.orbits_completed_this_level == 0
    assert t.blind_level == 0

    # the next hand's button wraps back to whoever held it first -- orbit
    # done, and since a single orbit is the whole level here, that same hand
    # both completes the orbit and immediately advances the blind level (the
    # orbit counter resets back to 0 for the new level, re-seeded with the
    # repeat holder rather than starting empty)
    _play_and_forfeit_hand(t)
    assert t.orbits_completed_this_level == 0
    assert t.orbits_until_next_level == rules.ORBITS_PER_BLIND_LEVEL
    assert t.blind_level == 1


def test_orbit_length_shrinks_as_players_bust():
    t = make_tournament()
    assert rules.ORBITS_PER_BLIND_LEVEL == 1, "this test assumes one orbit per level"
    # eliminate everyone except two seats so an orbit completes much faster
    # than a full table would need
    for p in t.players[2:]:
        p.status = PlayerStatus.ELIMINATED

    for _ in range(rules.NUM_SEATS - 2):
        _play_and_forfeit_hand(t)
    # with only 2 active seats, an orbit is just 2 hands (once seeded) -- far
    # fewer than NUM_SEATS - 2 hands, so at least one has already completed.
    # At ORBITS_PER_BLIND_LEVEL == 1 that immediately resets
    # orbits_completed_this_level back to 0 and bumps the blind level, so the
    # blind level (not the orbit counter) is the observable signal here --
    # same reasoning as test_orbit_completes_when_button_returns_to_a_repeat_holder.
    assert t.blind_level >= 1


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


def test_forfeit_current_hand_is_a_noop_with_no_hand_in_progress():
    t = make_tournament()
    assert t.forfeit_current_hand() == {}


def test_forfeit_current_hand_ends_the_hand_and_keeps_committed_chips_forfeited():
    t = make_tournament()
    hand = t.start_hand()
    actor_id = hand.current_actor_id
    stack_before_hand = t.player(actor_id).stack

    # the actor calls, putting chips in the pot -- those chips must NOT come
    # back to them once the hand is forfeited, unlike a normal fold
    t.apply_action(actor_id, "check_or_call")
    live_stack_after_call = hand.stack_of(actor_id)
    assert live_stack_after_call < stack_before_hand

    net_results = t.forfeit_current_hand()

    assert t.current_hand is None
    assert t.player(actor_id).stack == live_stack_after_call
    assert net_results[actor_id] == live_stack_after_call - stack_before_hand
    # bookkeeping still ran, same as a normal finish_hand
    assert t.hand_count == 1


def test_forfeit_current_hand_can_trigger_a_bust():
    t = make_tournament()
    hand = t.start_hand()
    actor_id = hand.current_actor_id

    # first-to-act preflop always has the option to shove their entire stack
    legal = hand.legal_actions()
    assert legal.can_bet_or_raise
    t.apply_action(actor_id, "bet_or_raise_to", legal.max_bet_to)
    assert hand.stack_of(actor_id) == 0

    t.forfeit_current_hand()

    assert t.player(actor_id).buy_ins_used == 2  # rebought
    assert t.player(actor_id).stack == rules.STARTING_STACK


def test_view_public_reveal_all_shows_every_hole_card_regardless_of_status():
    """Backs the debug "always show hands" control: with reveal_all=True,
    even a folded/un-shown seat's dealt hole cards should be visible to a
    viewer who normally wouldn't see them at all."""
    t = make_tournament()
    hand = t.start_hand()
    folded_id = hand.current_actor_id
    other_id = next(pid for pid in hand.seat_player_ids if pid != folded_id)
    dealt = hand.dealt_hole_cards_of(folded_id)

    t.apply_action(folded_id, "fold")

    normal_view = state_mod.view_public(t, hand, other_id)
    normal_seat = next(s for s in normal_view["hand"]["seats"] if s["player_id"] == folded_id)
    assert normal_seat["hole_cards"] is None  # hidden, as usual

    debug_view = state_mod.view_public(t, hand, other_id, reveal_all=True)
    debug_seat = next(s for s in debug_view["hand"]["seats"] if s["player_id"] == folded_id)
    assert debug_seat["hole_cards"] == dealt


def test_voluntarily_invested_flag_tracks_real_contributions_beyond_blinds():
    """Backs the fold-talk-eligibility chore: a seat's `voluntarily_invested`
    should only flip true once that player has actually put chips in beyond
    a forced blind post (a real call/raise), not merely for posting or
    checking their own blind."""
    t = make_tournament()
    hand = t.start_hand()

    def seat(pid: str) -> dict:
        view = state_mod.view_public(t, hand, None)
        return next(s for s in view["hand"]["seats"] if s["player_id"] == pid)

    sb_id = hand.seat_player_ids[0]
    bb_id = hand.seat_player_ids[1]
    utg_id = hand.current_actor_id  # first to act preflop, acts before either blind

    assert seat(sb_id)["voluntarily_invested"] is False
    assert seat(bb_id)["voluntarily_invested"] is False
    assert seat(utg_id)["voluntarily_invested"] is False

    # UTG limps in (calls the unraised big blind) -- a real voluntary call
    t.apply_action(utg_id, "check_or_call")
    assert seat(utg_id)["voluntarily_invested"] is True

    # fold everyone else around to the blinds
    while hand.current_actor_id not in (sb_id, bb_id):
        t.apply_action(hand.current_actor_id, "fold")

    # SB completes to match the big blind -- also a real voluntary call
    assert seat(sb_id)["voluntarily_invested"] is False
    t.apply_action(sb_id, "check_or_call")
    assert seat(sb_id)["voluntarily_invested"] is True

    # BB checks their option for free -- not a voluntary investment
    t.apply_action(bb_id, "check_or_call")
    assert seat(bb_id)["voluntarily_invested"] is False


def test_validate_action_rejects_out_of_turn_action():
    t = make_tournament()
    hand = t.start_hand()
    actor_id = hand.current_actor_id
    other_id = next(p.id for p in t.players if p.id != actor_id)

    with pytest.raises(ActionError):
        t.validate_action(other_id, "fold")

    # validation alone must not mutate the hand
    assert hand.current_actor_id == actor_id
    assert not hand.is_folded(actor_id)


def test_validate_action_rejects_out_of_range_raise():
    t = make_tournament()
    hand = t.start_hand()
    actor_id = hand.current_actor_id
    legal = hand.legal_actions()

    with pytest.raises(ActionError):
        t.validate_action(actor_id, "bet_or_raise_to", legal.max_bet_to + 1)

    with pytest.raises(ActionError):
        t.validate_action(actor_id, "bet_or_raise_to", legal.min_bet_to - 1)

    # still their turn, still legal to actually raise within range afterwards
    assert hand.current_actor_id == actor_id
    t.apply_action(actor_id, "bet_or_raise_to", legal.min_bet_to)
    assert hand.current_actor_id != actor_id


def test_apply_action_raises_and_does_not_mutate_on_illegal_input():
    t = make_tournament()
    hand = t.start_hand()
    actor_id = hand.current_actor_id
    stack_before = hand.stack_of(actor_id)

    with pytest.raises(ActionError):
        t.apply_action(actor_id, "bet_or_raise_to", amount=None)

    assert hand.current_actor_id == actor_id
    assert hand.stack_of(actor_id) == stack_before


def test_view_public_shows_viewers_own_cards_even_after_they_fold():
    """A broadcast is always built with viewer_id set to the human -- they
    should keep seeing their own hole cards for the rest of the hand (and
    into the post-hand freeze-frame) even after folding, not just up until
    the moment they mucked."""
    t = make_tournament()
    hand = t.start_hand()
    viewer_id = hand.current_actor_id

    dealt = hand.dealt_hole_cards_of(viewer_id)
    t.apply_action(viewer_id, "fold")

    view = state_mod.view_public(t, hand, viewer_id)
    viewer_seat = next(s for s in view["hand"]["seats"] if s["player_id"] == viewer_id)
    assert viewer_seat["hole_cards"] == dealt


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
