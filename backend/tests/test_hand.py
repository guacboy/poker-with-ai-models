"""Engine-level coverage for what gets revealed at the end of a hand: a real
showdown should only reveal the cards of whoever could still win the pot, and
a hand won by everyone else folding should reveal nothing at all -- this is
what lets the frontend glow the winning hand's cards without leaking cards
from a fold-out win. See app.engine.hand.Hand.revealed_hole_cards.
"""

from __future__ import annotations

from app import rules
from app.engine.tournament import Tournament


def make_tournament() -> Tournament:
    specs = [(f"p{i}", f"Player{i}", "ai") for i in range(rules.NUM_SEATS)]
    return Tournament.new(specs)


def test_showdown_reveals_hole_cards_only_for_winners():
    t = make_tournament()
    hand = t.start_hand()

    # nobody folds -- forces every street to run out to a real showdown,
    # regardless of what the random deck deals
    while not hand.is_over:
        actor_id = hand.current_actor_id
        legal = hand.legal_actions()
        action = "check_or_call" if legal.can_check_or_call else "fold"
        t.apply_action(actor_id, action)

    winners = {pid for pid, net in hand.net_results().items() if net > 0}
    revealed = hand.revealed_hole_cards()

    assert winners, "expected at least one winner"
    assert winners <= revealed.keys(), "every winner must have shown their hand to claim the pot"


def test_fold_out_win_reveals_no_hole_cards():
    t = make_tournament()
    hand = t.start_hand()

    # everyone folds whenever they're allowed to, so the hand ends the moment
    # only one player is left -- no showdown ever happens
    while not hand.is_over:
        actor_id = hand.current_actor_id
        legal = hand.legal_actions()
        action = "fold" if legal.can_fold else "check_or_call"
        t.apply_action(actor_id, action)

    winners = {pid for pid, net in hand.net_results().items() if net > 0}
    assert len(winners) == 1, "a fold-out always has exactly one winner"
    assert hand.revealed_hole_cards() == {}


def test_dealt_hole_cards_of_survives_folding():
    """pokerkit clears a player's hole_cards from its own state the instant
    they fold (mucking) -- hole_cards_of documents that, but a viewer should
    still be able to see their OWN folded hand, which is what
    dealt_hole_cards_of is for."""
    t = make_tournament()
    hand = t.start_hand()
    folded_pid = hand.current_actor_id

    original = hand.dealt_hole_cards_of(folded_pid)
    assert len(original) == 2

    t.apply_action(folded_pid, "fold")

    assert hand.hole_cards_of(folded_pid) == [], "pokerkit mucks a folded player's cards"
    assert hand.dealt_hole_cards_of(folded_pid) == original, "but the dealt snapshot must be unaffected"


def test_dealt_hole_cards_of_survives_hand_completion():
    """At the end of a hand, pokerkit also mucks (clears) the hole cards of
    anyone left unshown -- e.g. a player who reached showdown but couldn't
    beat what was already shown. dealt_hole_cards_of must still return their
    real hand after the fact, for every seat, not just the winner."""
    t = make_tournament()
    hand = t.start_hand()
    all_seats = list(hand.seat_player_ids)
    dealt_before = {pid: hand.dealt_hole_cards_of(pid) for pid in all_seats}

    while not hand.is_over:
        actor_id = hand.current_actor_id
        legal = hand.legal_actions()
        action = "check_or_call" if legal.can_check_or_call else "fold"
        t.apply_action(actor_id, action)

    for pid in all_seats:
        assert hand.dealt_hole_cards_of(pid) == dealt_before[pid]
        assert len(hand.dealt_hole_cards_of(pid)) == 2


def test_is_folded_reflects_only_real_folds_not_showdown_mucking():
    """pokerkit flips the same live status flag folding uses when it mucks a
    losing hand at the end of an all-in showdown -- and does it the instant
    the closing action applies, before any remaining board even gets shown.
    is_folded must not pick that up as a fold, or the frontend dims out the
    losers (and thus spoils who won) as soon as the runout starts, long
    before the river is actually revealed."""
    t = make_tournament()
    hand = t.start_hand()

    # nobody folds -- forces a real showdown among everyone, so any seat
    # coming back is_folded=True afterwards would only be from mucking
    while not hand.is_over:
        actor_id = hand.current_actor_id
        legal = hand.legal_actions()
        action = "check_or_call" if legal.can_check_or_call else "fold"
        t.apply_action(actor_id, action)

    for pid in hand.seat_player_ids:
        assert not hand.is_folded(pid), f"{pid} never folded but is_folded() says otherwise"


def test_is_folded_still_true_for_actual_folds():
    t = make_tournament()
    hand = t.start_hand()
    folded_ids = set()

    while not hand.is_over:
        actor_id = hand.current_actor_id
        legal = hand.legal_actions()
        if legal.can_fold:
            t.apply_action(actor_id, "fold")
            folded_ids.add(actor_id)
        else:
            t.apply_action(actor_id, "check_or_call")

    assert folded_ids, "expected at least one real fold in this hand"
    for pid in hand.seat_player_ids:
        assert hand.is_folded(pid) == (pid in folded_ids)
