import { useCallback, useEffect, useRef } from "react";
import { BETTING_SOUNDS } from "../utils/soundEffects";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

// Every effect file the game can ever request -- preloaded as soon as the
// hook mounts (see below) so play() isn't the first time the browser fetches
// them.
const SOUND_FILES = [...BETTING_SOUNDS, "cards.mp3", "check.mp3", "crowd-gasp.mp3", "folding.mp3"];

/** Plays short one-shot sound effects (betting chips, all-in crowd gasp,
 * cards, folding, check). Unlike trash-talk audio, these don't need to be
 * queued -- they're brief and it's fine (often more realistic) for two to
 * overlap, e.g. a call that also turns the flop.
 *
 * Each file gets one `<audio preload="auto">` element created up front, so
 * the browser starts fetching/buffering it immediately instead of on first
 * play. play() reuses that element directly when it's idle (the common
 * case -- genuinely zero fetch/decode delay, since it's already loaded), and
 * only falls back to `new Audio(url)` when the same sound is still playing
 * from a moment ago and needs to overlap itself. Without the preload, a
 * fresh `new Audio(url)` per call had to fetch over the network before it
 * could play at all -- most noticeable on check.mp3, where the table had
 * often already highlighted the next player's turn by the time the sound
 * caught up. */
export function useSoundEffects() {
  const preloadedRef = useRef<Map<string, HTMLAudioElement>>(new Map());

  const getPreloaded = useCallback((filename: string): HTMLAudioElement => {
    let audio = preloadedRef.current.get(filename);
    if (!audio) {
      audio = new Audio(`${API_BASE}/sounds/${filename}`);
      audio.preload = "auto";
      preloadedRef.current.set(filename, audio);
    }
    return audio;
  }, []);

  useEffect(() => {
    SOUND_FILES.forEach(getPreloaded);
  }, [getPreloaded]);

  const play = useCallback(
    (filename: string) => {
      const base = getPreloaded(filename);
      const instance = base.paused ? base : (base.cloneNode(true) as HTMLAudioElement);
      if (instance !== base) {
        instance.play().catch(() => {});
        return;
      }
      instance.currentTime = 0;
      instance.play().catch(() => {
        // autoplay can be blocked before the user has interacted with the
        // page yet -- nothing to do about a single missed sound effect
      });
    },
    [getPreloaded]
  );

  return { play };
}
