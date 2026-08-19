import { useEffect, useRef, useState } from "react";
import "./App.css";
import { ActionControls } from "./components/ActionControls";
import type { SeatViewModel } from "./components/Seat";
import { Table } from "./components/Table";
import { TournamentStatus } from "./components/TournamentStatus";
import { useAudioQueue } from "./hooks/useAudioQueue";
import { createTournament, useGameSocket } from "./hooks/useGameSocket";

// Fallback when there's no audio duration to go on (e.g. TTS isn't downloaded).
const FALLBACK_SPEECH_BUBBLE_DURATION_MS = 4500;
// Matches the backend's AUDIO_TRAILING_DELAY_SECONDS default -- how much
// longer the line lingers on screen after it finishes playing.
const AUDIO_TRAILING_DELAY_MS = 1000;

function StartScreen({ onStart }: { onStart: () => void }) {
  return (
    <div className="start-screen">
      <h1>AI Poker Table</h1>
      <button onClick={onStart}>Start Tournament</button>
    </div>
  );
}

function GameScreen({ tournamentId, humanPlayerId }: { tournamentId: string; humanPlayerId: string }) {
  const { state, submitAction } = useGameSocket(tournamentId);
  const { enqueue } = useAudioQueue();

  const [speechMessages, setSpeechMessages] = useState<Record<string, string | null>>({});
  const timeoutsRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  useEffect(() => {
    const action = state.lastPlayerAction;
    if (!action) return;

    if (action.message) {
      const displayMs =
        action.audioDuration != null
          ? action.audioDuration * 1000 + AUDIO_TRAILING_DELAY_MS
          : FALLBACK_SPEECH_BUBBLE_DURATION_MS;

      setSpeechMessages((prev) => ({ ...prev, [action.playerId]: action.message }));
      clearTimeout(timeoutsRef.current[action.playerId]);
      timeoutsRef.current[action.playerId] = setTimeout(() => {
        setSpeechMessages((prev) => ({ ...prev, [action.playerId]: null }));
      }, displayMs);
    }

    if (action.audioBase64) {
      enqueue(action.audioBase64);
    }
  }, [state.lastPlayerAction, enqueue]);

  useEffect(() => {
    const timeouts = timeoutsRef.current;
    return () => {
      Object.values(timeouts).forEach(clearTimeout);
    };
  }, []);

  const publicState = state.publicState;
  if (!publicState) {
    return <div className="loading-screen">Connecting…</div>;
  }

  // while a just-finished hand's result is on screen, keep rendering its
  // frozen board/cards instead of publicState.hand, which goes null the
  // instant the hand ends
  const isHandResult = state.handResultWinners !== null;
  const displayHand = isHandResult ? state.lastHandSnapshot : publicState.hand;

  const seats: SeatViewModel[] = publicState.players.map((player) => {
    const handSeat = displayHand?.seats.find((s) => s.player_id === player.player_id);
    return {
      playerId: player.player_id,
      name: player.name,
      kind: player.kind,
      status: player.status,
      // handSeat.stack is live and updates as bets go in; player.stack only
      // reflects stack-at-start-of-hand until the hand finishes
      stack: handSeat?.stack ?? player.stack,
      bet: handSeat?.bet ?? 0,
      folded: handSeat?.folded ?? false,
      isButton: handSeat?.is_button ?? false,
      isSmallBlind: handSeat?.is_small_blind ?? false,
      isBigBlind: handSeat?.is_big_blind ?? false,
      isToAct: handSeat?.is_to_act ?? false,
      holeCards: handSeat?.hole_cards ?? null,
      buyInsUsed: player.buy_ins_used,
      buyInsRemaining: player.buy_ins_remaining,
      lastActionLabel: state.lastActionLabelByPlayer[player.player_id],
      isWinner: isHandResult && (state.handResultWinners?.includes(player.player_id) ?? false),
    };
  });

  const isMyTurn = state.actorView?.your_player_id === humanPlayerId;

  return (
    <div className="game-screen">
      <TournamentStatus
        handCount={publicState.hand_count}
        smallBlind={publicState.small_blind}
        bigBlind={publicState.big_blind}
        handsUntilNextLevel={publicState.hands_until_next_level}
        players={publicState.players}
        humanPlayerId={humanPlayerId}
      />

      <div className="game-main">
        <Table
          seats={seats}
          humanPlayerId={humanPlayerId}
          speechMessages={speechMessages}
          boardCards={displayHand?.board_cards ?? []}
          potTotal={displayHand?.pot_total ?? 0}
          bigBlind={publicState.big_blind}
        />

        <ActionControls
          legalActions={isMyTurn ? state.actorView!.legal_actions : null}
          bigBlind={publicState.big_blind}
          onAction={(action, amount) => {
            submitAction(action, amount).catch((err) => console.error(err));
          }}
        />

        {state.tournamentOver && (
          <div className="tournament-over-banner">
            {state.winnerPlayerId
              ? `${publicState.players.find((p) => p.player_id === state.winnerPlayerId)?.name ?? "Someone"} wins the tournament!`
              : "Tournament over."}
          </div>
        )}

        {state.error && <div className="error-banner">{state.error}</div>}
      </div>
    </div>
  );
}

export default function App() {
  const [session, setSession] = useState<{ tournamentId: string; humanPlayerId: string } | null>(
    null
  );

  if (!session) {
    return (
      <StartScreen
        onStart={async () => {
          const result = await createTournament();
          setSession(result);
        }}
      />
    );
  }

  return <GameScreen tournamentId={session.tournamentId} humanPlayerId={session.humanPlayerId} />;
}
