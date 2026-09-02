"""Tournament rule constants.

Pure data, no logic. Every tunable rule for the tournament format lives here so it
can be adjusted without touching engine code. `engine/tournament.py` reads these
values; it never hardcodes numbers itself.
"""

# Table
NUM_SEATS = 6

# Buy-ins
STARTING_STACK = 10_000  # chips per buy-in; = 100 * STARTING_BIG_BLIND below
MAX_BUY_INS = 3  # per player (human and AI alike); busting all of them = eliminated
REBUY_SCALES_WITH_BLINDS = False  # rebuys are always STARTING_STACK, not current-level 100BB

# Blinds -- computed from a formula (see `blinds_for_level` below) instead of
# a fixed schedule list, so there's no defined-levels length to ever run out
# of: blinds keep climbing for as long as a tournament (or a heads-up
# stalemate) keeps running. Big blind starts at STARTING_BIG_BLIND and
# multiplies by BLIND_GROWTH_FACTOR every level; small blind is always
# exactly half of it.
STARTING_BIG_BLIND = 100
BLIND_GROWTH_FACTOR = 1.4  # roughly doubles the big blind every 2 levels
ORBITS_PER_BLIND_LEVEL = 1  # one orbit = the button returning to someone who already held it

# Antes. "none" is the only mode wired up today; "big_blind" (BB posts one ante
# covering the table) and "every_player" (each player posts individually) are
# reserved names for a future rule change so callers don't need to invent new ones.
ANTE_MODE = "none"  # "none" | "big_blind" | "every_player"
ANTE_SCHEDULE: list[int] | None = None  # per-level ante amount, indexed the same way as blind levels; unused while ANTE_MODE == "none"


def blinds_for_level(level_index: int) -> tuple[int, int]:
    """Small/big blind for a 0-indexed blind level, computed directly from
    BLIND_GROWTH_FACTOR compounding off STARTING_BIG_BLIND rather than a
    fixed lookup table -- blinds keep increasing indefinitely regardless of
    how long a tournament (or a heads-up stalemate) runs, with no schedule
    length to ever run out of. Rounded to a clean 50-chip denomination;
    small blind is always exactly half the big blind."""
    big_blind = round(STARTING_BIG_BLIND * BLIND_GROWTH_FACTOR**level_index / 50) * 50
    return big_blind // 2, big_blind


def ante_for_level(level_index: int) -> int:
    if ANTE_MODE == "none" or not ANTE_SCHEDULE:
        return 0
    clamped = min(level_index, len(ANTE_SCHEDULE) - 1)
    return ANTE_SCHEDULE[clamped]
