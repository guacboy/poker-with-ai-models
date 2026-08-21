import type { ServerEvent } from "../types/game";

const BETTING_SOUNDS = ["betting-1.mp3", "betting-2.mp3", "betting-3.mp3"];

function randomBettingSound(): string {
  return BETTING_SOUNDS[Math.floor(Math.random() * BETTING_SOUNDS.length)];
}

export interface SoundEffectTrackingState {
  boardLen: number;
  // the biggest starting-hand stack that has gone all-in (and gasped) so far
  // this hand -- -1 means nobody has yet
  maxAllInStack: number;
}

export const INITIAL_SOUND_EFFECT_TRACKING_STATE: SoundEffectTrackingState = {
  boardLen: 0,
  maxAllInStack: -1,
};

export interface SoundEffectResult {
  sounds: string[];
  next: SoundEffectTrackingState;
}

/** Picks the sound effect(s) (if any) a server event should trigger, given
 * tracking state threaded in from the previous call (callers pass the
 * returned `next` back in as `prev` for the following event).
 *
 * "cards.mp3" covers both hole cards being dealt (hand_started) and any new
 * community card(s) appearing, whether that's a normal single-street reveal
 * bundled into a player_action broadcast or a staged street during an all-in
 * runout (board_dealt). A single action can both reveal cards *and* place a
 * bet/fold (e.g. the call that closes betting and turns the flop) -- when
 * that happens both sounds play together, same as it would at a real table.
 *
 * "crowd-gasp.mp3" only plays for the first all-in of a hand, or a later one
 * that shoves for *more* than any all-in seen so far this hand (a bigger
 * stack re-raising over the top) -- a short stack merely calling an existing
 * all-in doesn't re-trigger it, but still gets a betting sound instead so
 * the chips going in aren't silent.
 *
 * "check.mp3" plays for a free check_or_call (call_amount of 0 -- no chips
 * actually go in), which otherwise wouldn't make any sound at all.
 *
 * hand_result reuses one of the same betting sounds to simulate the pot
 * actually being pushed to the winner(s) -- same sound whether it's a single
 * winner or a chopped pot, since either way chips are physically moving. A
 * forfeited hand (debug "End Round", `winners` empty) stays silent -- nobody
 * actually won anything to push chips toward. */
export function soundEffectForEvent(
  event: ServerEvent,
  prev: SoundEffectTrackingState
): SoundEffectResult {
  switch (event.type) {
    case "hand_started":
      return {
        sounds: ["cards.mp3"],
        next: { boardLen: event.state.hand?.board_cards.length ?? 0, maxAllInStack: -1 },
      };

    case "board_dealt":
      return { sounds: ["cards.mp3"], next: { ...prev, boardLen: event.board_cards.length } };

    case "player_action": {
      const newBoardLen = event.state.hand?.board_cards.length ?? prev.boardLen;
      const sounds: string[] = [];
      let maxAllInStack = prev.maxAllInStack;

      if (newBoardLen > prev.boardLen) {
        sounds.push("cards.mp3");
      }

      if (event.action === "fold") {
        sounds.push("folding.mp3");
      } else if (event.action === "check_or_call" && event.call_amount === 0) {
        sounds.push("check.mp3");
      } else {
        // reaching here means either a bet/raise, or a call over a real
        // amount -- chips are always going in
        const resultingStack =
          event.state.hand?.seats.find((s) => s.player_id === event.player_id)?.stack ?? -1;
        if (resultingStack === 0) {
          // a stack of 0 means they just shoved everything they had --
          // their PublicPlayer.stack (unchanged since hand_started) is
          // exactly how big that shove was
          const startingStack =
            event.state.players.find((p) => p.player_id === event.player_id)?.stack ?? 0;
          if (startingStack > maxAllInStack) {
            sounds.push("crowd-gasp.mp3");
            maxAllInStack = startingStack;
          } else {
            // covering/calling an existing bigger all-in still puts chips
            // in, it just isn't a new biggest shove worth a crowd gasp
            sounds.push(randomBettingSound());
          }
        } else {
          sounds.push(randomBettingSound());
        }
      }

      return { sounds, next: { boardLen: newBoardLen, maxAllInStack } };
    }

    case "hand_result":
      return { sounds: event.winners.length > 0 ? [randomBettingSound()] : [], next: prev };

    default:
      return { sounds: [], next: prev };
  }
}
