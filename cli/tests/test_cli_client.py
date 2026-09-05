"""Tests for TankClient WebSocket client."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import numpy as np
import opuslib
import pytest
from tank_protocol import MessageType, WebsocketMessage

from tank_cli.audio.frame import decode_audio_frame
from tank_cli.cli.client import TankClient

MODULE = "tank_cli.cli.client"


def _mock_ws_connect(mock_ws):
    """Create a patch for websockets.connect that returns mock_ws as an awaitable."""
    return patch(f"{MODULE}.websockets.connect", AsyncMock(return_value=mock_ws))


def _make_async_iter_ws(items):
    """Create a mock WebSocket that yields items via async for."""
    mock_ws = AsyncMock()

    async def async_iter():
        for item in items:
            yield item

    mock_ws.__aiter__ = lambda self: async_iter()
    return mock_ws


def _make_gated_ws(items):
    """Mock WebSocket yielding ``items`` then blocking until ``gate`` is set —
    keeps the receive loop (and negotiated state) alive for post-loop asserts."""
    mock_ws = AsyncMock()
    drained = asyncio.Event()
    gate = asyncio.Event()

    async def async_iter():
        for item in items:
            yield item
        drained.set()
        await gate.wait()

    mock_ws.__aiter__ = lambda self: async_iter()
    return mock_ws, drained, gate


def _signal(content, metadata=None):
    return WebsocketMessage(
        type=MessageType.SIGNAL, content=content, metadata=metadata or {}
    ).model_dump_json()


def _sent_frames(mock_ws):
    return [c.args[0] for c in mock_ws.send.call_args_list]


DOWNLINK_RATE = 24000
DOWNLINK_FRAME_SAMPLES = DOWNLINK_RATE * 20 // 1000


def _downlink_packet(pcm: np.ndarray) -> bytes:
    enc = opuslib.Encoder(DOWNLINK_RATE, 1, opuslib.APPLICATION_AUDIO)
    enc.bitrate = 32000
    return enc.encode(pcm.tobytes(), DOWNLINK_FRAME_SAMPLES)



@pytest.fixture
def client():
    return TankClient(base_url="localhost:9999", session_id="test123")


def test_init_defaults():
    c = TankClient()
    assert c.session_id
    assert not c.is_connected


def test_contract_parses_speaker_and_attachments():
    """The shared tank_protocol envelope keeps fields the old hand-copied
    tank_cli.schemas dropped (speaker / attachments) — protocol plan W2."""
    raw = (
        '{"type":"attachment","content":"cap","speaker":"Brain","is_user":false,'
        '"is_final":true,"msg_id":"m1","session_id":"s1","metadata":{},'
        '"attachments":[{"kind":"image","url":"/api/media/s1/x.jpg",'
        '"mime_type":"image/jpeg","caption":"cap"}]}'
    )
    msg = WebsocketMessage.model_validate_json(raw)
    assert msg.type == MessageType.ATTACHMENT
    assert msg.speaker == "Brain"
    assert msg.attachments[0].url == "/api/media/s1/x.jpg"
    assert msg.attachments[0].caption == "cap"


def test_init_custom_session():
    c = TankClient(base_url="example.com:8000", session_id="abc")
    assert c.session_id == "abc"
    assert c._url == "ws://example.com:8000/ws/abc"


@pytest.mark.asyncio
async def test_connect_sets_state(client):
    mock_ws = AsyncMock()
    with _mock_ws_connect(mock_ws):
        await client.connect(on_text_message=lambda m: None, on_audio_chunk=lambda d: None)
        assert client.is_connected
        assert client._ws is mock_ws


@pytest.mark.asyncio
async def test_receive_loop_dispatches_text(client):
    received_messages = []

    text_payload = WebsocketMessage(
        type=MessageType.TEXT, content="hello", is_final=True
    ).model_dump_json()

    mock_ws = _make_async_iter_ws([text_payload])

    with _mock_ws_connect(mock_ws):
        await client.connect(
            on_text_message=received_messages.append,
            on_audio_chunk=lambda d: None,
        )
        await client.receive_loop()

    assert len(received_messages) == 1
    assert received_messages[0].content == "hello"
    assert received_messages[0].type == MessageType.TEXT


@pytest.mark.asyncio
async def test_receive_loop_dispatches_binary(client):
    received_chunks = []
    audio_data = b"\x00\x01\x02\x03"

    mock_ws = _make_async_iter_ws([audio_data])

    with _mock_ws_connect(mock_ws):
        await client.connect(
            on_text_message=lambda m: None,
            on_audio_chunk=received_chunks.append,
        )
        await client.receive_loop()

    assert len(received_chunks) == 1
    assert received_chunks[0] == audio_data


@pytest.mark.asyncio
async def test_send_audio(client):
    mock_ws = AsyncMock()
    with _mock_ws_connect(mock_ws):
        await client.connect(on_text_message=lambda m: None, on_audio_chunk=lambda d: None)
        await client.send_audio(b"\x00\x01")
        mock_ws.send.assert_called_once_with(b"\x00\x01")


@pytest.mark.asyncio
async def test_send_text_input(client):
    mock_ws = AsyncMock()
    with _mock_ws_connect(mock_ws):
        await client.connect(on_text_message=lambda m: None, on_audio_chunk=lambda d: None)
        await client.send_text_input("hi there")

        sent = mock_ws.send.call_args[0][0]
        parsed = json.loads(sent)
        assert parsed["type"] == "input"
        assert parsed["content"] == "hi there"


@pytest.mark.asyncio
async def test_send_interrupt(client):
    mock_ws = AsyncMock()
    with _mock_ws_connect(mock_ws):
        await client.connect(on_text_message=lambda m: None, on_audio_chunk=lambda d: None)
        await client.send_interrupt()

        sent = mock_ws.send.call_args[0][0]
        parsed = json.loads(sent)
        assert parsed["type"] == "signal"
        assert parsed["content"] == "interrupt"


@pytest.mark.asyncio
async def test_disconnect(client):
    mock_ws = AsyncMock()
    with _mock_ws_connect(mock_ws):
        await client.connect(on_text_message=lambda m: None, on_audio_chunk=lambda d: None)
        assert client.is_connected

        await client.disconnect()
        assert not client.is_connected
        mock_ws.close.assert_called_once()


@pytest.mark.asyncio
async def test_send_audio_when_not_connected(client):
    """send_audio should be a no-op when not connected."""
    await client.send_audio(b"\x00")
    # No exception raised


@pytest.mark.asyncio
async def test_send_text_input_when_not_connected(client):
    """send_text_input should be a no-op when not connected."""
    await client.send_text_input("hello")
    # No exception raised


# ---------------------------------------------------------------------------
# Opus negotiation (protocol plan P1-2 Step 4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ready_with_opus_sends_declaration(client):
    """ready advertising opus → one capabilities declaration, no codec yet."""
    mock_ws, drained, gate = _make_gated_ws(
        [_signal("ready", {"protocol_features": ["opus"], "protocol_version": "0.2.0"})]
    )
    with _mock_ws_connect(mock_ws):
        await client.connect(on_text_message=lambda m: None, on_audio_chunk=lambda d: None)
        task = asyncio.create_task(client.receive_loop())
        await asyncio.wait_for(drained.wait(), 2)

        assert client._codecs is None  # switch happens on ack, not on ready
        (decl,) = _sent_frames(mock_ws)
        parsed = json.loads(decl)
        assert parsed["type"] == "signal"
        assert parsed["content"] == "capabilities"
        assert parsed["metadata"]["enable"] == ["opus"]

        gate.set()
        await task


@pytest.mark.asyncio
async def test_ready_without_opus_stays_pcm(client):
    mock_ws, drained, gate = _make_gated_ws(
        [_signal("ready", {"protocol_features": [], "protocol_version": "0.2.0"})]
    )
    with _mock_ws_connect(mock_ws):
        await client.connect(on_text_message=lambda m: None, on_audio_chunk=lambda d: None)
        task = asyncio.create_task(client.receive_loop())
        await asyncio.wait_for(drained.wait(), 2)

        assert _sent_frames(mock_ws) == []
        assert client._codecs is None

        gate.set()
        await task


@pytest.mark.asyncio
async def test_duplicate_ready_sends_declaration_once(client):
    mock_ws, drained, gate = _make_gated_ws(
        [_signal("ready", {"protocol_features": ["opus"]})] * 2
    )
    with _mock_ws_connect(mock_ws):
        await client.connect(on_text_message=lambda m: None, on_audio_chunk=lambda d: None)
        task = asyncio.create_task(client.receive_loop())
        await asyncio.wait_for(drained.wait(), 2)

        assert len(_sent_frames(mock_ws)) == 1

        gate.set()
        await task


@pytest.mark.asyncio
async def test_ack_switches_uplink_to_opus(client):
    mock_ws, drained, gate = _make_gated_ws(
        [
            _signal("ready", {"protocol_features": ["opus"]}),
            _signal("capabilities", {"enabled": ["opus"]}),
        ]
    )
    with _mock_ws_connect(mock_ws):
        await client.connect(on_text_message=lambda m: None, on_audio_chunk=lambda d: None)
        task = asyncio.create_task(client.receive_loop())
        await asyncio.wait_for(drained.wait(), 2)

        await client.send_audio(np.zeros(320, dtype=np.int16).tobytes())
        sends = _sent_frames(mock_ws)
        assert len(sends) == 2  # declaration + one opus packet
        packet = sends[1]
        assert packet != sends[0]
        assert 0 < len(packet) < 200  # opus packet, not 640 B of raw PCM

        dec = opuslib.Decoder(16000, 1)
        assert len(dec.decode(packet, 320 * 6)) == 320 * 2  # bytes = 320 samples

        gate.set()
        await task


@pytest.mark.asyncio
async def test_ack_without_opus_keeps_raw_pcm(client):
    mock_ws, drained, gate = _make_gated_ws(
        [
            _signal("ready", {"protocol_features": ["opus"]}),
            _signal("capabilities", {"enabled": []}),
        ]
    )
    with _mock_ws_connect(mock_ws):
        await client.connect(on_text_message=lambda m: None, on_audio_chunk=lambda d: None)
        task = asyncio.create_task(client.receive_loop())
        await asyncio.wait_for(drained.wait(), 2)

        raw = np.zeros(320, dtype=np.int16).tobytes()
        await client.send_audio(raw)
        assert _sent_frames(mock_ws)[-1] == raw
        assert client._codecs is None

        gate.set()
        await task


@pytest.mark.asyncio
async def test_ack_switches_downlink_to_opus(client):
    pcm = (np.sin(np.linspace(0, 100, DOWNLINK_FRAME_SAMPLES)) * 8000).astype(np.int16)
    mock_ws = _make_async_iter_ws(
        [
            _signal("ready", {"protocol_features": ["opus"]}),
            _signal("capabilities", {"enabled": ["opus"]}),
            _downlink_packet(pcm),
        ]
    )
    chunks = []
    with _mock_ws_connect(mock_ws):
        await client.connect(
            on_text_message=lambda m: None, on_audio_chunk=chunks.append
        )
        await client.receive_loop()

    assert len(chunks) == 1
    got_pcm, rate, channels = decode_audio_frame(chunks[0])
    assert (rate, channels) == (24000, 1)
    assert len(got_pcm) == DOWNLINK_FRAME_SAMPLES * 2


@pytest.mark.asyncio
async def test_opus_downlink_garbage_packet_dropped(client):
    """A bad packet is dropped with a warning; the connection continues."""
    pcm = (np.sin(np.linspace(0, 100, DOWNLINK_FRAME_SAMPLES)) * 8000).astype(np.int16)
    mock_ws = _make_async_iter_ws(
        [
            _signal("ready", {"protocol_features": ["opus"]}),
            _signal("capabilities", {"enabled": ["opus"]}),
            b"\xff" * 200,
            _downlink_packet(pcm),
        ]
    )
    chunks = []
    with _mock_ws_connect(mock_ws):
        await client.connect(
            on_text_message=lambda m: None, on_audio_chunk=chunks.append
        )
        await client.receive_loop()

    assert len(chunks) == 1


@pytest.mark.asyncio
async def test_disconnect_resets_codecs(client):
    mock_ws = _make_async_iter_ws(
        [
            _signal("ready", {"protocol_features": ["opus"]}),
            _signal("capabilities", {"enabled": ["opus"]}),
        ]
    )
    with _mock_ws_connect(mock_ws):
        await client.connect(on_text_message=lambda m: None, on_audio_chunk=lambda d: None)
        await client.receive_loop()
        assert client._codecs is not None

        await client.disconnect()
        assert client._codecs is None
