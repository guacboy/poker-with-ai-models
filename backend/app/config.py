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
# deepseek-v4-pro (the heavier reasoning tier) can spend 80+ seconds and its
# entire reasoning budget on this prompt shape without ever producing a
# reply, even at a generous token budget -- deepseek-v4-flash is far more
# reliable for a bounded per-turn decision and still plenty capable.
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
XAI_MODEL = os.getenv("XAI_MODEL", "grok-4.6")

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

# Hard ceiling on a single AI provider call (decide/react_to_win/react_to_loss).
# Without this, a slow or hung provider blocks the entire tournament loop
# indefinitely -- every other seat and the human both wait on it -- instead of
# just falling back to a quiet fold/no-reaction the way a normal API error
# already does (see GameSession._run and the *_reaction methods).
AI_RESPONSE_TIMEOUT_SECONDS = float(os.getenv("AI_RESPONSE_TIMEOUT_SECONDS", "45.0"))

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

# Distinct built-in Kokoro voice per seat, picked to accent-match each
# model's company/CEO (still spoken in English -- Kokoro's `lang` param
# controls phonemization independently of `voice`, so a non-English voice
# pack reads English text in its own accent instead of switching language;
# see app/tts/kokoro_tts.py): Anthropic/Dario Amodei and OpenAI/Sam Altman
# are both American; DeepSeek is a Chinese company; Gemini's parent Google
# is led by Sundar Pichai, who is Indian; xAI/Elon Musk is a US citizen (no
# South African voice exists in Kokoro's set to match his birthplace).
VOICE_BY_PLAYER_ID: dict[str, str] = {
    "claude": "af_heart",
    "openai": "am_michael",
    "deepseek": "zm_yunjian",
    "gemini": "hf_alpha",
    "grok": "am_fenrir",
}

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
