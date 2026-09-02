from __future__ import annotations

import pytest

from app.ai.mock_player import LOSS_REACTION_LINES, TRASH_TALK_LINES, WIN_REACTION_LINES, MockPlayer


@pytest.mark.asyncio
async def test_react_to_win_returns_one_of_the_canned_lines_or_none() -> None:
    player = MockPlayer("bot", "Bot", seed=0)
    for _ in range(50):
        message = await player.react_to_win({}, "Flush", 500)
        assert message in WIN_REACTION_LINES


@pytest.mark.asyncio
async def test_react_to_loss_returns_one_of_the_canned_lines_or_none() -> None:
    player = MockPlayer("bot", "Bot", seed=0)
    for _ in range(50):
        message = await player.react_to_loss({}, "Flush", 500)
        assert message in LOSS_REACTION_LINES


@pytest.mark.asyncio
async def test_force_dialogue_guarantees_a_real_win_reaction_line() -> None:
    """Regression test: every canned line list includes `None` entries so a
    mock stays quiet most of the time by default -- force_dialogue is meant
    to bypass exactly that, guaranteeing a real line every time instead of
    still occasionally landing on silence."""
    player = MockPlayer("bot", "Bot", seed=0)
    player.force_dialogue = True
    for _ in range(50):
        message = await player.react_to_win({}, "Flush", 500)
        assert message is not None
        assert message in WIN_REACTION_LINES


@pytest.mark.asyncio
async def test_force_dialogue_guarantees_a_real_loss_reaction_line() -> None:
    player = MockPlayer("bot", "Bot", seed=0)
    player.force_dialogue = True
    for _ in range(50):
        message = await player.react_to_loss({}, "Flush", 500)
        assert message is not None
        assert message in LOSS_REACTION_LINES


@pytest.mark.asyncio
async def test_force_dialogue_guarantees_a_real_action_talk_line() -> None:
    player = MockPlayer("bot", "Bot", seed=0)
    player.force_dialogue = True
    view = {
        "legal_actions": {
            "can_check_or_call": True,
            "can_bet_or_raise": False,
            "can_fold": False,
            "call_amount": 0,
            "min_bet_to": None,
            "max_bet_to": None,
        }
    }
    for _ in range(50):
        result = await player.decide(view)
        assert result.message is not None
        assert result.message in TRASH_TALK_LINES


def test_force_dialogue_defaults_to_off() -> None:
    assert MockPlayer("bot", "Bot").force_dialogue is False
