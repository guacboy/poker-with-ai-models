from __future__ import annotations

import base64
import wave
from io import BytesIO

import numpy as np

from app.tts.kokoro_tts import _samples_to_wav_base64


def _decode_peak_amplitude(encoded: str) -> int:
    with wave.open(BytesIO(base64.b64decode(encoded)), "rb") as wf:
        pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
    return int(np.abs(pcm).max())


def test_volume_scales_down_peak_amplitude() -> None:
    samples = np.array([1.0, -1.0, 0.5, -0.5], dtype=np.float32)

    full = _decode_peak_amplitude(_samples_to_wav_base64(samples, 24000, volume=1.0))
    half = _decode_peak_amplitude(_samples_to_wav_base64(samples, 24000, volume=0.5))

    assert abs(half - full // 2) <= 1


def test_volume_one_is_unchanged() -> None:
    samples = np.array([0.25, -0.25], dtype=np.float32)
    peak = _decode_peak_amplitude(_samples_to_wav_base64(samples, 24000, volume=1.0))
    assert peak == int(0.25 * 32767)
