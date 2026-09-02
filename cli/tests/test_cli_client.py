"""Tests for TankClient WebSocket client."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from tank_protocol import MessageType, WebsocketMessage

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
