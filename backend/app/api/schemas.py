from __future__ import annotations

from pydantic import BaseModel


class NewTournamentRequest(BaseModel):
    human_name: str = "You"
    # debug mode: every seat is a MockPlayer regardless of configured API
    # keys (see GameSession.new) and unlocks the debug-only endpoints below --
    # a real tournament (debug=False) never touches this at all.
    debug: bool = False


class NewTournamentResponse(BaseModel):
    tournament_id: str
    human_player_id: str
    is_debug: bool


class ActionRequest(BaseModel):
    action: str  # "fold" | "check_or_call" | "bet_or_raise_to"
    amount: int | None = None


class ForcedActionRequest(BaseModel):
    mode: str | None = None  # "all_in" | "call" | "check" | "fold" | None (clears it)


class AlwaysShowHandsRequest(BaseModel):
    enabled: bool
