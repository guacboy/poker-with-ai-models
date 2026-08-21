import { useCallback, useEffect, useReducer, useRef } from "react";
import type { ActionName, ActorView, PublicHand, PublicState, ServerEvent } from "../types/game";
import { formatBB } from "../utils/formatChips";
import { INITIAL_SOUND_EFFECT_TRACKING_STATE, soundEffectForEvent } from "../utils/soundEffects";
import { useSoundEffects } from "./useSoundEffects";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
const WS_BASE = API_BASE.replace(/^http/, "ws");

export interface PlayerActionEvent {
  id: string;
  playerId: string;
  // null for a guaranteed post-showdown win reaction, which isn't tied to
  // any poker action -- only the speech bubble/audio fields apply there
  action: ActionName | null;
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
  // the winning hand's pokerkit category (e.g. "Straight flush"), only set
  // when the hand actually reached a showdown; null for a fold-out win or
  // once the next hand starts
  winningHandLabel: string | null;
  // the board cards that were actually part of that winning hand -- empty
  // outside the same window winningHandLabel is set for
  winningBoardCards: string[];
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
  winningHandLabel: null,
  winningBoardCards: [],
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

// A street change (community cards just dealt, whether bundled into a
// player_action or delivered as its own board_dealt stage of a suspenseful
// all-in runout) makes every seat's leftover check/call/raise label from the
// previous betting round stale -- including the action that closed out that
// round, since it belongs to the street that just ended, not the one that
// just started. A "Folded" label is the one exception -- it should stick
// around for the rest of the hand, same as the seat's dimmed styling does.
function foldedOnlyLabels(
  labels: Record<string, string>,
  seats: PublicHand["seats"] | undefined
): Record<string, string> {
  return Object.fromEntries(
    Object.entries(labels).filter(([playerId]) => seats?.find((s) => s.player_id === playerId)?.folded === true)
  );
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
            // actorView is deliberately left as-is here (not reset to null):
            // the human's action controls stay on screen (disabled) between
            // their turns instead of disappearing, so this keeps the last
            // known legal_actions shape around as a placeholder until the
            // next "awaiting_action" event replaces it with the real one
            lastActionLabelByPlayer: {},
            lastHandSnapshot: event.state.hand,
            handResultWinners: null,
            winningHandLabel: null,
            winningBoardCards: [],
          };
        case "awaiting_action":
          return { ...state, actorView: event.view };
        case "board_dealt":
          // a suspenseful runout stage (e.g. everyone's all-in) -- refresh
          // the board/seat snapshot and clear stale action labels the same
          // way a street change bundled into player_action would
          return {
            ...state,
            publicState: event.state,
            lastHandSnapshot: event.state.hand,
            lastActionLabelByPlayer: foldedOnlyLabels(state.lastActionLabelByPlayer, event.state.hand?.seats),
          };
        case "player_action": {
          const priorStreet = state.publicState?.hand?.street_index ?? null;
          const newStreet = event.state.hand?.street_index ?? null;
          const streetChanged = newStreet !== priorStreet;
          const labelsBase = streetChanged
            ? foldedOnlyLabels(state.lastActionLabelByPlayer, event.state.hand?.seats)
            : state.lastActionLabelByPlayer;
          // the live, in-hand stack (not PublicState.players[].stack, which only
          // reflects stack-at-start-of-hand until finish_hand() runs) is what
          // actually tells us whether this action put them all in
          const resultingStack =
            event.state.hand?.seats.find((s) => s.player_id === event.player_id)?.stack ?? -1;
          return {
            ...state,
            publicState: event.state,
            // see the "hand_started" case above -- actorView is left in
            // place so the controls stay visible (disabled) until it's the
            // human's turn again
            lastHandSnapshot: event.state.hand,
            lastActionLabelByPlayer: streetChanged
              ? labelsBase
              : {
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
          return {
            ...state,
            publicState: event.state,
            handResultWinners: event.winners,
            winningHandLabel: event.winning_hand_label,
            winningBoardCards: event.winning_board_cards,
          };
        case "win_reaction":
        case "loss_reaction":
          // a guaranteed post-showdown reaction (gloating or sore-loser alike)
          // -- reuses lastPlayerAction so the same speech-bubble/audio-queue
          // effect in App.tsx picks it up, but doesn't touch
          // publicState/lastActionLabelByPlayer since no actual poker action
          // happened
          return {
            ...state,
            lastPlayerAction: {
              id: `${event.player_id}-${Date.now()}-${Math.random()}`,
              playerId: event.player_id,
              action: null,
              amount: null,
              message: event.message,
              audioBase64: event.audio_base64,
              audioDuration: event.audio_duration,
            },
          };
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
  const { play: playSoundEffect } = useSoundEffects();
  const soundTrackingRef = useRef(INITIAL_SOUND_EFFECT_TRACKING_STATE);

  useEffect(() => {
    if (!tournamentId) return;

    const ws = new WebSocket(`${WS_BASE}/tournament/${tournamentId}/ws`);
    wsRef.current = ws;

    ws.onopen = () => dispatch({ kind: "connected" });
    ws.onclose = () => dispatch({ kind: "disconnected" });
    ws.onmessage = (event) => {
      const parsed = JSON.parse(event.data) as ServerEvent;

      const { sounds, next } = soundEffectForEvent(parsed, soundTrackingRef.current);
      soundTrackingRef.current = next;
      sounds.forEach(playSoundEffect);

      dispatch({ kind: "server_event", event: parsed });
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [tournamentId, playSoundEffect]);

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

export async function createTournament(options?: { debug?: boolean }): Promise<{
  tournamentId: string;
  humanPlayerId: string;
  isDebug: boolean;
}> {
  const resp = await fetch(`${API_BASE}/tournament/new`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ human_name: "You", debug: options?.debug ?? false }),
  });
  if (!resp.ok) throw new Error(`failed to start tournament (${resp.status})`);
  const body = await resp.json();
  return { tournamentId: body.tournament_id, humanPlayerId: body.human_player_id, isDebug: body.is_debug };
}

export type ForcedActionMode = "all_in" | "call" | "check" | "fold";

// Debug-only controls -- the backend rejects all of these with a 403 on a
// non-debug tournament, so there's no risk of accidentally affecting a real
// (API-key-driven) game.
async function debugPost(tournamentId: string, path: string, body: unknown): Promise<void> {
  const resp = await fetch(`${API_BASE}/tournament/${tournamentId}/debug/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}));
    throw new Error(detail.detail ?? `debug request failed (${resp.status})`);
  }
}

export function setForcedAiAction(tournamentId: string, mode: ForcedActionMode | null): Promise<void> {
  return debugPost(tournamentId, "forced_action", { mode });
}

export function setAlwaysShowHands(tournamentId: string, enabled: boolean): Promise<void> {
  return debugPost(tournamentId, "always_show_hands", { enabled });
}

export function endRound(tournamentId: string): Promise<void> {
  return debugPost(tournamentId, "end_round", {});
}
