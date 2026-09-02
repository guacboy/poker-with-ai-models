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
  // same idea as liveCallAmount, but for the raise-to bounds: a rough "min
  // raise" (current live highest bet + one big blind) and "max raise" (the
  // human's own current bet + stack, i.e. shoving all in), so the raise
  // slider/presets/pre-select can be shown and used before the human's first
  // real turn ever arrives, instead of staying hidden until then
  liveMinRaiseTo: number;
  liveMaxRaiseTo: number;
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
// and submitted automatically without them having to click again. "raise"
// fires "bet_or_raise_to" using whatever the raise-to slider/inputs are set
// to at the moment it resolves, not a fixed amount picked when it was armed.
type QueuedAction = "fold" | "check" | "call" | "raise";

// Resolves a queued preset against the legal_actions that are actually live
// right now. Returns null when the preset doesn't apply this decision (e.g.
// "Check" queued but there's a bet to face) -- the caller drops the queue
// and falls back to the normal buttons rather than guessing.
function resolveQueuedAction(
  queued: QueuedAction,
  legal: LegalActions,
  raiseTo: number
): { action: ActionName; amount: number | null } | null {
  switch (queued) {
    case "fold":
      // the standard "check/fold" combo: fold if there's actually something
      // to fold to, otherwise it's a free street so just check instead
      if (legal.can_fold) return { action: "fold", amount: null };
      return legal.can_check_or_call ? { action: "check_or_call", amount: null } : null;
    case "call":
      // commits to staying in regardless of size, including a free check
      return legal.can_check_or_call ? { action: "check_or_call", amount: null } : null;
    case "check":
      // only fires when there's genuinely nothing to call -- if a bet shows
      // up instead, this cancels itself rather than silently calling it
      return legal.call_amount === 0 && legal.can_check_or_call
        ? { action: "check_or_call", amount: null }
        : null;
    case "raise":
      if (!legal.can_bet_or_raise || legal.min_bet_to == null || legal.max_bet_to == null) return null;
      return {
        action: "bet_or_raise_to",
        amount: Math.max(legal.min_bet_to, Math.min(legal.max_bet_to, raiseTo)),
      };
  }
}

