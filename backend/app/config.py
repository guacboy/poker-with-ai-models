"""Environment configuration: API keys, model names, and seat layout.

Nothing here talks to a provider SDK directly -- `ai/factory.py` reads these
values to decide which player implementation to instantiate per seat.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
XAI_API_KEY = os.getenv("XAI_API_KEY")

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-pro")
XAI_MODEL = os.getenv("XAI_MODEL", "grok-5")

# (player_id, display_name) for each AI seat, in fixed seat order.
AI_SEATS: list[tuple[str, str]] = [
    ("claude", "Claude"),
    ("openai", "OpenAI"),
    ("deepseek", "DeepSeek"),
    ("gemini", "Gemini"),
    ("grok", "Grok"),
]
HUMAN_PLAYER_ID = "human"

# Artificial delay before an AI's action is applied, purely for UX pacing so
# actions don't feel instant/jarring in the UI.
AI_THINKING_DELAY_SECONDS = float(os.getenv("AI_THINKING_DELAY_SECONDS", "1.0"))

# After a spoken trash-talk line, how much longer to hold before moving on to
# the next player's turn, on top of however long the line itself takes to play.
AUDIO_TRAILING_DELAY_SECONDS = float(os.getenv("AUDIO_TRAILING_DELAY_SECONDS", "0.3"))

# How long to keep the finished hand (winner glow, board, revealed cards) on
# screen before dealing the next one.
HAND_RESULT_DISPLAY_SECONDS = float(os.getenv("HAND_RESULT_DISPLAY_SECONDS", "5.0"))

# Same, but for a hand result with no winning-hand label to show (a fold-out
# win -- nobody's cards were ever revealed) -- shorter since there's less on
# screen to actually look at.
HAND_RESULT_DISPLAY_SECONDS_NO_REVEAL = float(os.getenv("HAND_RESULT_DISPLAY_SECONDS_NO_REVEAL", "2.0"))

# When a single action leaves no more decisions to make (e.g. everyone left is
# all-in) and pokerkit deals out multiple remaining streets at once, how long
# to hold on each newly-revealed street before showing the next one, instead
# of dumping the whole runout on screen in one shot.
BOARD_REVEAL_DELAY_SECONDS = float(os.getenv("BOARD_REVEAL_DELAY_SECONDS", "3.0"))

# Distinct built-in Kokoro voice per seat, for tell-apart-ability only (not
# personality). See app/tts/kokoro_tts.py.
VOICE_BY_PLAYER_ID: dict[str, str] = {
    "claude": "af_heart",
    "openai": "am_michael",
    "deepseek": "bm_george",
    "gemini": "bf_emma",
    "grok": "am_fenrir",
}

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
