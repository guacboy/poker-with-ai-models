from __future__ import annotations

from app import rules


def test_blinds_for_level_starts_at_the_configured_starting_big_blind() -> None:
    small_blind, big_blind = rules.blinds_for_level(0)
    assert big_blind == rules.STARTING_BIG_BLIND
    assert small_blind == big_blind // 2


def test_blinds_for_level_keeps_climbing_indefinitely() -> None:
    """Regression test: blinds used to come from a fixed schedule list that
    clamped to its last entry forever once a tournament (or a heads-up
    stalemate) outlasted it. There's no schedule now -- blinds_for_level is a
    pure formula, so it should keep producing a strictly higher big blind at
    every level with no upper bound to ever run out of."""
    big_blinds = [rules.blinds_for_level(level)[1] for level in range(30)]
    assert big_blinds == sorted(big_blinds)
    assert len(set(big_blinds)) == len(big_blinds)

    # sampled far out -- still climbing, not just for the first handful of levels
    assert rules.blinds_for_level(100)[1] > rules.blinds_for_level(50)[1] > rules.blinds_for_level(30)[1]


def test_blinds_for_level_keeps_small_blind_at_exactly_half_the_big_blind() -> None:
    for level in range(30):
        small_blind, big_blind = rules.blinds_for_level(level)
        assert small_blind == big_blind // 2


def test_blinds_for_level_rounds_to_a_clean_denomination() -> None:
    for level in range(30):
        _, big_blind = rules.blinds_for_level(level)
        assert big_blind % 50 == 0


def _round_to_nearest_50(value: float) -> int:
    return round(value / 50) * 50


def test_blinds_for_level_compounds_by_the_configured_growth_factor() -> None:
    # confirms the actual progression is STARTING_BIG_BLIND * BLIND_GROWTH_FACTOR
    # ** level (modulo the 50-chip rounding), not some other unrelated curve
    for level in range(1, 10):
        expected = rules.STARTING_BIG_BLIND * rules.BLIND_GROWTH_FACTOR**level
        _, actual = rules.blinds_for_level(level)
        assert actual == _round_to_nearest_50(expected)
