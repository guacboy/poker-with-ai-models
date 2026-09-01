from __future__ import annotations

from unittest.mock import patch

from app.ai.base import (
    AMBIENT_TALK_CHANCE,
    MEANINGFUL_TALK_CHANCE,
    MEANINGFUL_TALK_CHANCE_RISKY,
    FLOP,
    PREFLOP,
    RIVER,
    TURN,
    build_loss_reaction_prompt,
    build_prompt,
    build_win_reaction_prompt,
    is_talk_eligible,
    talk_chance,
)


def make_view(
    *,
    street_index: int,
    call_amount: int,
    own_bet: int,
    big_blind: int = 100,
    voluntarily_invested: bool = False,
    max_bet_to: int | None = None,
    other_seats: list[dict] | None = None,
) -> dict:
    seats = [
        {
            "player_id": "hero",
            "bet": own_bet,
            "voluntarily_invested": voluntarily_invested,
            "folded": False,
            "stack": 1000,
        }
    ]
    seats += other_seats or []
    return {
        "your_player_id": "hero",
        "street_index": street_index,
        "big_blind": big_blind,
        "seats": seats,
        "legal_actions": {"call_amount": call_amount, "max_bet_to": max_bet_to},
    }


def all_in_opponent(player_id: str = "villain") -> dict:
    return {"player_id": player_id, "bet": 0, "voluntarily_invested": True, "folded": False, "stack": 0}


# -- talk_chance: ambient tier (previously always-silent actions) ------------


def test_preflop_fold_with_no_prior_investment_uses_ambient_chance() -> None:
    # e.g. UTG folding to an unraised big blind, or to someone else's raise,
    # having never put in anything beyond (at most) a forced blind themselves
    view = make_view(street_index=PREFLOP, call_amount=100, own_bet=0, voluntarily_invested=False)
    assert talk_chance("fold", view) == AMBIENT_TALK_CHANCE


def test_flop_fold_with_no_prior_investment_uses_ambient_chance() -> None:
    view = make_view(street_index=FLOP, call_amount=50, own_bet=0, voluntarily_invested=False)
    assert talk_chance("fold", view) == AMBIENT_TALK_CHANCE


def test_free_check_uses_flat_ambient_chance_on_every_street() -> None:
    for street in (PREFLOP, FLOP, TURN, RIVER):
        view = make_view(street_index=street, call_amount=0, own_bet=0)
        assert talk_chance("check_or_call", view) == AMBIENT_TALK_CHANCE


def test_preflop_limp_into_unraised_big_blind_uses_ambient_chance() -> None:
    # UTG facing just the posted big blind, nobody has raised
    view = make_view(street_index=PREFLOP, call_amount=100, own_bet=0, big_blind=100)
    assert talk_chance("check_or_call", view) == AMBIENT_TALK_CHANCE


def test_small_blind_completing_to_unraised_big_blind_uses_ambient_chance() -> None:
    # SB has already posted 50, needs 50 more to match the (unraised) 100 BB
    view = make_view(street_index=PREFLOP, call_amount=50, own_bet=50, big_blind=100)
    assert talk_chance("check_or_call", view) == AMBIENT_TALK_CHANCE


# -- talk_chance: meaningful tier (previously always-eligible actions) -------


def test_preflop_fold_after_having_voluntarily_invested_uses_meaningful_chance() -> None:
    # e.g. hero limped in (or raised) earlier this hand, then gives up to a
    # later raise -- that's a real decision to react to
    view = make_view(street_index=PREFLOP, call_amount=200, own_bet=0, voluntarily_invested=True)
    assert talk_chance("fold", view) == MEANINGFUL_TALK_CHANCE


def test_flop_fold_after_having_voluntarily_invested_uses_meaningful_chance() -> None:
    view = make_view(street_index=FLOP, call_amount=50, own_bet=0, voluntarily_invested=True)
    assert talk_chance("fold", view) == MEANINGFUL_TALK_CHANCE


def test_turn_and_river_folds_use_meaningful_chance_regardless_of_investment() -> None:
    for street in (TURN, RIVER):
        view = make_view(street_index=street, call_amount=50, own_bet=0, voluntarily_invested=False)
        assert talk_chance("fold", view) == MEANINGFUL_TALK_CHANCE


def test_bet_or_raise_uses_meaningful_chance() -> None:
    view = make_view(street_index=PREFLOP, call_amount=0, own_bet=0)
    assert talk_chance("bet_or_raise_to", view) == MEANINGFUL_TALK_CHANCE


def test_preflop_call_over_an_actual_raise_uses_meaningful_chance() -> None:
    # someone raised to 300; hero calls
    view = make_view(street_index=PREFLOP, call_amount=300, own_bet=0, big_blind=100)
    assert talk_chance("check_or_call", view) == MEANINGFUL_TALK_CHANCE


def test_postflop_call_uses_meaningful_chance_when_nonzero() -> None:
    # postflop has no blind baseline -- any nonzero call is over a real bet
    view = make_view(street_index=FLOP, call_amount=50, own_bet=0)
    assert talk_chance("check_or_call", view) == MEANINGFUL_TALK_CHANCE


def test_unknown_action_has_zero_chance() -> None:
    view = make_view(street_index=PREFLOP, call_amount=0, own_bet=0)
    assert talk_chance("some_other_action", view) == 0.0


# -- risky-moment boost (turn/river only) ------------------------------------


def test_shoving_all_in_on_turn_boosts_meaningful_chance_to_certain() -> None:
    view = make_view(street_index=TURN, call_amount=0, own_bet=0, max_bet_to=1000)
    assert talk_chance("bet_or_raise_to", view, amount=1000) == MEANINGFUL_TALK_CHANCE_RISKY


