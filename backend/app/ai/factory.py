"""Picks the real provider for a seat when its API key is configured, falling
back to the randomized mock player otherwise. This is the one place that
needs to change as keys get added -- nothing else in the app cares which
implementation a seat is actually running.

Debug-mode sessions (see api/session.py) never call this at all -- they build
every seat's MockPlayer directly, so a debug game can never trigger a real
provider call regardless of what's configured here."""

from __future__ import annotations

from .. import config
from .mock_player import MockPlayer
from .providers.anthropic_player import AnthropicPlayer
from .providers.gemini_player import GeminiPlayer
from .providers.openai_compatible_player import OpenAICompatiblePlayer

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
XAI_BASE_URL = "https://api.x.ai/v1"


def create_ai_player(player_id: str, display_name: str):
    if player_id == "claude" and config.ANTHROPIC_API_KEY:
        return AnthropicPlayer(player_id, display_name, config.ANTHROPIC_API_KEY, config.ANTHROPIC_MODEL)
    if player_id == "openai" and config.OPENAI_API_KEY:
        return OpenAICompatiblePlayer(player_id, display_name, config.OPENAI_API_KEY, config.OPENAI_MODEL)
    if player_id == "deepseek" and config.DEEPSEEK_API_KEY:
        return OpenAICompatiblePlayer(
            player_id, display_name, config.DEEPSEEK_API_KEY, config.DEEPSEEK_MODEL, base_url=DEEPSEEK_BASE_URL
        )
    if player_id == "gemini" and config.GEMINI_API_KEY:
        return GeminiPlayer(player_id, display_name, config.GEMINI_API_KEY, config.GEMINI_MODEL)
    if player_id == "grok" and config.XAI_API_KEY:
        return OpenAICompatiblePlayer(
            player_id, display_name, config.XAI_API_KEY, config.XAI_MODEL, base_url=XAI_BASE_URL
        )
    return MockPlayer(player_id, display_name)
