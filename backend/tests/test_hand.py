"""Engine-level coverage for what gets revealed at the end of a hand: a real
showdown should only reveal the cards of whoever could still win the pot, and
a hand won by everyone else folding should reveal nothing at all -- this is
what lets the frontend glow the winning hand's cards without leaking cards
from a fold-out win. See app.engine.hand.Hand.revealed_hole_cards.
"""

from __future__ import annotations

from pokerkit import Automation, NoLimitTexasHoldem

from app import rules
from app.engine.hand import Hand
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


def test_winning_hand_label_is_a_real_category_at_showdown():
    t = make_tournament()
    hand = t.start_hand()

    # nobody folds -- forces a real showdown, regardless of what's dealt
    while not hand.is_over:
        actor_id = hand.current_actor_id
        legal = hand.legal_actions()
        action = "check_or_call" if legal.can_check_or_call else "fold"
        t.apply_action(actor_id, action)

    winner_id = next(pid for pid, net in hand.net_results().items() if net > 0)
    label = hand.winning_hand_label(winner_id)

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
    assert label in valid_labels


# Fixed, deterministic burn cards for _showdown_state below -- picked to
# never collide with any hole/board card any test actually deals. Automation
# would otherwise burn a RANDOM card from the deck before each street, which
# can (and did) coincidentally collide with a card a test deals explicitly
# later, corrupting the deck and silently knocking a player out of the hand.
_BURN_CARDS = ("8c", "8d", "8h")


def _showdown_state(hole0: str, hole1: str, flop: str, turn: str, river: str):
    """Deals a fully controlled 2-player hand straight to showdown (bypassing
    Hand.start, which can't force exact cards), checking through every
    street. Used to pin down exactly which cards winning_hand_label/
    winning_hand_cards should report for a specific, known board/hole
    combination. Card burning is done manually with _BURN_CARDS rather than
    left to Automation.CARD_BURNING, so nothing here depends on which random
    card the deck happens to burn (see _BURN_CARDS)."""
    automations = (
        Automation.ANTE_POSTING,
        Automation.BET_COLLECTION,
        Automation.BLIND_OR_STRADDLE_POSTING,
        Automation.HOLE_CARDS_SHOWING_OR_MUCKING,
        Automation.HAND_KILLING,
        Automation.CHIPS_PUSHING,
        Automation.CHIPS_PULLING,
    )
    state = NoLimitTexasHoldem.create_state(automations, True, 0, (50, 100), 100, (10000, 10000), 2)
    state.deal_hole(hole0)
    state.deal_hole(hole1)
    state.check_or_call()  # SB completes
    state.check_or_call()  # BB checks
    for board, burn in zip((flop, turn, river), _BURN_CARDS):
        state.burn_card(burn)
        state.deal_board(board)
        state.check_or_call()
        state.check_or_call()
    assert not state.status, "hand should be fully over"
    return state


def test_winning_hand_label_reports_high_card_the_same_as_any_other_category():
    """"High card" is a real pokerkit label like any other -- not a special
    case that reads as "no hand"/falsy anywhere in the label pipeline. Deals
    a fully controlled, unpaired, unconnected board to force an actual
    high-card showdown and confirm the label comes back as the literal
    string, the same way every other category already does in
    test_winning_hand_label_is_a_real_category_at_showdown."""
    state = _showdown_state("AsKd", "QcJh", "2h6s9c", "3d", "7c")  # unpaired, no straight/flush possible
    hand = state.get_hand(0, 0, 0)
    assert hand is not None
    assert hand.entry.label.value == "High card"


def test_winning_hand_cards_reports_all_5_cards_for_a_no_kicker_category():
    """Straight/flush/full house/straight flush already use all 5 cards as
    the pattern itself -- there's no separate kicker to trim out. Deals a
    controlled wheel straight flush so the exact expected cards are known."""
    state = _showdown_state("AsKs", "QcJh", "2s3s4s", "5s", "9d")  # As + 2s3s4s5s
    hand = Hand(state, ["p0", "p1"], {"p0": 10000, "p1": 10000})

    assert hand.winning_hand_label("p0") == "Straight flush"
    assert set(hand.winning_hand_cards("p0")) == {"As", "2s", "3s", "4s", "5s"}