def test_shoving_less_than_max_does_not_count_as_risky() -> None:
    view = make_view(street_index=TURN, call_amount=0, own_bet=0, max_bet_to=1000)
    assert talk_chance("bet_or_raise_to", view, amount=500) == MEANINGFUL_TALK_CHANCE


def test_reacting_to_an_opponents_all_in_on_river_boosts_a_call_to_certain() -> None:
    view = make_view(street_index=RIVER, call_amount=500, own_bet=0, other_seats=[all_in_opponent()])
    assert talk_chance("check_or_call", view) == MEANINGFUL_TALK_CHANCE_RISKY


def test_reacting_to_an_opponents_all_in_on_river_boosts_a_fold_to_certain() -> None:
    view = make_view(street_index=RIVER, call_amount=500, own_bet=0, other_seats=[all_in_opponent()])
    assert talk_chance("fold", view) == MEANINGFUL_TALK_CHANCE_RISKY


def test_reacting_to_an_opponents_all_in_on_river_does_not_boost_a_free_check() -> None:
    # edge case (e.g. a side pot already settled elsewhere) -- the risky boost
    # only applies to the meaningful tier, ambient stays flat regardless
    view = make_view(street_index=RIVER, call_amount=0, own_bet=0, other_seats=[all_in_opponent()])
    assert talk_chance("check_or_call", view) == AMBIENT_TALK_CHANCE


def test_a_folded_opponents_empty_stack_does_not_count_as_an_all_in() -> None:
    folded_broke_seat = {"player_id": "villain", "bet": 0, "voluntarily_invested": True, "folded": True, "stack": 0}
    view = make_view(street_index=RIVER, call_amount=500, own_bet=0, other_seats=[folded_broke_seat])
    assert talk_chance("check_or_call", view) == MEANINGFUL_TALK_CHANCE  # not boosted


def test_risky_boost_does_not_apply_preflop_or_flop() -> None:
    for street in (PREFLOP, FLOP):
        view = make_view(street_index=street, call_amount=500, own_bet=0, other_seats=[all_in_opponent()])
        assert talk_chance("check_or_call", view) == MEANINGFUL_TALK_CHANCE


# -- is_talk_eligible: rolls talk_chance against random.random() ------------


def test_is_talk_eligible_rolls_below_chance_as_eligible() -> None:
    view = make_view(street_index=PREFLOP, call_amount=0, own_bet=0)  # ambient 50%
    with patch("app.ai.base.random.random", return_value=0.49):
        assert is_talk_eligible("check_or_call", view) is True


def test_is_talk_eligible_rolls_above_chance_as_not_eligible() -> None:
    view = make_view(street_index=PREFLOP, call_amount=0, own_bet=0)  # ambient 50%
    with patch("app.ai.base.random.random", return_value=0.51):
        assert is_talk_eligible("check_or_call", view) is False


# -- build_loss_reaction_prompt: cites the human's hand when it's known -----


def _loss_view(opponent_hole_cards: list[str] | None = None) -> dict:
    view = {"your_hole_cards": ["2c", "7d"], "board_cards": ["Ah", "Kh", "Qh", "Jh", "Th"]}
    if opponent_hole_cards is not None:
        view["opponent_hole_cards"] = opponent_hole_cards
    return view


def test_build_loss_reaction_prompt_cites_the_humans_hand_when_revealed() -> None:
    prompt = build_loss_reaction_prompt(_loss_view(["Ac", "Kc"]), "One pair", 500)
    assert "The human's hole cards: Ac, Kc" in prompt


def test_build_loss_reaction_prompt_omits_the_humans_hand_when_not_revealed() -> None:
    prompt = build_loss_reaction_prompt(_loss_view(), "One pair", 500)
    assert "The human's hole cards" not in prompt


# -- information leaks: the AI must not blurt out an unshown hand's cards ---


def _decide_view() -> dict:
    return {
        "your_player_id": "hero",
        "small_blind": 50,
        "big_blind": 100,
        "your_hole_cards": ["Ah", "As"],
        "board_cards": [],
        "pot_total": 150,
        "seats": [
            {
                "player_id": "hero",
                "name": "Hero",
                "stack": 1000,
                "bet": 0,
                "is_button": False,
                "is_small_blind": False,
                "is_big_blind": False,
                "folded": False,
                "is_to_act": True,
            }
        ],
        "legal_actions": {
            "can_fold": True,
            "can_check_or_call": True,
            "call_amount": 0,
            "can_bet_or_raise": True,
            "min_bet_to": 200,
            "max_bet_to": 1000,
        },
    }


def test_build_prompt_forbids_revealing_hole_cards_in_talk() -> None:
    """Regression test: the model was given its own hole cards for context but
    never told to keep them secret, so a raise's trash talk could blurt out
    e.g. "pocket aces" mid-hand -- long before any showdown actually reveals
    that hand to the table."""
    prompt = build_prompt(_decide_view())
    assert "never reveal or hint at your actual hole cards" in prompt


def test_build_win_reaction_prompt_forbids_leak_on_a_fold_out_win() -> None:
    """A fold-out win never reveals any cards -- hand_label is None -- so the
    gloating reaction must not be allowed to name what was actually held."""
    prompt = build_win_reaction_prompt(_loss_view(), None, 500)
    assert "never reveal or hint" in prompt


def test_build_win_reaction_prompt_has_no_secrecy_note_at_a_real_showdown() -> None:
    """At a real showdown the hand really was shown, so there's nothing left
    to protect -- the secrecy note only belongs on the fold-out branch."""
    prompt = build_win_reaction_prompt(_loss_view(), "One pair", 500)
    assert "never reveal or hint" not in prompt
