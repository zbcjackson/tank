"""Tests for CLI opus codecs (protocol plan P1-2 Step 4).

Round-trip quality uses the aligned-SNR method from the binding-selection
spike (speech-shaped noise + FFT integer alignment) with the server's
32 kbps threshold — the same helper as backend ``test_ws_opus.py``.
"""

from __future__ import annotations

import numpy as np
import opuslib
import pytest

from tank_cli.audio.opus_codec import (
    DOWNLINK_SAMPLE_RATE,
    ClientCodecs,
    OpusDecodeError,
    OpusDownlinkDecoder,
    OpusUplinkEncoder,
    create_client_codecs,
)

UPLINK_RATE = 16000
UPLINK_FRAME_SAMPLES = UPLINK_RATE * 20 // 1000
DOWNLINK_FRAME_SAMPLES = DOWNLINK_SAMPLE_RATE * 20 // 1000


def _speech_noise(n: int, rate: int, seed: int = 7) -> np.ndarray:
    """Band-limited (300-3400 Hz), syllabically enveloped noise — speech
    statistics, aperiodic so correlation alignment is unambiguous."""
    rng = np.random.default_rng(seed)
    t = np.arange(n) / rate
    spec = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n, 1 / rate)
    spec[(freqs < 300) | (freqs > 3400)] = 0
    sig = np.fft.irfft(spec, n)
    env = 0.5 + 0.5 * np.abs(np.sin(2 * np.pi * 3 * t)) ** 0.7
    sig = sig / max(float(np.max(np.abs(sig))), 1e-9) * 0.5 * env
    return (sig * 32767).astype(np.int16)


def _aligned_snr(ref: np.ndarray, deg: np.ndarray) -> float:
    """SNR after FFT integer alignment (``deg`` is a delayed copy of ``ref``)."""
    n = min(len(ref), len(deg))
    ref = ref[:n].astype(np.float64)
    deg = deg[:n].astype(np.float64)
    size = 1 << int(np.ceil(np.log2(2 * n)))
    corr = np.fft.irfft(np.fft.rfft(ref, size) * np.conj(np.fft.rfft(deg, size)), size)
    lag = int(np.argmax(corr))
    if lag > size // 2:
        lag -= size
    if lag >= 0:
        a, b = ref[lag:], deg[: n - lag]
    else:
        a, b = ref[: n + lag], deg[-lag:]
    m = min(len(a), len(b))
    err = a[:m] - b[:m]
    return float(
        10 * np.log10(float((a[:m] ** 2).sum()) / max(float((err**2).sum()), 1e-9))
    )


# ---------------------------------------------------------------------------
# Uplink encoder
# ---------------------------------------------------------------------------


def test_uplink_feed_rebuffers_arbitrary_chunks():
    """Any chunk boundaries in, exactly one packet per 20 ms frame out."""
    enc = OpusUplinkEncoder()
    pcm = _speech_noise(UPLINK_FRAME_SAMPLES * 5, UPLINK_RATE).tobytes()

    assert enc.feed(pcm[:100]) == []  # residue only
    packets = enc.feed(pcm[100:])
    assert len(packets) == 5
    for p in packets:
        assert 0 < len(p) <= 1275  # opus packet cap


def test_uplink_roundtrip_snr():
    """Encode → decode (server-side view) at ≥ the 32 kbps SNR threshold."""
    enc = OpusUplinkEncoder()
    pcm = _speech_noise(UPLINK_RATE, UPLINK_RATE)  # 1 s
    packets = enc.feed(pcm.tobytes())
    assert len(packets) == 50

    dec = opuslib.Decoder(UPLINK_RATE, 1)
    out = b"".join(dec.decode(p, UPLINK_FRAME_SAMPLES * 6) for p in packets)
    decoded = np.frombuffer(out, dtype=np.int16)
    assert _aligned_snr(pcm, decoded) >= 10.0


# ---------------------------------------------------------------------------
# Downlink decoder
# ---------------------------------------------------------------------------


def test_downlink_roundtrip_snr():
    """Server-side-encoded packets decode at ≥ the 32 kbps SNR threshold."""
    enc = opuslib.Encoder(DOWNLINK_SAMPLE_RATE, 1, opuslib.APPLICATION_AUDIO)
    enc.bitrate = 32000
    pcm = _speech_noise(DOWNLINK_SAMPLE_RATE, DOWNLINK_SAMPLE_RATE)  # 1 s @24k
    packets = [
        enc.encode(
            pcm[i : i + DOWNLINK_FRAME_SAMPLES].tobytes(), DOWNLINK_FRAME_SAMPLES
        )
        for i in range(0, len(pcm) - DOWNLINK_FRAME_SAMPLES + 1, DOWNLINK_FRAME_SAMPLES)
    ]

    dec = OpusDownlinkDecoder()
    out = b"".join(dec.decode_packet(p) for p in packets)
    decoded = np.frombuffer(out, dtype=np.int16)
    assert _aligned_snr(pcm, decoded) >= 10.0


def test_downlink_decodes_variable_duration_packets():
    """A 40 ms packet (like Chrome's variable-duration uplink, but here on
    the downlink path) decodes to its full sample count, not an error."""
    enc = opuslib.Encoder(DOWNLINK_SAMPLE_RATE, 1, opuslib.APPLICATION_AUDIO)
    pcm = _speech_noise(DOWNLINK_FRAME_SAMPLES * 2, DOWNLINK_SAMPLE_RATE)
    packet = enc.encode(pcm.tobytes(), DOWNLINK_FRAME_SAMPLES * 2)

    dec = OpusDownlinkDecoder()
    out = dec.decode_packet(packet)
    assert len(out) >= DOWNLINK_FRAME_SAMPLES * 2 * 2


def test_downlink_garbage_packet_raises_decode_error():
    dec = OpusDownlinkDecoder()
    dec.decode_packet(b"")  # empty is a valid PLC trigger, must not raise
    with pytest.raises(OpusDecodeError):
        dec.decode_packet(b"\xff" * 200)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_create_client_codecs():
    codecs = create_client_codecs()
    assert isinstance(codecs, ClientCodecs)
    assert isinstance(codecs.uplink, OpusUplinkEncoder)
    assert isinstance(codecs.downlink, OpusDownlinkDecoder)
