"""P1-2 Step 2: server-side opus negotiation and codec paths.

Layers covered:

- ``audio/opus_codec.py`` — rebuffering downlink encoder + uplink decoder,
  round-trip quality (aligned SNR — the method from the binding-selection
  spike: speech-shaped noise, FFT integer alignment; pure tones alias and
  white noise sits at ~0 dB, so neither is usable here), stale-residue
  reset after an interrupt gap.
- ``signal_handlers.handle_capabilities`` — the real negotiation: ack with
  the enabled set + opus profile, codec registration, warn-and-ignore for
  unknown/unavailable features.
- The ``/ws`` endpoint — ready advertises ``opus``, a declaration switches
  binary frames to one-opus-packet-per-message in both directions, and
  channel fan-out encodes per subscriber (mixed opus/PCM sessions).
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import opuslib
import pytest
from fastapi.testclient import TestClient
from tank_contracts import decode_audio_frame
from tank_contracts.tts import AudioChunk
from tank_protocol import OPUS_PROFILE, MessageType, WebsocketMessage, __version__

from tank_backend.api import deps
from tank_backend.api.manager import ConnectionManager
from tank_backend.api.server import app
from tank_backend.api.signal_handlers import handle_capabilities
from tank_backend.audio.opus_codec import (
    OpusDecodeError,
    OpusDownlinkEncoder,
    OpusUplinkDecoder,
    create_session_codecs,
    supported_protocol_features,
)
from tank_backend.channels.subscription import ChannelSubscriptionManager
from tank_backend.config import AppConfig
from tank_backend.config.context import AppContext

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


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


def _eventually(cond: Any, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return False


# ---------------------------------------------------------------------------
# audio/opus_codec.py — codec units
# ---------------------------------------------------------------------------


def test_supported_features_advertise_opus():
    assert supported_protocol_features() == ["opus"]


def test_downlink_encoder_roundtrip_quality_and_rebuffering():
    rate = OPUS_PROFILE["downlink"]["sample_rate"]
    pcm = _speech_noise(rate * 3, rate)  # 3 s
    encoder = OpusDownlinkEncoder()
    packets: list[bytes] = []
    # Feed awkward, non-frame-aligned sizes — the encoder must re-buffer.
    pos = 0
    for size in (777, 3, 9600, 1, 4444, 19200, 5):
        while pos < len(pcm):
            packets.extend(encoder.feed(pcm[pos : pos + size].tobytes()))
            pos += size
            if size == 1 and pos > 2000:  # keep the byte-at-a-time leg short
                break
    packets.extend(encoder.feed(pcm[pos:].tobytes()))
    assert packets, "rebuffering produced no packets"

    decoder = opuslib.Decoder(rate, 1)
    decoded = b"".join(decoder.decode(p, rate * 20 // 1000) for p in packets)
    assert _aligned_snr(pcm, np.frombuffer(decoded, np.int16)) >= 10.0


def test_downlink_encoder_drops_stale_residue_after_gap():
    clock = {"t": 100.0}
    encoder = OpusDownlinkEncoder(clock=lambda: clock["t"])
    encoder.feed(b"\x00\x70" * 10)  # loud 10-sample residue, buffered
    clock["t"] += 5.0  # interrupt-scale gap
    packets = encoder.feed(b"\x00\x00" * 480)  # exactly one silent frame

    decoder = opuslib.Decoder(24000, 1)
    out = np.frombuffer(decoder.decode(packets[0], 480), np.int16)
    assert len(out) == 480
    # Residue was dropped: the decoded frame is silence, not stale audio.
    assert int(np.max(np.abs(out.astype(np.int32)))) < 1000


def test_downlink_encoder_keeps_fresh_residue():
    clock = {"t": 100.0}
    encoder = OpusDownlinkEncoder(clock=lambda: clock["t"])
    encoder.feed(b"\x00\x70" * 10)  # loud residue — must survive into next frame
    packets = encoder.feed(b"\x00\x00" * 470)  # 10 + 470 = one 20 ms frame

    decoder = opuslib.Decoder(24000, 1)
    out = np.frombuffer(decoder.decode(packets[0], 480), np.int16)
    assert int(np.max(np.abs(out.astype(np.int32)))) > 5000


def test_uplink_decoder_roundtrip():
    rate = OPUS_PROFILE["uplink"]["sample_rate"]
    pcm = _speech_noise(rate, rate, seed=3)  # 1 s
    encoder = opuslib.Encoder(rate, 1, opuslib.APPLICATION_AUDIO)
    encoder.bitrate = OPUS_PROFILE["uplink"]["bitrate"]
    frame_samples = rate * OPUS_PROFILE["uplink"]["frame_ms"] // 1000

    decoder = OpusUplinkDecoder()
    out = b"".join(
        decoder.decode_packet(encoder.encode(pcm[i : i + frame_samples].tobytes(), frame_samples))
        for i in range(0, len(pcm) - frame_samples + 1, frame_samples)
    )
    assert _aligned_snr(pcm, np.frombuffer(out, np.int16)) >= 10.0


def test_uplink_decoder_tolerates_garbage_without_crashing():
    decoder = OpusUplinkDecoder()
    for blob in (b"", b"\xff" * 40, b"\x00", bytes(range(256)) * 4):
        try:
            out = decoder.decode_packet(blob)
        except OpusDecodeError:
            continue
        # Bounded output: well-formed packets decode to one 20 ms frame;
        # garbage may trigger PLC up to the 120 ms capacity domain.
        assert len(out) <= 5760


def test_create_session_codecs_pairs_both_directions():
    codecs = create_session_codecs()
    assert isinstance(codecs.uplink, OpusUplinkDecoder)
    assert isinstance(codecs.downlink, OpusDownlinkEncoder)


# ---------------------------------------------------------------------------
# handle_capabilities — the negotiation
# ---------------------------------------------------------------------------


@pytest.fixture()
def conn_mgr():
    ctx = AppContext(app_config=AppConfig())
    mgr = ConnectionManager(app_context=ctx)
    prior = (deps._deps["ctx"], deps._mgr["v"])
    deps._deps["ctx"], deps._mgr["v"] = ctx, mgr
    yield mgr
    deps._deps["ctx"], deps._mgr["v"] = prior


def _declaration(enable: Any) -> WebsocketMessage:
    return WebsocketMessage(
        type=MessageType.SIGNAL, content="capabilities", metadata={"enable": enable}
    )


async def test_declaration_enables_opus_registers_codecs_and_acks(conn_mgr):
    send_fn = AsyncMock()
    await handle_capabilities(MagicMock(), _declaration(["opus"]), "s1", send_fn)

    ack = send_fn.call_args[0][0]
    assert ack.content == "capabilities"
    assert ack.metadata["enabled"] == ["opus"]
    assert ack.metadata["opus"] == OPUS_PROFILE
    assert conn_mgr.get_codec("s1") is not None


async def test_unknown_feature_is_ignored_but_known_ones_enable(conn_mgr, caplog):
    send_fn = AsyncMock()
    await handle_capabilities(
        MagicMock(), _declaration(["opus", "warp-drive"]), "s1", send_fn
    )
    ack = send_fn.call_args[0][0]
    assert ack.metadata["enabled"] == ["opus"]
    assert any("warp-drive" in r.message for r in caplog.records)


async def test_unavailable_feature_is_not_enabled(conn_mgr):
    send_fn = AsyncMock()
    await handle_capabilities(MagicMock(), _declaration(["resume"]), "s1", send_fn)
    ack = send_fn.call_args[0][0]
    assert ack.metadata["enabled"] == []
    assert "opus" not in ack.metadata
    assert conn_mgr.get_codec("s1") is None


async def test_non_list_enable_is_rejected_without_crash(conn_mgr):
    send_fn = AsyncMock()
    await handle_capabilities(MagicMock(), _declaration("opus"), "s1", send_fn)
    assert send_fn.call_args[0][0].metadata["enabled"] == []


async def test_non_string_entries_are_dropped(conn_mgr):
    send_fn = AsyncMock()
    await handle_capabilities(MagicMock(), _declaration(["opus", 42]), "s1", send_fn)
    assert send_fn.call_args[0][0].metadata["enabled"] == ["opus"]


# ---------------------------------------------------------------------------
# /ws endpoint — full negotiation + both binary directions + fan-out
# ---------------------------------------------------------------------------


@pytest.fixture()
def harness(monkeypatch):
    """Real ConnectionManager (registries) + MagicMock assistant behind the
    real websocket_endpoint."""
    ctx = AppContext(app_config=AppConfig())
    mgr = ConnectionManager(app_context=ctx)
    assistant = MagicMock()
    assistant.capabilities = {"asr": True, "tts": True}
    assistant.pipeline_sample_rate = 16000
    assistant.capture_sample_rate = 16000
    assistant.capture_channels = 1
    assistant.brain.conversation_id = None
    callbacks: dict[str, Any] = {}
    assistant.set_playback_callback = lambda cb: callbacks.__setitem__("playback", cb)

    async def fake_get_or_create(session_id: str, **kwargs: Any):
        return assistant, True

    monkeypatch.setattr(mgr, "get_or_create_assistant", fake_get_or_create)
    sub_mgr = ChannelSubscriptionManager()
    prior = (
        deps._deps["ctx"],
        deps._mgr["v"],
        deps._sub_mgr["v"],
        deps._channel_audio["v"],
    )
    deps.init(ctx, mgr, sub_mgr, None)
    yield SimpleNamespace(
        mgr=mgr, assistant=assistant, sub_mgr=sub_mgr, callbacks=callbacks
    )
    deps._deps["ctx"], deps._mgr["v"], deps._sub_mgr["v"], deps._channel_audio["v"] = prior


def _declare_opus(ws: Any) -> dict[str, Any]:
    ws.send_text(
        json.dumps({"type": "signal", "content": "capabilities",
                    "metadata": {"enable": ["opus"]}})
    )
    return json.loads(ws.receive_text())


def test_ready_advertises_opus(harness):
    with TestClient(app).websocket_connect("/ws/s1") as ws:
        ready = json.loads(ws.receive_text())
    assert "opus" in ready["metadata"]["protocol_features"]
    assert ready["metadata"]["protocol_version"] == __version__


def test_negotiation_switches_uplink_to_opus(harness):
    with TestClient(app).websocket_connect("/ws/s1") as ws:
        ws.receive_text()  # ready
        ack = _declare_opus(ws)
        assert ack["metadata"]["enabled"] == ["opus"]

        rate = OPUS_PROFILE["uplink"]["sample_rate"]
        frame_samples = rate * OPUS_PROFILE["uplink"]["frame_ms"] // 1000
        pcm = _speech_noise(frame_samples, rate, seed=11)
        enc = opuslib.Encoder(rate, 1, opuslib.APPLICATION_AUDIO)
        enc.bitrate = OPUS_PROFILE["uplink"]["bitrate"]
        ws.send_bytes(enc.encode(pcm.tobytes(), frame_samples))

        assert _eventually(lambda: harness.assistant.push_audio.call_count == 1)
        frame = harness.assistant.push_audio.call_args[0][0]
        assert frame.sample_rate == 16000
        assert _aligned_snr(pcm, (frame.pcm * 32768).astype(np.int16)) >= 10.0


def test_negotiation_switches_downlink_to_opus(harness):
    with TestClient(app).websocket_connect("/ws/s1") as ws:
        ws.receive_text()  # ready
        _declare_opus(ws)

        rate = OPUS_PROFILE["downlink"]["sample_rate"]
        pcm = _speech_noise(rate, rate, seed=5)  # 1 s = 50 frames
        # Feed the whole second via the captured playback callback.
        step = rate * 20 // 1000 * 2  # one 20 ms frame per chunk
        for i in range(0, len(pcm) - step + 1, step):
            harness.callbacks["playback"](
                AudioChunk(data=pcm[i : i + step].tobytes(),
                           sample_rate=rate, channels=1)
            )
        packets = [ws.receive_bytes() for _ in range(len(pcm) // step)]

    decoder = opuslib.Decoder(rate, 1)
    decoded = b"".join(decoder.decode(p, rate * 20 // 1000) for p in packets)
    assert _aligned_snr(pcm, np.frombuffer(decoded, np.int16)) >= 10.0


def test_fanout_self_opus_serves_pcm_subscriber_native_rate(harness):
    with TestClient(app).websocket_connect("/ws/s1") as ws:
        ws.receive_text()  # ready
        _declare_opus(ws)
        harness.mgr.set_session_channel("s1", "ch")
        harness.sub_mgr.subscribe("s2", ["ch"])
        binary_fn = AsyncMock()
        harness.mgr.register_binary_sender("s2", binary_fn)

        rate = OPUS_PROFILE["downlink"]["sample_rate"]
        step = rate * 20 // 1000 * 2
        pcm = _speech_noise(step, rate, seed=9)
        harness.callbacks["playback"](
            AudioChunk(data=pcm.tobytes(), sample_rate=rate, channels=1)
        )

        ws.receive_bytes()  # self gets opus packets (may buffer this chunk)
        assert _eventually(lambda: binary_fn.call_count >= 1)
        pcm_out, sr, ch = decode_audio_frame(binary_fn.call_args_list[0][0][0])
        assert (sr, ch) == (24000, 1)
        assert np.frombuffer(pcm_out, np.int16).tobytes() == pcm.tobytes()


def test_fanout_opus_subscriber_of_pcm_session(harness):
    with TestClient(app).websocket_connect("/ws/s1") as ws:
        ws.receive_text()  # ready — no declaration: self stays raw PCM
        harness.mgr.set_session_channel("s1", "ch")
        harness.sub_mgr.subscribe("s2", ["ch"])
        harness.mgr.register_codec("s2", create_session_codecs())
        binary_fn = AsyncMock()
        harness.mgr.register_binary_sender("s2", binary_fn)

        rate = OPUS_PROFILE["downlink"]["sample_rate"]
        step = rate * 20 // 1000 * 2
        pcm = _speech_noise(step * 3, rate, seed=13)
        for i in range(0, len(pcm), step):
            harness.callbacks["playback"](
                AudioChunk(data=pcm[i : i + step].tobytes(),
                           sample_rate=rate, channels=1)
            )

        # Self (PCM) still receives a header-framed chunk.
        frame = ws.receive_bytes()
        pcm_self, sr_self, _ = decode_audio_frame(frame)
        assert sr_self == 24000
        # Opus subscriber gets packets via the shared channel encoder.
        assert _eventually(lambda: binary_fn.call_count >= 1)

    packets = [c[0][0] for c in binary_fn.call_args_list]
    decoder = opuslib.Decoder(rate, 1)
    decoded = b"".join(decoder.decode(p, rate * 20 // 1000) for p in packets)
    assert _aligned_snr(pcm, np.frombuffer(decoded, np.int16)) >= 10.0
