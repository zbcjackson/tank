"""Unit tests for TTS output resampling (adaptive per-client sample rate).

The :func:`tank_backend.api.router._resample_pcm16` helper adapts TTS
audio (native rate, e.g. 24kHz) to a client's requested output rate
(e.g. a hardware device fixed at 16kHz). It's pure, so we exercise it
directly rather than spinning up a WebSocket session.
"""

from __future__ import annotations

import numpy as np

from tank_backend.api.router import _resample_pcm16


def _pcm(samples: list[int]) -> bytes:
    return np.array(samples, dtype=np.int16).tobytes()


def test_same_rate_returns_input_unchanged():
    data = _pcm([1, 2, 3, 4])
    assert _resample_pcm16(data, 16000, 16000) is data


def test_empty_input_returns_input():
    assert _resample_pcm16(b"", 24000, 16000) == b""


def test_downsample_24k_to_16k_reduces_sample_count():
    # 24 samples at 24kHz -> ~16 samples at 16kHz (2:3 ratio)
    src = _pcm(list(range(24)))
    out = _resample_pcm16(src, 24000, 16000)
    out_samples = np.frombuffer(out, dtype=np.int16)
    assert out_samples.size == 16


def test_resample_preserves_duration_within_tolerance():
    # 1 second of audio at 24kHz should stay ~1 second at 16kHz.
    src = _pcm([0] * 24000)
    out = _resample_pcm16(src, 24000, 16000)
    out_samples = np.frombuffer(out, dtype=np.int16)
    assert abs(out_samples.size - 16000) <= 1


def test_resample_output_is_int16():
    src = _pcm([100, 200, 300, 400, 500, 600])
    out = _resample_pcm16(src, 24000, 16000)
    assert len(out) % 2 == 0  # valid int16 byte buffer
    out_samples = np.frombuffer(out, dtype=np.int16)
    assert out_samples.dtype == np.int16


def test_resample_endpoints_match_source():
    # Linear interpolation keeps the first and last samples intact.
    src = _pcm([1000, 2000, 3000, 4000, 5000, 6000])
    out = np.frombuffer(_resample_pcm16(src, 24000, 16000), dtype=np.int16)
    assert out[0] == 1000
    assert out[-1] == 6000
