import { useEffect, useRef, useState } from "react";
import "./App.css";
import { ActionControls } from "./components/ActionControls";
import type { SeatViewModel } from "./components/Seat";
import { Table } from "./components/Table";
import { TournamentStatus } from "./components/TournamentStatus";
import {
  PLACEHOLDER_BIG_BLIND,
  PLACEHOLDER_PLAYERS,
  PLACEHOLDER_SEATS,
  PLACEHOLDER_SMALL_BLIND,
} from "./data/placeholderTable";
import { useAudioQueue } from "./hooks/useAudioQueue";
import { createTournament, useGameSocket } from "./hooks/useGameSocket";

// Fallback when there's no audio duration to go on (e.g. TTS isn't downloaded).
const FALLBACK_SPEECH_BUBBLE_DURATION_MS = 4500;
// Matches the backend's AUDIO_TRAILING_DELAY_SECONDS default -- how much
// longer the line lingers on screen after it finishes playing.
const AUDIO_TRAILING_DELAY_MS = 1000;

// Shows the real table layout (dimmed, inert) as a backdrop instead of a
// blank splash screen -- `starting` lifts the dim and hides the button the
// instant it's clicked, so the table visibly brightens while the tournament
// is created underneath, rather than cutting straight to a loading screen.
function StartOverlay({ onStart, starting }: { onStart: () => void; starting: boolean }) {
  return (
    <div className="start-overlay">
      <div
        className={`start-overlay__backdrop game-screen${starting ? " start-overlay__backdrop--bright" : ""}`}
        aria-hidden="true"
        inert={!starting ? true : undefined}
      >
        <TournamentStatus
          handCount={0}
          smallBlind={PLACEHOLDER_SMALL_BLIND}
          bigBlind={PLACEHOLDER_BIG_BLIND}
          handsUntilNextLevel={10}
          players={PLACEHOLDER_PLAYERS}
          humanPlayerId="human"
        />
        <div className="game-main">
          <Table
            seats={PLACEHOLDER_SEATS}
            speechMessages={{}}
            boardCards={[]}
            potTotal={0}
            bigBlind={PLACEHOLDER_BIG_BLIND}
            winningHandLabel={null}
          />
          <ActionControls legalActions={null} disabled bigBlind={PLACEHOLDER_BIG_BLIND} onAction={() => {}} />
        </div>
      </div>
      {!starting && (
        <div className="start-overlay__scrim">
          <button className="start-overlay__button" onClick={onStart}>
            Start Tournament
          </button>
        </div>
      )}
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

  // while a just-finished hand's result is on screen, keep rendering its
  // frozen board/cards instead of publicState.hand, which goes null the
  // instant the hand ends
  const isHandResult = state.handResultWinners !== null;
  const displayHand = isHandResult ? state.lastHandSnapshot : state.publicState?.hand ?? null;

  const publicState = state.publicState;
  if (!publicState) {
    return <div className="loading-screen">Connecting…</div>;
  }

  const seats: SeatViewModel[] = publicState.players.map((player) => {
    const handSeat = displayHand?.seats.find((s) => s.player_id === player.player_id);
    const isWinner = isHandResult && (state.handResultWinners?.includes(player.player_id) ?? false);
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
      isWinner,
      // once the result is on screen (river shown, hand decided), dim every
      // other hand's cards to contrast with the winner's glow
      isShowdownLoser: isHandResult && !isWinner,
    };
  });

  // derived from the broadcast state (not state.actorView -- that's only
  // refreshed the instant it's the human's turn, whereas current_actor_id is
  // kept up to date on every event) so it flips false the moment an opponent
  // starts acting, not just whenever the human's own view happens to update
  const isMyTurn = publicState.hand?.current_actor_id === humanPlayerId;

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
          speechMessages={speechMessages}
          boardCards={displayHand?.board_cards ?? []}
          potTotal={displayHand?.pot_total ?? 0}
          bigBlind={publicState.big_blind}
          winningHandLabel={state.winningHandLabel}
        />

        <ActionControls
          legalActions={state.actorView?.legal_actions ?? null}
          disabled={!isMyTurn}
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
  const [starting, setStarting] = useState(false);

  if (!session) {
    return (
      <StartOverlay
        starting={starting}
        onStart={async () => {
          setStarting(true);
          try {
            const result = await createTournament();
            setSession(result);
          } catch (err) {
            console.error(err);
            setStarting(false);
          }
        }}
      />
    );
  }

  return <GameScreen tournamentId={session.tournamentId} humanPlayerId={session.humanPlayerId} />;
}
