import { useEffect, useState } from "react";
import type { ActionName, LegalActions } from "../types/game";
import { bbToChips, chipsToBB, formatBB } from "../utils/formatChips";

interface ActionControlsProps {
  legalActions: LegalActions | null;
  disabled: boolean;
  bigBlind: number;
  potTotal: number;
  onAction: (action: ActionName, amount: number | null) => void;
}

// pot-fraction quick presets for the raise-to amount -- computed off the
// current pot size, not a "true" pot-sized-raise formula (which would also
// factor in the call amount); simple multiples of the displayed pot are what
// was asked for and are what a player glancing at the pot total expects
const POT_PRESETS: { label: string; multiplier: number }[] = [
  { label: "1/2 Pot", multiplier: 0.5 },
  { label: "Pot", multiplier: 1 },
  { label: "2x Pot", multiplier: 2 },
];

export function ActionControls({ legalActions, disabled, bigBlind, potTotal, onAction }: ActionControlsProps) {
  const [raiseTo, setRaiseTo] = useState<number>(legalActions?.min_bet_to ?? 0);

  useEffect(() => {
    if (legalActions?.min_bet_to != null) setRaiseTo(legalActions.min_bet_to);
  }, [legalActions?.min_bet_to]);

  // nothing has ever come through yet (e.g. the very first hand hasn't
  // reached the human's turn) -- there's no legal-actions shape to render
  // even in a disabled/placeholder form yet
  if (!legalActions) {
    return <div className="action-controls action-controls--waiting">Waiting for other players…</div>;
  }

  const { can_fold, can_check_or_call, can_bet_or_raise, call_amount, min_bet_to, max_bet_to } =
    legalActions;

  const setRaiseToBB = (bb: number) => {
    if (min_bet_to == null || max_bet_to == null) return;
    const chips = Math.max(min_bet_to, Math.min(max_bet_to, bbToChips(bb, bigBlind)));
    setRaiseTo(chips);
  };

  const setRaiseToChips = (chips: number) => {
    if (min_bet_to == null || max_bet_to == null) return;
    setRaiseTo(Math.max(min_bet_to, Math.min(max_bet_to, chips)));
  };

  return (
    <div className={`action-controls${disabled ? " action-controls--disabled" : ""}`}>
      {can_bet_or_raise && min_bet_to != null && max_bet_to != null && (
        <div className="action-controls__raise">
          <input
            type="range"
            min={min_bet_to}
            max={max_bet_to}
            value={raiseTo}
            disabled={disabled}
            onChange={(e) => setRaiseTo(Number(e.target.value))}
          />
          <input
            type="number"
            min={chipsToBB(min_bet_to, bigBlind)}
            max={chipsToBB(max_bet_to, bigBlind)}
            step={0.1}
            value={chipsToBB(raiseTo, bigBlind)}
            disabled={disabled}
            onChange={(e) => setRaiseToBB(Number(e.target.value))}
          />
          <span className="action-controls__unit">BB</span>
        </div>
      )}
      {can_bet_or_raise && min_bet_to != null && max_bet_to != null && (
        <div className="action-controls__presets">
          {POT_PRESETS.map(({ label, multiplier }) => (
            <button
              key={label}
              type="button"
              className="btn btn--preset"
              disabled={disabled}
              onClick={() => setRaiseToChips(Math.round(potTotal * multiplier))}
            >
              {label}
            </button>
          ))}
          <button
            type="button"
            className="btn btn--preset"
            disabled={disabled}
            onClick={() => setRaiseToChips(max_bet_to)}
          >
            All In
          </button>
        </div>
      )}
      <div className="action-controls__buttons">
        {can_fold && (
          <button className="btn btn--fold" disabled={disabled} onClick={() => onAction("fold", null)}>
            Fold
          </button>
        )}
        {can_check_or_call && (
          <button
            className="btn btn--call"
            disabled={disabled}
            onClick={() => onAction("check_or_call", null)}
          >
            {call_amount > 0 ? `Call ${formatBB(call_amount, bigBlind)}` : "Check"}
          </button>
        )}
        {can_bet_or_raise && (
          <button
            className="btn btn--raise"
            disabled={disabled}
            onClick={() => onAction("bet_or_raise_to", raiseTo)}
          >
            {call_amount > 0
              ? `Raise to ${formatBB(raiseTo, bigBlind)}`
              : `Bet ${formatBB(raiseTo, bigBlind)}`}
          </button>
        )}
      </div>
      {disabled && <div className="action-controls__waiting">Waiting for other players…</div>}
    </div>
  );
}
