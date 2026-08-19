from __future__ import annotations

from app.ai.base import is_talk_eligible


def make_view(
    *, street_index: int, call_amount: int, own_bet: int, big_blind: int = 100, voluntarily_invested: bool = False
) -> dict:
    return {
        "your_player_id": "hero",
        "street_index": street_index,
        "big_blind": big_blind,
        "seats": [{"player_id": "hero", "bet": own_bet, "voluntarily_invested": voluntarily_invested}],
        "legal_actions": {"call_amount": call_amount},
    }


def test_preflop_fold_with_no_prior_investment_is_not_talk_eligible() -> None:
    # e.g. UTG folding to an unraised big blind, or to someone else's raise,
    # having never put in anything beyond (at most) a forced blind themselves
    view = make_view(street_index=0, call_amount=100, own_bet=0, voluntarily_invested=False)
    assert is_talk_eligible("fold", view) is False


def test_flop_fold_with_no_prior_investment_is_not_talk_eligible() -> None:
    view = make_view(street_index=1, call_amount=50, own_bet=0, voluntarily_invested=False)
    assert is_talk_eligible("fold", view) is False


def test_preflop_fold_after_having_voluntarily_invested_is_talk_eligible() -> None:
    # e.g. hero limped in (or raised) earlier this hand, then gives up to a
    # later raise -- that's a real decision to react to
    view = make_view(street_index=0, call_amount=200, own_bet=0, voluntarily_invested=True)
    assert is_talk_eligible("fold", view) is True


def test_flop_fold_after_having_voluntarily_invested_is_talk_eligible() -> None:
    view = make_view(street_index=1, call_amount=50, own_bet=0, voluntarily_invested=True)
    assert is_talk_eligible("fold", view) is True


def test_turn_and_river_folds_are_always_talk_eligible_regardless_of_investment() -> None:
    for street_index in (2, 3):
        view = make_view(street_index=street_index, call_amount=50, own_bet=0, voluntarily_invested=False)
        assert is_talk_eligible("fold", view) is True


def test_bet_or_raise_is_always_talk_eligible() -> None:
    view = make_view(street_index=0, call_amount=0, own_bet=0)
    assert is_talk_eligible("bet_or_raise_to", view) is True


def test_free_check_is_not_talk_eligible() -> None:
    view = make_view(street_index=1, call_amount=0, own_bet=0)
    assert is_talk_eligible("check_or_call", view) is False


def test_preflop_limp_into_unraised_big_blind_is_not_talk_eligible() -> None:
    # UTG facing just the posted big blind, nobody has raised
    view = make_view(street_index=0, call_amount=100, own_bet=0, big_blind=100)
    assert is_talk_eligible("check_or_call", view) is False


def test_small_blind_completing_to_unraised_big_blind_is_not_talk_eligible() -> None:
    # SB has already posted 50, needs 50 more to match the (unraised) 100 BB
    view = make_view(street_index=0, call_amount=50, own_bet=50, big_blind=100)
    assert is_talk_eligible("check_or_call", view) is False


def test_preflop_call_over_an_actual_raise_is_talk_eligible() -> None:
    # someone raised to 300; hero calls
    view = make_view(street_index=0, call_amount=300, own_bet=0, big_blind=100)
    assert is_talk_eligible("check_or_call", view) is True


def test_postflop_call_is_always_talk_eligible_when_nonzero() -> None:
    # postflop has no blind baseline -- any nonzero call is over a real bet
    view = make_view(street_index=1, call_amount=50, own_bet=0)
    assert is_talk_eligible("check_or_call", view) is True
