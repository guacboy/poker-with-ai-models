from __future__ import annotations

from pydantic import BaseModel


class NewTournamentRequest(BaseModel):
    human_name: str = "You"


class NewTournamentResponse(BaseModel):
    tournament_id: str
    human_player_id: str


class ActionRequest(BaseModel):
    action: str  # "fold" | "check_or_call" | "bet_or_raise_to"
    amount: int | None = None
