import { useEffect, useState } from "react";
import type { ActionName, LegalActions } from "../types/game";
import { bbToChips, chipsToBB, formatBB } from "../utils/formatChips";

interface ActionControlsProps {
  legalActions: LegalActions | null;
  disabled: boolean;
  bigBlind: number;
  potTotal: number;
  // best-effort "what would I owe to call right now" read off the live table
  // state, used only while it's not actually the human's turn (so there's no
  // real legal_actions to go on yet) -- lets the pre-select row react to e.g.
  // an opponent's raise before the human's own turn ever arrives
  liveCallAmount: number;
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

// A pre-selected action, armed before it's actually the human's turn -- the
// moment a fresh legal_actions view shows up for their turn, it's resolved
// and submitted automatically without them having to click again.
type QueuedAction = "fold" | "check" | "call";

// hiddenWhenFacingBet: "Check" only makes sense with nothing to call -- once
// a bet is in front of the human (an opponent's raise, live or from their
// own last real turn), it's hidden rather than shown as a dead option.
// Fold/Call Any stay meaningful either way, so they're always shown.
const QUEUED_ACTION_PRESETS: { queued: QueuedAction; label: string; hiddenWhenFacingBet: boolean }[] = [
  { queued: "fold", label: "Fold", hiddenWhenFacingBet: false },
  { queued: "check", label: "Check", hiddenWhenFacingBet: true },
  { queued: "call", label: "Call Any", hiddenWhenFacingBet: false },
];

// Shown before the human's very first real turn of the tournament (no
// legal_actions view has ever arrived yet), so the whole panel -- Fold/Check
// placeholders, pre-select row -- is visible and lets them queue "Fold" or
// "Call Any" for their first hand, instead of showing nothing at all until
// their first actual decision. can_bet_or_raise is deliberately left false:
// with no real bet-sizing bounds to show yet, a "Bet 0.0 BB" placeholder
// would just be confusing.
const PLACEHOLDER_LEGAL_ACTIONS: LegalActions = {
  can_fold: true,
  can_check_or_call: true,
  can_bet_or_raise: false,
  call_amount: 0,
  min_bet_to: null,
  max_bet_to: null,
};

// Resolves a queued preset against the legal_actions that are actually live
// right now. Returns null when the preset doesn't apply this decision (e.g.
// "Check" queued but there's a bet to face) -- the caller drops the queue
// and falls back to the normal buttons rather than guessing.
function resolveQueuedAction(queued: QueuedAction, legal: LegalActions): ActionName | null {
  switch (queued) {
    case "fold":
      // the standard "check/fold" combo: fold if there's actually something
      // to fold to, otherwise it's a free street so just check instead
      return legal.can_fold ? "fold" : legal.can_check_or_call ? "check_or_call" : null;
    case "call":
      // commits to staying in regardless of size, including a free check
      return legal.can_check_or_call ? "check_or_call" : null;
    case "check":
      // only fires when there's genuinely nothing to call -- if a bet shows
      // up instead, this cancels itself rather than silently calling it
      return legal.call_amount === 0 && legal.can_check_or_call ? "check_or_call" : null;
  }
}

export function ActionControls({
  legalActions,
  disabled,
  bigBlind,
  potTotal,
  liveCallAmount,
  onAction,
}: ActionControlsProps) {
  const [raiseTo, setRaiseTo] = useState<number>(legalActions?.min_bet_to ?? 0);
  const [queuedAction, setQueuedAction] = useState<QueuedAction | null>(null);

  useEffect(() => {
    if (legalActions?.min_bet_to != null) setRaiseTo(legalActions.min_bet_to);
  }, [legalActions?.min_bet_to]);

  // whether there's currently something to call -- the real legal_actions
  // when it's actually the human's turn, otherwise the live best-effort read
  // off the table while waiting for their turn to come around
  const facingBet = legalActions ? legalActions.call_amount > 0 : liveCallAmount > 0;

  // fires the instant a queued preset can actually apply: either it was
  // queued while it wasn't the human's turn and their turn just arrived, or
  // they queued it while already on the clock (in which case this resolves
  // right away instead of waiting for a click on the normal buttons)
  useEffect(() => {
    if (queuedAction === null || disabled || !legalActions) return;
    const resolved = resolveQueuedAction(queuedAction, legalActions);
    setQueuedAction(null);
    if (resolved) onAction(resolved, null);
  }, [queuedAction, disabled, legalActions, onAction]);

  // a queued "Check" that stops applying (an opponent raises before the
  // human's turn arrives) disarms itself immediately, matching the button
  // disappearing from the row below, instead of sitting there as "Queued:
  // Check" with the button nowhere to be found to cancel it
  useEffect(() => {
    if (queuedAction === "check" && facingBet) setQueuedAction(null);
  }, [queuedAction, facingBet]);

  // before the human's first real turn, legalActions is null -- render the
  // same layout anyway (via the placeholder shape) so the panel, including
  // the pre-select row, is visible from the start instead of only appearing
  // once their first turn has actually happened. Buttons stay forced-disabled
  // whenever there's no real legalActions yet, regardless of the `disabled`
  // prop, so a click can't race a real view that hasn't landed yet.
  const effectiveLegalActions = legalActions ?? PLACEHOLDER_LEGAL_ACTIONS;
  const effectiveDisabled = disabled || !legalActions;

  const { can_fold, can_check_or_call, can_bet_or_raise, call_amount, min_bet_to, max_bet_to } =
    effectiveLegalActions;

  const togglePreset = (preset: QueuedAction) => {
    setQueuedAction((current) => (current === preset ? null : preset));
  };

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
    <div className={`action-controls${effectiveDisabled ? " action-controls--disabled" : ""}`}>
      <div className="action-controls__autoplay">
        <span className="action-controls__autoplay-label">
          {queuedAction ? `Queued: ${QUEUED_ACTION_PRESETS.find((p) => p.queued === queuedAction)?.label}` : "Pre-select:"}
        </span>
        {QUEUED_ACTION_PRESETS.filter((p) => !(p.hiddenWhenFacingBet && facingBet)).map(({ queued, label }) => (
          <button
            key={queued}
            type="button"
            className={`btn btn--preset${queuedAction === queued ? " btn--preset-armed" : ""}`}
            onClick={() => togglePreset(queued)}
          >
            {label}
          </button>
        ))}
      </div>
      {can_bet_or_raise && min_bet_to != null && max_bet_to != null && (
        <div className="action-controls__raise">
          <input
            type="range"
            min={min_bet_to}
            max={max_bet_to}
            value={raiseTo}
            disabled={effectiveDisabled}
            onChange={(e) => setRaiseTo(Number(e.target.value))}
          />
          <input
            type="number"
            min={chipsToBB(min_bet_to, bigBlind)}
            max={chipsToBB(max_bet_to, bigBlind)}
            step={0.1}
            value={chipsToBB(raiseTo, bigBlind)}
            disabled={effectiveDisabled}
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
              disabled={effectiveDisabled}
              onClick={() => setRaiseToChips(Math.round(potTotal * multiplier))}
            >
              {label}
            </button>
          ))}
          <button
            type="button"
            className="btn btn--preset"
            disabled={effectiveDisabled}
            onClick={() => setRaiseToChips(max_bet_to)}
          >
            All In
          </button>
        </div>
      )}
      <div className="action-controls__buttons">
        {can_fold && (
          <button
            className="btn btn--fold"
            disabled={effectiveDisabled}
            onClick={() => onAction("fold", null)}
          >
            Fold
          </button>
        )}
        {can_check_or_call && (
          <button
            className="btn btn--call"
            disabled={effectiveDisabled}
            onClick={() => onAction("check_or_call", null)}
          >
            {call_amount > 0 ? `Call ${formatBB(call_amount, bigBlind)}` : "Check"}
          </button>
        )}
        {can_bet_or_raise && (
          <button
            className="btn btn--raise"
            disabled={effectiveDisabled}
            onClick={() => onAction("bet_or_raise_to", raiseTo)}
          >
            {call_amount > 0
              ? `Raise to ${formatBB(raiseTo, bigBlind)}`
              : `Bet ${formatBB(raiseTo, bigBlind)}`}
          </button>
        )}
      </div>
      {effectiveDisabled && <div className="action-controls__waiting">Waiting for other players…</div>}
    </div>
  );
}
