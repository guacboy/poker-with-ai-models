import { useCallback } from "react";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

/** Plays short one-shot sound effects (betting chips, all-in crowd gasp,
 * cards, folding) served from the backend's /sounds mount. Unlike trash-talk
 * audio, these don't need to be queued -- they're brief and it's fine (often
 * more realistic) for two to overlap, e.g. a call that also turns the flop. */
export function useSoundEffects() {
  const play = useCallback((filename: string) => {
    const audio = new Audio(`${API_BASE}/sounds/${filename}`);
    audio.play().catch(() => {
      // autoplay can be blocked before the user has interacted with the
      // page yet -- nothing to do about a single missed sound effect
    });
  }, []);

  return { play };
}