def test_winning_hand_cards_excludes_kickers_unrelated_to_the_pair():
    """A pair made with one hole card + one board card should only report
    that one board card -- not also whichever other board cards happened to
    be the best available kickers to round out the 5-card comparison hand.
    Board is Ah/9s/7c/Th/2d: p0's pair of aces (As + Ah) picks up Kd/Th/9s as
    kickers (the top 3 remaining cards) in pokerkit's raw 5-card hand, but
    only Ah actually made the pair -- Th and 9s never should have lit up.
    p1's 4d/5d never pairs or connects into anything with this board, so
    p0's pair wins outright (needed for get_hand to still evaluate p0 at
    all -- pokerkit stops treating the loser of a showdown as "in
    contention" once the hand's over, same as a folded player)."""
    state = _showdown_state("AsKd", "4d5d", "Ah9s7c", "Th", "2d")
    hand = Hand(state, ["p0", "p1"], {"p0": 10000, "p1": 10000})

    assert hand.winning_hand_label("p0") == "One pair"
    # sanity check on the premise: pokerkit's raw best-hand really does pull
    # in Th/9s as kickers, so this is genuinely testing the trim-down and not
    # a hand where they'd never have been candidates in the first place
    raw_hand = state.get_hand(0, 0, 0)
    raw_cards = {repr(c) for c in raw_hand.cards}
    assert raw_cards == {"As", "Ah", "Kd", "9s", "Th"}, f"unexpected raw best hand: {raw_cards}"

    assert set(hand.winning_hand_cards("p0")) == {"As", "Ah"}


def _hand_via_apply(hole0: str, hole1: str, flop: str, turn: str, river: str, *, river_aggressor: int) -> Hand:
    """Builds a 2-player hand by driving it through Hand's own apply_fold/
    apply_check_or_call/apply_bet_or_raise_to (not raw pokerkit calls like
    _showdown_state above), so this exercises Hand's actual showdown-reveal
    behavior end to end. `river_aggressor` (0 or 1) is the seat that bets the
    river -- pokerkit's own default automation only shows a showdown
    participant's cards if they still have a chance to win, so putting the
    winner in that seat and the loser in the other reproduces exactly the
    scenario where pokerkit would otherwise muck the loser's hand silently,
    without ever revealing it."""
    automations = (
        Automation.ANTE_POSTING,
        Automation.BET_COLLECTION,
        Automation.BLIND_OR_STRADDLE_POSTING,
        Automation.HAND_KILLING,
        Automation.CHIPS_PUSHING,
        Automation.CHIPS_PULLING,
    )
    state = NoLimitTexasHoldem.create_state(automations, True, 0, (50, 100), 100, (10000, 10000), 2)
    state.deal_hole(hole0)
    state.deal_hole(hole1)
    hand = Hand(state, ["p0", "p1"], {"p0": 10000, "p1": 10000})
    hand.apply_check_or_call()  # SB completes
    hand.apply_check_or_call()  # BB checks
    for board, burn in zip((flop, turn, river), _BURN_CARDS):
        state.burn_card(burn)
        state.deal_board(board)
        if board == river:
            while state.actor_index is not None:
                if state.actor_index == river_aggressor:
                    hand.apply_bet_or_raise_to(500)
                else:
                    hand.apply_check_or_call()
        else:
            hand.apply_check_or_call()
            hand.apply_check_or_call()
    assert not state.status, "hand should be fully over"
    return hand


def test_showdown_loser_hand_is_revealed_even_when_pokerkit_would_muck_it_silently():
    """Regression test: pokerkit's own show-or-muck automation only reveals a
    showdown participant's cards if they still have a chance to win the pot
    (or it's an all-in) -- an outright loser who isn't first in showdown
    order (i.e. not the hand's last aggressor) mucks WITHOUT ever showing.
    Here p1 (river aggressor, big pair) wins and shows first; p0 (caller,
    garbage hand) has no chance to win and would normally muck silently.
    Hand._force_full_showdown_reveal exists specifically so this doesn't
    happen -- both revealed_hole_cards and winning_hand_label/
    winning_hand_cards must still work for p0 despite the loss."""
    hand = _hand_via_apply("2c7d", "AsAh", "Kd9s4h", "Qc", "Jh", river_aggressor=1)

    assert hand.revealed_hole_cards() == {"p0": ["2c", "7d"], "p1": ["As", "Ah"]}
    assert hand.winning_hand_label("p0") == "High card"
    assert hand.winning_hand_cards("p0") == ["Kd"]
    assert hand.net_results()["p0"] < 0


def test_winning_hand_cards_is_none_for_a_player_no_longer_in_contention():
    t = make_tournament()
    hand = t.start_hand()
    folded_pid = hand.current_actor_id
    t.apply_action(folded_pid, "fold")

    assert hand.winning_hand_cards(folded_pid) is None


def test_winning_hand_label_is_none_for_a_player_no_longer_in_contention():
    t = make_tournament()
    hand = t.start_hand()
    folded_pid = hand.current_actor_id
    t.apply_action(folded_pid, "fold")

    assert hand.winning_hand_label(folded_pid) is None


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
