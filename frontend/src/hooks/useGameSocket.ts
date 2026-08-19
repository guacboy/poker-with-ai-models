import { useCallback, useEffect, useReducer, useRef } from "react";
import type { ActionName, ActorView, PublicHand, PublicState, ServerEvent } from "../types/game";
import { formatBB } from "../utils/formatChips";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
const WS_BASE = API_BASE.replace(/^http/, "ws");

export interface PlayerActionEvent {
  id: string;
  playerId: string;
  action: ActionName;
  amount: number | null;
  message: string | null;
  audioBase64: string | null;
  audioDuration: number | null;
}

interface GameSocketState {
  connected: boolean;
  publicState: PublicState | null;
  actorView: ActorView | null;
  lastPlayerAction: PlayerActionEvent | null;
  lastActionLabelByPlayer: Record<string, string>;
  winnerPlayerId: string | null;
  tournamentOver: boolean;
  error: string | null;
  // the last in-progress hand's board/seats (including any cards revealed at
  // showdown) -- kept around so the result screen has something to render,
  // since the hand itself is gone (publicState.hand is null) once it's over
  lastHandSnapshot: PublicHand | null;
  // set for the HAND_RESULT_DISPLAY_SECONDS window after a hand ends; null
  // once the next hand starts
  handResultWinners: string[] | null;
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
  lastActionLabelByPlayer: {},
  winnerPlayerId: null,
  tournamentOver: false,
  error: null,
  lastHandSnapshot: null,
  handResultWinners: null,
};

function formatActionLabel(
  action: ActionName,
  amount: number | null,
  callAmount: number,
  resultingStack: number,
  bigBlind: number
): string {
  const isAllIn = resultingStack === 0;
  switch (action) {
    case "fold":
      return "Folded";
    case "check_or_call":
      if (callAmount === 0) return "Checked";
      return isAllIn ? "All In" : `Called ${formatBB(callAmount, bigBlind)}`;
    case "bet_or_raise_to":
      if (isAllIn) return "All In";
      return callAmount > 0
        ? `Raised to ${formatBB(amount ?? 0, bigBlind)}`
        : `Bet ${formatBB(amount ?? 0, bigBlind)}`;
  }
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
            lastActionLabelByPlayer: {},
            lastHandSnapshot: event.state.hand,
            handResultWinners: null,
          };
        case "awaiting_action":
          return { ...state, actorView: event.view };
        case "player_action": {
          const priorStreet = state.publicState?.hand?.street_index ?? null;
          const newStreet = event.state.hand?.street_index ?? null;
          // a street change (community cards just dealt) makes every other
          // seat's leftover check/call/raise label from the previous betting
          // round stale -- but a "Folded" label should stick around for the
          // rest of the hand, same as the seat's dimmed styling does.
          const labelsBase =
            newStreet !== priorStreet
              ? Object.fromEntries(
                  Object.entries(state.lastActionLabelByPlayer).filter(([playerId]) => {
                    const seat = event.state.hand?.seats.find((s) => s.player_id === playerId);
                    return seat?.folded === true;
                  })
                )
              : state.lastActionLabelByPlayer;
          // the live, in-hand stack (not PublicState.players[].stack, which only
          // reflects stack-at-start-of-hand until finish_hand() runs) is what
          // actually tells us whether this action put them all in
          const resultingStack =
            event.state.hand?.seats.find((s) => s.player_id === event.player_id)?.stack ?? -1;
          return {
            ...state,
            publicState: event.state,
            actorView: null,
            lastHandSnapshot: event.state.hand,
            lastActionLabelByPlayer: {
              ...labelsBase,
              [event.player_id]: formatActionLabel(
                event.action,
                event.amount,
                event.call_amount,
                resultingStack,
                event.state.big_blind
              ),
            },
            lastPlayerAction: {
              id: `${event.player_id}-${Date.now()}-${Math.random()}`,
              playerId: event.player_id,
              action: event.action,
              amount: event.amount,
              message: event.message,
              audioBase64: event.audio_base64,
              audioDuration: event.audio_duration,
            },
          };
        }
        case "hand_result":
          // event.state.hand is always null here (the hand just finished) --
          // keep the frozen lastHandSnapshot from the final player_action so
          // the board/cards stay on screen through the result display window
          return { ...state, publicState: event.state, handResultWinners: event.winners };
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
