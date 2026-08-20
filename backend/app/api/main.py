from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .. import config
from .schemas import (
    ActionRequest,
    AlwaysShowHandsRequest,
    ForcedActionRequest,
    NewTournamentRequest,
    NewTournamentResponse,
)
from .session import DebugOnlyError, GameSession, HumanTurnError, SESSIONS

app = FastAPI(title="AI Poker Table")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_ORIGIN],
    allow_methods=["*"],
    allow_headers=["*"],
)

# static sound effects (betting, all-in, cards, folding) -- lives at the repo
# root as assets/sounds/, served here so the frontend can just <audio src>
# them by URL instead of duplicating the files into the frontend build
SOUNDS_DIR = Path(__file__).resolve().parents[3] / "assets" / "sounds"
if SOUNDS_DIR.is_dir():
    app.mount("/sounds", StaticFiles(directory=SOUNDS_DIR), name="sounds")

# static bot profile pictures -- same reasoning as /sounds above
IMAGES_DIR = Path(__file__).resolve().parents[3] / "assets" / "png"
if IMAGES_DIR.is_dir():
    app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")


def get_session(tournament_id: str) -> GameSession:
    session = SESSIONS.get(tournament_id)
    if session is None:
        raise HTTPException(404, "tournament not found")
    return session


@app.post("/tournament/new", response_model=NewTournamentResponse)
async def new_tournament(body: NewTournamentRequest) -> NewTournamentResponse:
    session = GameSession.new(body.human_name, debug=body.debug)
    SESSIONS[session.tournament_id] = session
    session.start()
    return NewTournamentResponse(
        tournament_id=session.tournament_id, human_player_id=session.human_player_id, is_debug=session.is_debug
    )


@app.post("/tournament/{tournament_id}/action")
async def submit_action(tournament_id: str, body: ActionRequest) -> dict:
    session = get_session(tournament_id)
    try:
        session.submit_human_action(body.action, body.amount)
    except HumanTurnError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}


@app.post("/tournament/{tournament_id}/debug/forced_action")
async def set_forced_action(tournament_id: str, body: ForcedActionRequest) -> dict:
    session = get_session(tournament_id)
    try:
        session.set_forced_ai_action(body.mode)
    except DebugOnlyError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}


@app.post("/tournament/{tournament_id}/debug/always_show_hands")
async def set_always_show_hands(tournament_id: str, body: AlwaysShowHandsRequest) -> dict:
    session = get_session(tournament_id)
    try:
        session.set_always_show_hands(body.enabled)
    except DebugOnlyError as exc:
        raise HTTPException(403, str(exc)) from exc
    await session.broadcast_snapshot()
    return {"ok": True}


@app.post("/tournament/{tournament_id}/debug/end_round")
async def end_round(tournament_id: str) -> dict:
    session = get_session(tournament_id)
    try:
        await session.force_end_round()
    except DebugOnlyError as exc:
        raise HTTPException(403, str(exc)) from exc
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
