import { useCallback, useEffect, useRef } from "react";

/** Plays base64-encoded WAV clips one at a time, so overlapping trash talk
 * doesn't collide. `enqueue` is safe to call while a clip is already playing. */
export function useAudioQueue() {
  const queueRef = useRef<string[]>([]);
  const playingRef = useRef(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const playNext = useCallback(() => {
    const next = queueRef.current.shift();
    if (!next) {
      playingRef.current = false;
      return;
    }
    playingRef.current = true;
    const audio = new Audio(`data:audio/wav;base64,${next}`);
    audioRef.current = audio;
    audio.onended = playNext;
    audio.onerror = playNext;
    audio.play().catch(playNext);
  }, []);

  const enqueue = useCallback(
    (base64Wav: string) => {
      queueRef.current.push(base64Wav);
      if (!playingRef.current) playNext();
    },
    [playNext]
  );

  useEffect(() => {
    return () => {
      audioRef.current?.pause();
      queueRef.current = [];
    };
  }, []);

  return { enqueue };
}
