import { useState } from "react";
import {
  endRound,
  setAlwaysShowHands as postAlwaysShowHands,
  setForceDialogue as postForceDialogue,
  setForcedAiAction,
  type ForcedActionMode,
} from "../hooks/useGameSocket";

interface DebugWidgetProps {
  tournamentId: string;
}

const FORCED_MODES: { mode: ForcedActionMode; label: string }[] = [
  { mode: "all_in", label: "Force All-Ins" },
  { mode: "call", label: "Force Call" },
  { mode: "check", label: "Force Check" },
  { mode: "fold", label: "Force Fold" },
];

/** Debug-only controls for a mock-players (no API usage) session -- see
 * backend/app/api/session.py, which rejects every one of these requests with
 * a 403 unless the tournament was actually created in debug mode. */
export function DebugWidget({ tournamentId }: DebugWidgetProps) {
  const [activeMode, setActiveMode] = useState<ForcedActionMode | null>(null);
  const [alwaysShowHands, setAlwaysShowHands] = useState(false);
  const [forceDialogue, setForceDialogue] = useState(false);

  const toggleMode = (mode: ForcedActionMode) => {
    // clicking the already-active mode clears it back to normal random play
    const next = activeMode === mode ? null : mode;
    setActiveMode(next);
    setForcedAiAction(tournamentId, next).catch((err) => console.error(err));
  };

  const toggleAlwaysShowHands = () => {
    const next = !alwaysShowHands;
    setAlwaysShowHands(next);
    postAlwaysShowHands(tournamentId, next).catch((err) => console.error(err));
  };

  const toggleForceDialogue = () => {
    const next = !forceDialogue;
    setForceDialogue(next);
    postForceDialogue(tournamentId, next).catch((err) => console.error(err));
  };

  return (
    <div className="debug-widget">
      <div className="debug-widget__title">Debug Mode</div>
      {FORCED_MODES.map(({ mode, label }) => (
        <button
          key={mode}
          className={`debug-widget__btn${activeMode === mode ? " debug-widget__btn--active" : ""}`}
          onClick={() => toggleMode(mode)}
        >
          {label}
        </button>
      ))}
      <button
        className={`debug-widget__btn${alwaysShowHands ? " debug-widget__btn--active" : ""}`}
        onClick={toggleAlwaysShowHands}
      >
        Always Show Hands
      </button>
      <button
        className={`debug-widget__btn${forceDialogue ? " debug-widget__btn--active" : ""}`}
        onClick={toggleForceDialogue}
      >
        Force Dialogue
      </button>
      <button
        className="debug-widget__btn debug-widget__btn--danger"
        onClick={() => {
          endRound(tournamentId).catch((err) => console.error(err));
        }}
      >
        End Round
      </button>
    </div>
  );
}
