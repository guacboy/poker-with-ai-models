from __future__ import annotations

import pytest

from app.ai.mock_player import WIN_REACTION_LINES, MockPlayer


@pytest.mark.asyncio
async def test_react_to_win_returns_one_of_the_canned_lines_or_none() -> None:
    player = MockPlayer("bot", "Bot", seed=0)
    for _ in range(50):
        message = await player.react_to_win({}, "Flush", 500)
        assert message in WIN_REACTION_LINES
