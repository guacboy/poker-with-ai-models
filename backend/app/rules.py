"""Tournament rule constants.

Pure data, no logic. Every tunable rule for the tournament format lives here so it
can be adjusted without touching engine code. `engine/tournament.py` reads these
values; it never hardcodes numbers itself.
"""

# Table
NUM_SEATS = 6

# Buy-ins
STARTING_STACK = 5_000  # chips per buy-in; = 100 * STARTING BIG BLIND below
MAX_BUY_INS = 3  # per player (human and AI alike); busting all of them = eliminated
REBUY_SCALES_WITH_BLINDS = False  # rebuys are always STARTING_STACK, not current-level 100BB

# Blinds
# List of (small_blind, big_blind) tuples. The last entry repeats indefinitely once
# the tournament outlasts the defined schedule.
BLIND_SCHEDULE = [
    (50, 100),
    (75, 150),
    (100, 200),
    (150, 300),
    (200, 400),
    (300, 600),
    (400, 800),
    (600, 1_200),
    (800, 1_600),
    (1_200, 2_400),
    (1_600, 3_200),
    (2_000, 4_000),
]
ORBITS_PER_BLIND_LEVEL = 2  # one orbit = the button returning to someone who already held it

# Antes. "none" is the only mode wired up today; "big_blind" (BB posts one ante
# covering the table) and "every_player" (each player posts individually) are
# reserved names for a future rule change so callers don't need to invent new ones.
ANTE_MODE = "none"  # "none" | "big_blind" | "every_player"
ANTE_SCHEDULE: list[int] | None = None  # per-level ante amount, parallel to BLIND_SCHEDULE; unused while ANTE_MODE == "none"


def blinds_for_level(level_index: int) -> tuple[int, int]:
    """Small/big blind for a 0-indexed blind level, clamped to the last defined level."""
    clamped = min(level_index, len(BLIND_SCHEDULE) - 1)
    return BLIND_SCHEDULE[clamped]


def ante_for_level(level_index: int) -> int:
    if ANTE_MODE == "none" or not ANTE_SCHEDULE:
        return 0
    clamped = min(level_index, len(ANTE_SCHEDULE) - 1)
    return ANTE_SCHEDULE[clamped]
