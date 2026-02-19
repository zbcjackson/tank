"""Integration tests for the API Server and WebSocket interaction."""

import pytest
import numpy as np
import json
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from tank_backend.api.server import app
from tank_backend.api.schemas import WebsocketMessage, MessageType


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_websocket_lifecycle(client):
    """Test full WebSocket lifecycle: connect, receive ready, send audio, receive response."""
    with patch("src.voice_assistant.api.router.session_manager.create_assistant") as mock_create:
        mock_assistant = MagicMock()
        mock_assistant.get_messages.return_value = []
        mock_create.return_value = mock_assistant
        
        # Bridge mock to allow us to push messages manually
        messages_to_yield = []
        mock_assistant.get_messages.side_effect = lambda: [messages_to_yield.pop(0)] if messages_to_yield else []

        with client.websocket_connect("/ws/test_session") as ws:
            # 1. Check ready signal
            data = ws.receive_text()
            msg = WebsocketMessage.model_validate_json(data)
            assert msg.type == MessageType.SIGNAL
            assert msg.content == "ready"
            
            # 2. Send dummy binary audio
            dummy_audio = np.zeros(1600, dtype=np.int16).tobytes()
            ws.send_bytes(dummy_audio)
            
            # 3. Send interrupt signal
            interrupt_msg = WebsocketMessage(type=MessageType.SIGNAL, content="interrupt")
            ws.send_text(interrupt_msg.model_dump_json())
            
            # 4. Trigger a message from assistant
            from tank_backend.core.events import DisplayMessage
            messages_to_yield.append(DisplayMessage(
                speaker="Brain", text="Hello from server", is_user=False, is_final=True, msg_id="123"
            ))
            
            # Wait for text message (TestClient is synchronous and should receive it)
            data = ws.receive_text()
            msg = WebsocketMessage.model_validate_json(data)
            # It might be TEXT or UPDATE depending on DisplayMessage attributes
            assert msg.content == "Hello from server"