export function ActionControls({
  legalActions,
  disabled,
  bigBlind,
  potTotal,
  liveCallAmount,
  liveMinRaiseTo,
  liveMaxRaiseTo,
  onAction,
}: ActionControlsProps) {
  const [raiseTo, setRaiseTo] = useState<number>(legalActions?.min_bet_to ?? liveMinRaiseTo);
  const [queuedAction, setQueuedAction] = useState<QueuedAction | null>(null);

  // Resets the raise-to amount back to the new minimum whenever a fresh
  // decision's bounds show up (including the transition from "waiting" into
  // the human's real turn) -- except while "Raise" is actively queued, where
  // resetting here would silently blow away the amount the human deliberately
  // dialed in while waiting, right before the queue-resolution effect below
  // gets a chance to fire with it.
  useEffect(() => {
    if (legalActions?.min_bet_to == null || queuedAction === "raise") return;
    setRaiseTo(legalActions.min_bet_to);
  }, [legalActions?.min_bet_to, queuedAction]);

  // whether there's currently something to call -- the real legal_actions
  // when it's actually the human's turn, otherwise the live best-effort read
  // off the table while waiting for their turn to come around
  const facingBet = legalActions ? legalActions.call_amount > 0 : liveCallAmount > 0;

  // fires the instant a queued preset can actually apply: either it was
  // queued while it wasn't the human's turn and their turn just arrived, or
  // they queued it while already on the clock (in which case this resolves
  // right away instead of waiting for a click on the normal buttons). Reads
  // the current `raiseTo` at resolution time, not whatever it was when
  // "raise" got queued, so adjusting the amount while waiting still counts.
  useEffect(() => {
    if (queuedAction === null || disabled || !legalActions) return;
    const resolved = resolveQueuedAction(queuedAction, legalActions, raiseTo);
    setQueuedAction(null);
    if (resolved) onAction(resolved.action, resolved.amount);
  }, [queuedAction, disabled, legalActions, raiseTo, onAction]);

  // a queued "Check" that stops applying (an opponent raises before the
  // human's turn arrives) disarms itself immediately, matching the button
  // disappearing from the row below, instead of sitting there as "Queued:
  // Check" with the button nowhere to be found to cancel it
  useEffect(() => {
    if (queuedAction === "check" && facingBet) setQueuedAction(null);
  }, [queuedAction, facingBet]);

  // before the human's first real turn, legalActions is null -- render the
  // same layout anyway (via a placeholder shape, using the live best-effort
  // call/raise reads) so the whole panel, including the raise slider/presets
  // and the pre-select row, is visible from the start instead of only
  // appearing once their first turn has actually happened. Buttons stay
  // forced-disabled whenever there's no real legalActions yet, regardless of
  // the `disabled` prop, so a click can't race a real view that hasn't
  // landed yet.
  const effectiveLegalActions: LegalActions =
    legalActions ?? {
      can_fold: true,
      can_check_or_call: true,
      can_bet_or_raise: liveMaxRaiseTo > liveMinRaiseTo,
      call_amount: liveCallAmount,
      min_bet_to: liveMinRaiseTo,
      max_bet_to: liveMaxRaiseTo,
    };
  const effectiveDisabled = disabled || !legalActions;

  const { can_fold, can_check_or_call, can_bet_or_raise, call_amount, min_bet_to, max_bet_to } =
    effectiveLegalActions;

  // The real min_bet_to/max_bet_to are null whenever can_bet_or_raise is
  // false (e.g. the human is already all in) -- fall back to the same live
  // best-effort bounds used before the human's first turn, purely so the
  // slider/presets still have a range to render (disabled) instead of
  // needing to unmount rather than just grey out.
  const displayMinBetTo = min_bet_to ?? liveMinRaiseTo;
  const displayMaxBetTo = max_bet_to ?? liveMaxRaiseTo;

  const togglePreset = (preset: QueuedAction) => {
    setQueuedAction((current) => (current === preset ? null : preset));
  };

  const setRaiseToBB = (bb: number) => {
    const chips = Math.max(displayMinBetTo, Math.min(displayMaxBetTo, bbToChips(bb, bigBlind)));
    setRaiseTo(chips);
  };

  const setRaiseToChips = (chips: number) => {
    setRaiseTo(Math.max(displayMinBetTo, Math.min(displayMaxBetTo, chips)));
  };

  return (
    <div className={`action-controls${effectiveDisabled ? " action-controls--disabled" : ""}`}>
      {/* Pre-selecting only makes sense while it's NOT actually the human's
          turn -- this label (and the pre-select buttons below, in place of
          the real ones) only shows up while waiting, and gives way to the
          real controls the instant it's actually their turn. Which one (if
          any) is armed is shown by the buttons themselves (see
          btn--preselect-armed below), not repeated here as text. */}
      {effectiveDisabled && <div className="action-controls__autoplay-label">Waiting for other players…</div>}
      {/* Always mounted, even when raising isn't currently possible (no real
          bet-sizing bounds yet, or the human is already all in) -- disabled
          rather than removed, so the layout doesn't jump depending on the
          decision. */}
      <div className="action-controls__raise">
        <input
          type="range"
          min={displayMinBetTo}
          max={displayMaxBetTo}
          value={raiseTo}
          disabled={!can_bet_or_raise}
          onChange={(e) => setRaiseTo(Number(e.target.value))}
        />
        <input
          type="number"
          min={chipsToBB(displayMinBetTo, bigBlind)}
          max={chipsToBB(displayMaxBetTo, bigBlind)}
          step={0.1}
          value={chipsToBB(raiseTo, bigBlind)}
          disabled={!can_bet_or_raise}
          onChange={(e) => setRaiseToBB(Number(e.target.value))}
        />
        <span className="action-controls__unit">BB</span>
      </div>
      <div className="action-controls__presets">
        {POT_PRESETS.map(({ label, multiplier }) => (
          <button
            key={label}
            type="button"
            className="btn btn--preset"
            disabled={!can_bet_or_raise}
            onClick={() => setRaiseToChips(Math.round(potTotal * multiplier))}
          >
            {label}
          </button>
        ))}
        <button
          type="button"
          className="btn btn--preset"
          disabled={!can_bet_or_raise}
          onClick={() => setRaiseToChips(displayMaxBetTo)}
        >
          All In
        </button>
      </div>
      <div className="action-controls__buttons">
        {effectiveDisabled ? (
          // All four always render while waiting, whether or not each one
          // actually applies right now (e.g. Check while already facing a
          // bet, or Raise after already shoving all in) -- an inapplicable
          // one stays in place, just greyed out and unarmable, instead of
          // disappearing from the row.
          <>
            <button
              type="button"
              className={`btn btn--fold btn--preselect${queuedAction === "fold" ? " btn--preselect-armed" : ""}`}
              disabled={!can_fold}
              onClick={() => togglePreset("fold")}
            >
              Fold
            </button>
            <button
              type="button"
              className={`btn btn--call btn--preselect${queuedAction === "check" ? " btn--preselect-armed" : ""}`}
              disabled={!can_check_or_call || facingBet}
              onClick={() => togglePreset("check")}
            >
              Check
            </button>
            <button
              type="button"
              className={`btn btn--call btn--preselect${queuedAction === "call" ? " btn--preselect-armed" : ""}`}
              disabled={!can_check_or_call}
              onClick={() => togglePreset("call")}
            >
              Call Any
            </button>
            <button
              type="button"
              className={`btn btn--raise btn--preselect${queuedAction === "raise" ? " btn--preselect-armed" : ""}`}
              disabled={!can_bet_or_raise}
              onClick={() => togglePreset("raise")}
            >
              {can_bet_or_raise ? `Raise to ${formatBB(raiseTo, bigBlind)}` : "Raise"}
            </button>
          </>
        ) : (
          // Same four-button shape as the pre-select row above (Fold / Check
          // / Call / Raise), rather than merging Check and Call into one
          // relabeled button -- that merge used to make it look like the
          // Check option had vanished the instant it became your real turn
          // (four buttons while waiting, only three once it's on the clock).
          // Whichever of Check/Call doesn't apply this decision just stays in
          // place, greyed out, same as every other inapplicable option here.
          <>
            <button className="btn btn--fold" disabled={!can_fold} onClick={() => onAction("fold", null)}>
              Fold
            </button>
            <button
              className="btn btn--call"
              disabled={!can_check_or_call || call_amount > 0}
              onClick={() => onAction("check_or_call", null)}
            >
              Check
            </button>
            <button
              className="btn btn--call"
              disabled={!can_check_or_call || call_amount === 0}
              onClick={() => onAction("check_or_call", null)}
            >
              {call_amount > 0 ? `Call ${formatBB(call_amount, bigBlind)}` : "Call"}
            </button>
            <button
              className="btn btn--raise"
              disabled={!can_bet_or_raise}
              onClick={() => onAction("bet_or_raise_to", raiseTo)}
            >
              {can_bet_or_raise
                ? call_amount > 0
                  ? `Raise to ${formatBB(raiseTo, bigBlind)}`
                  : `Bet ${formatBB(raiseTo, bigBlind)}`
                : "Raise"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
