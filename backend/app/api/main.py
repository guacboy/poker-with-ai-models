from __future__ import annotations

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .. import config
from .schemas import ActionRequest, NewTournamentRequest, NewTournamentResponse
from .session import GameSession, HumanTurnError, SESSIONS

app = FastAPI(title="AI Poker Table")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_ORIGIN],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_session(tournament_id: str) -> GameSession:
    session = SESSIONS.get(tournament_id)
    if session is None:
        raise HTTPException(404, "tournament not found")
    return session


@app.post("/tournament/new", response_model=NewTournamentResponse)
async def new_tournament(body: NewTournamentRequest) -> NewTournamentResponse:
    session = GameSession.new(body.human_name)
    SESSIONS[session.tournament_id] = session
    session.start()
    return NewTournamentResponse(tournament_id=session.tournament_id, human_player_id=session.human_player_id)


@app.post("/tournament/{tournament_id}/action")
async def submit_action(tournament_id: str, body: ActionRequest) -> dict:
    session = get_session(tournament_id)
    try:
        session.submit_human_action(body.action, body.amount)
    except HumanTurnError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}


@app.websocket("/tournament/{tournament_id}/ws")
async def tournament_ws(websocket: WebSocket, tournament_id: str) -> None:
    session = SESSIONS.get(tournament_id)
    if session is None:
        await websocket.close(code=4404)
        return

    await session.register(websocket)
    try:
        while True:
            # clients don't send anything over this socket; just keep it open
            await websocket.receive_text()
    except WebSocketDisconnect:
        session.unregister(websocket)
