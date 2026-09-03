"""Local text-to-speech via Kokoro-82M (ONNX runtime).

Model weights aren't checked into git (run `python scripts/download_tts_model.py`
once to fetch them). If they're missing, `synthesize` returns None and the app
runs fine without audio -- speech bubbles just won't be read aloud.
"""

from __future__ import annotations

import asyncio
import base64
import io
import wave
from pathlib import Path
from typing import Optional

import numpy as np

MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models" / "kokoro"
MODEL_PATH = MODEL_DIR / "kokoro-v1.0.onnx"
VOICES_PATH = MODEL_DIR / "voices-v1.0.bin"

_kokoro = None
_load_attempted = False


def _get_kokoro():
    global _kokoro, _load_attempted
    if _load_attempted:
        return _kokoro
    _load_attempted = True
    if not (MODEL_PATH.exists() and VOICES_PATH.exists()):
        return None
    from kokoro_onnx import Kokoro

    _kokoro = Kokoro(str(MODEL_PATH), str(VOICES_PATH))
    return _kokoro


def _samples_to_wav_base64(samples: np.ndarray, sample_rate: int, volume: float) -> str:
    pcm16 = (np.clip(samples * volume, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _synthesize_sync(text: str, voice: str, volume: float) -> Optional[tuple[str, float]]:
    kokoro = _get_kokoro()
    if kokoro is None:
        return None
    samples, sample_rate = kokoro.create(text, voice=voice, speed=1.0, lang="en-us")
    duration_seconds = len(samples) / sample_rate
    return _samples_to_wav_base64(samples, sample_rate, volume), duration_seconds


async def synthesize(text: str, voice: str, volume: float = 1.0) -> tuple[str, float] | None:
    """Returns (base64-encoded WAV audio, duration in seconds) for `text`, or
    None if the model isn't downloaded yet. The duration is what lets the game
    loop pace itself around how long the line actually takes to play, not just
    a guess. Synthesis is CPU-bound, so it runs off the event loop.

    `volume` scales the raw samples before they're clipped to 16-bit PCM --
    some Kokoro voices are naturally louder than others, so callers can even
    them out per-voice rather than relying on playback-side volume."""
    return await asyncio.to_thread(_synthesize_sync, text, voice, volume)
