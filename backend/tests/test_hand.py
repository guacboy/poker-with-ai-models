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
