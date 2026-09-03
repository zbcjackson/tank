"""P1-1 handshake: the ready frame advertises the protocol block, and the
client's ``signal: capabilities`` declaration is a recognized signal.

Old-client compatibility is the point of the additive design: clients that
never send the declaration behave exactly as before (their ready handling
ignores the two new metadata keys), covered here by the dispatch tests.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from tank_protocol import KNOWN_SIGNALS, __version__
from tank_protocol import signal as signal_frame
from tank_protocol.payloads import validate_envelope

from tank_backend.api.router import _ready_metadata
from tank_backend.api.signal_handlers import dispatch


def _mock_assistant(conversation_id: str | None = None) -> MagicMock:
    assistant = MagicMock()
    assistant.capabilities = {"asr": True, "tts": True, "speaker_id": False}
    assistant.pipeline_sample_rate = 24000
    assistant.brain.conversation_id = conversation_id
    return assistant


def test_ready_metadata_carries_protocol_handshake():
    metadata = _ready_metadata(_mock_assistant())
    assert metadata["protocol_version"] == __version__
    # No protocol feature is implemented yet (opus → P1-2, config → P1-3).
    assert metadata["protocol_features"] == []
    assert metadata["pipeline_sample_rate"] == 24000
    assert "conversation_id" not in metadata


def test_ready_metadata_includes_active_conversation():
    metadata = _ready_metadata(_mock_assistant(conversation_id="c1"))
    assert metadata["conversation_id"] == "c1"


def test_ready_frame_validates_clean():
    frame = signal_frame(
        "ready", session_id="s1", metadata=_ready_metadata(_mock_assistant())
    )
    assert validate_envelope(frame) == []


async def test_capabilities_declaration_is_dispatched():
    msg = MagicMock()
    msg.metadata = {"enable": ["opus"]}
    handled = await dispatch("capabilities", MagicMock(), msg, "s1", AsyncMock())
    assert handled is True


async def test_unknown_signal_still_unhandled():
    handled = await dispatch("no_such_signal", MagicMock(), MagicMock(), "s1", AsyncMock())
    assert handled is False


def test_capabilities_signal_is_in_known_set():
    assert "capabilities" in KNOWN_SIGNALS
