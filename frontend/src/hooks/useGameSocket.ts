import { useCallback, useEffect, useReducer, useRef } from "react";
import type {
  ActionName,
  ActorView,
  LogEntry,
  PublicPlayer,
  PublicState,
  ServerEvent,
} from "../types/game";

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
  log: LogEntry[];
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
  log: [],
  winnerPlayerId: null,
  tournamentOver: false,
  error: null,
};

function playerName(players: PublicPlayer[], id: string): string {
  return players.find((p) => p.player_id === id)?.name ?? id;
}

function actionVerb(action: ActionName, amount: number | null): string {
  switch (action) {
    case "fold":
      return "folds";
    case "check_or_call":
      return amount ? `calls` : "checks";
    case "bet_or_raise_to":
      return `raises to ${amount}`;
  }
}

let logCounter = 0;
function pushLog(log: LogEntry[], text: string): LogEntry[] {
  logCounter += 1;
  const entry: LogEntry = { id: `log-${logCounter}`, text };
  return [...log.slice(-99), entry];
}

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
          return {
            ...state,
            publicState: event.state,
            actorView: null,
            log: pushLog(
              state.log,
              `Hand #${event.state.hand_count + 1} — blinds ${event.state.small_blind}/${event.state.big_blind}`
            ),
          };
        case "awaiting_action":
          return { ...state, actorView: event.view };
        case "player_action": {
          const name = playerName(event.state.players, event.player_id);
          const text = `${name} ${actionVerb(event.action, event.amount)}`;
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
            log: pushLog(state.log, text),
          };
        }
        case "hand_result": {
          let log = state.log;
          for (const bust of event.bust_events) {
            const name = playerName(event.state.players, bust.player_id);
            log = pushLog(
              log,
              bust.eliminated ? `${name} is eliminated!` : `${name} busts and rebuys.`
            );
          }
          return { ...state, publicState: event.state, log };
        }
        case "tournament_over":
          return {
            ...state,
            tournamentOver: true,
            winnerPlayerId: event.winner_player_id,
            log: pushLog(
              state.log,
              event.winner_player_id
                ? `${playerName(state.publicState?.players ?? [], event.winner_player_id)} wins the tournament!`
                : "Tournament over."
            ),
          };
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

export async function createTournament(humanName: string): Promise<{
  tournamentId: string;
  humanPlayerId: string;
}> {
  const resp = await fetch(`${API_BASE}/tournament/new`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ human_name: humanName }),
  });
  if (!resp.ok) throw new Error(`failed to start tournament (${resp.status})`);
  const body = await resp.json();
  return { tournamentId: body.tournament_id, humanPlayerId: body.human_player_id };
}
