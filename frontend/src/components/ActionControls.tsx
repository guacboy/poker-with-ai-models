import { useEffect, useState } from "react";
import type { ActionName, LegalActions } from "../types/game";

interface ActionControlsProps {
  legalActions: LegalActions | null;
  onAction: (action: ActionName, amount: number | null) => void;
}

export function ActionControls({ legalActions, onAction }: ActionControlsProps) {
  const [raiseTo, setRaiseTo] = useState<number>(legalActions?.min_bet_to ?? 0);

  useEffect(() => {
    if (legalActions?.min_bet_to != null) setRaiseTo(legalActions.min_bet_to);
  }, [legalActions?.min_bet_to]);

  if (!legalActions) {
    return <div className="action-controls action-controls--waiting">Waiting for other players…</div>;
  }

  const { can_fold, can_check_or_call, can_bet_or_raise, call_amount, min_bet_to, max_bet_to } =
    legalActions;

  return (
    <div className="action-controls">
      {can_bet_or_raise && min_bet_to != null && max_bet_to != null && (
        <div className="action-controls__raise">
          <input
            type="range"
            min={min_bet_to}
            max={max_bet_to}
            value={raiseTo}
            onChange={(e) => setRaiseTo(Number(e.target.value))}
          />
          <input
            type="number"
            min={min_bet_to}
            max={max_bet_to}
            value={raiseTo}
            onChange={(e) => setRaiseTo(Number(e.target.value))}
          />
        </div>
      )}
      <div className="action-controls__buttons">
        {can_fold && (
          <button className="btn btn--fold" onClick={() => onAction("fold", null)}>
            Fold
          </button>
        )}
        {can_check_or_call && (
          <button className="btn btn--call" onClick={() => onAction("check_or_call", null)}>
            {call_amount > 0 ? `Call ${call_amount.toLocaleString()}` : "Check"}
          </button>
        )}
        {can_bet_or_raise && (
          <button className="btn btn--raise" onClick={() => onAction("bet_or_raise_to", raiseTo)}>
            {call_amount > 0 ? `Raise to ${raiseTo.toLocaleString()}` : `Bet ${raiseTo.toLocaleString()}`}
          </button>
        )}
      </div>
    </div>
  );
}
