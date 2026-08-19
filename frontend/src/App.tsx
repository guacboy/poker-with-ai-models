import { useEffect, useRef, useState } from "react";
import "./App.css";
import { ActionControls } from "./components/ActionControls";
import type { SeatViewModel } from "./components/Seat";
import { Table } from "./components/Table";
import { TournamentStatus } from "./components/TournamentStatus";
import { useAudioQueue } from "./hooks/useAudioQueue";
import { createTournament, useGameSocket } from "./hooks/useGameSocket";

const SPEECH_BUBBLE_DURATION_MS = 4500;

function StartScreen({ onStart }: { onStart: (name: string) => void }) {
  const [name, setName] = useState("You");
  return (
    <div className="start-screen">
      <h1>AI Poker Table</h1>
      <p>No-Limit Hold'em, 6-max, against Claude, OpenAI, DeepSeek, Gemini, and Grok.</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onStart(name.trim() || "You");
        }}
      >
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={20} />
        <button type="submit">Start Tournament</button>
      </form>
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
      setSpeechMessages((prev) => ({ ...prev, [action.playerId]: action.message }));
      clearTimeout(timeoutsRef.current[action.playerId]);
      timeoutsRef.current[action.playerId] = setTimeout(() => {
        setSpeechMessages((prev) => ({ ...prev, [action.playerId]: null }));
      }, SPEECH_BUBBLE_DURATION_MS);
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

  const seats: SeatViewModel[] = publicState.players.map((player) => {
    const handSeat = publicState.hand?.seats.find((s) => s.player_id === player.player_id);
    return {
      playerId: player.player_id,
      name: player.name,
      kind: player.kind,
      status: player.status,
      stack: player.stack,
      bet: handSeat?.bet ?? 0,
      folded: handSeat?.folded ?? false,
      isButton: handSeat?.is_button ?? false,
      isSmallBlind: handSeat?.is_small_blind ?? false,
      isBigBlind: handSeat?.is_big_blind ?? false,
      isToAct: handSeat?.is_to_act ?? false,
      holeCards: handSeat?.hole_cards ?? null,
      buyInsUsed: player.buy_ins_used,
      buyInsRemaining: player.buy_ins_remaining,
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
          boardCards={publicState.hand?.board_cards ?? []}
          potTotal={publicState.hand?.pot_total ?? 0}
        />

        <ActionControls
          legalActions={isMyTurn ? state.actorView!.legal_actions : null}
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
        onStart={async (name) => {
          const result = await createTournament(name);
          setSession(result);
        }}
      />
    );
  }

  return <GameScreen tournamentId={session.tournamentId} humanPlayerId={session.humanPlayerId} />;
}
