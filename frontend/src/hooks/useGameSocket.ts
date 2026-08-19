import { useCallback, useEffect, useReducer, useRef } from "react";
import type { ActionName, ActorView, PublicState, ServerEvent } from "../types/game";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
const WS_BASE = API_BASE.replace(/^http/, "ws");

export interface PlayerActionEvent {
  id: string;
  playerId: string;
  action: ActionName;
  amount: number | null;
  message: string | null;
  audioBase64: string | null;
}

interface GameSocketState {
  connected: boolean;
  publicState: PublicState | null;
  actorView: ActorView | null;
  lastPlayerAction: PlayerActionEvent | null;
  winnerPlayerId: string | null;
  tournamentOver: boolean;
  error: string | null;
}

type Action =
  | { kind: "connected" }
  | { kind: "disconnected" }
  | { kind: "server_event"; event: ServerEvent };

const initialState: GameSocketState = {
  connected: false,
  publicState: null,
  actorView: null,
  lastPlayerAction: null,
  winnerPlayerId: null,
  tournamentOver: false,
  error: null,
};

function reducer(state: GameSocketState, action: Action): GameSocketState {
  switch (action.kind) {
    case "connected":
      return { ...state, connected: true, error: null };
    case "disconnected":
      return { ...state, connected: false };
    case "server_event": {
      const event = action.event;
      switch (event.type) {
        case "snapshot":
          return { ...state, publicState: event.state };
        case "hand_started":
          return { ...state, publicState: event.state, actorView: null };
        case "awaiting_action":
          return { ...state, actorView: event.view };
        case "player_action":
          return {
            ...state,
            publicState: event.state,
            actorView: null,
            lastPlayerAction: {
              id: `${event.player_id}-${Date.now()}-${Math.random()}`,
              playerId: event.player_id,
              action: event.action,
              amount: event.amount,
              message: event.message,
              audioBase64: event.audio_base64,
            },
          };
        case "hand_result":
          return { ...state, publicState: event.state };
        case "tournament_over":
          return { ...state, tournamentOver: true, winnerPlayerId: event.winner_player_id };
        case "error":
          return { ...state, error: event.message };
        default:
          return state;
      }
    }
  }
}

export function useGameSocket(tournamentId: string | null) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!tournamentId) return;

    const ws = new WebSocket(`${WS_BASE}/tournament/${tournamentId}/ws`);
    wsRef.current = ws;

    ws.onopen = () => dispatch({ kind: "connected" });
    ws.onclose = () => dispatch({ kind: "disconnected" });
    ws.onmessage = (event) => {
      const parsed = JSON.parse(event.data) as ServerEvent;
      dispatch({ kind: "server_event", event: parsed });
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [tournamentId]);

  const submitAction = useCallback(
    async (action: ActionName, amount: number | null) => {
      if (!tournamentId) return;
      const resp = await fetch(`${API_BASE}/tournament/${tournamentId}/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, amount }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.detail ?? `action failed (${resp.status})`);
      }
    },
    [tournamentId]
  );

  return { state, submitAction };
}

export async function createTournament(): Promise<{
  tournamentId: string;
  humanPlayerId: string;
}> {
  const resp = await fetch(`${API_BASE}/tournament/new`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ human_name: "You" }),
  });
  if (!resp.ok) throw new Error(`failed to start tournament (${resp.status})`);
  const body = await resp.json();
  return { tournamentId: body.tournament_id, humanPlayerId: body.human_player_id };
}
