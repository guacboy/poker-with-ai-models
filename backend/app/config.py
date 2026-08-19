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
AI_THINKING_DELAY_SECONDS = float(os.getenv("AI_THINKING_DELAY_SECONDS", "1.2"))

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
