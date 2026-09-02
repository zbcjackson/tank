"""Wire-compatibility lock for the P0-1 protocol contract extraction.

Every expected value below is FROZEN from the pre-extraction handwritten
``WebsocketMessage(...)`` constructions (protocol plan §8 P0-1: factory
output must diff empty against them). If one of these tests fails, a frame
changed shape on the wire and a shipped client will notice.

The router mapping helpers are exercised directly (not the factories alone)
so the ``DisplayMessage`` → frame translation — including ``step_id``
injection — is covered end to end.
"""

from __future__ import annotations

import json

from tank_protocol import signal as signal_frame

from tank_backend.api.router import (
    _attachment_payload_to_ws_msg,
    _ui_msg_to_ws_msg,
    _worker_activity_to_ws_msg,
    _worker_event_to_ws_msg,
)
from tank_backend.core.content import ImageBlock
from tank_backend.core.events import (
    ConversationMetadataUpdate,
    DisplayMessage,
    SignalMessage,
    UpdateType,
)

SESSION = "s1"


def test_signal_message_frame():
    msg = SignalMessage(signal_type="processing_started", msg_id="m1")
    frame = _ui_msg_to_ws_msg(msg, SESSION)
    assert frame is not None
    assert frame.model_dump() == {
        "type": "signal",
        "content": "processing_started",
        "speaker": None,
        "is_user": False,
        "is_final": False,
        "msg_id": "m1",
        "session_id": SESSION,
        "metadata": {},
        "attachments": [],
    }


def test_conversation_metadata_frame():
    msg = ConversationMetadataUpdate(conversation_id="c1", title="Hello")
    frame = _ui_msg_to_ws_msg(msg, SESSION, conversation_id="c1")
    assert frame is not None
    assert frame.model_dump() == {
        "type": "conversation_metadata_updated",
        "content": "",
        "speaker": None,
        "is_user": False,
        "is_final": True,
        "msg_id": None,
        "session_id": SESSION,
        "metadata": {"conversation_id": "c1", "title": "Hello"},
        "attachments": [],
    }


def test_transcript_frame_injects_step_id():
    # ASR result with a msg_id — the old code stamped
    # metadata["step_id"] = "<msg_id>_text_0" onto TRANSCRIPT frames too.
    msg = DisplayMessage(
        speaker="User", text="hi", is_user=True, is_final=True, msg_id="u1",
    )
    frame = _ui_msg_to_ws_msg(msg, SESSION)
    assert frame is not None
    assert frame.model_dump() == {
        "type": "transcript",
        "content": "hi",
        "speaker": "User",
        "is_user": True,
        "is_final": True,
        "msg_id": "u1",
        "session_id": SESSION,
        "metadata": {"step_id": "u1_text_0"},
        "attachments": [],
    }


def test_text_frame_keeps_turn_and_injects_step_id():
    msg = DisplayMessage(
        speaker="Brain", text="Hel", is_user=False, is_final=False,
        msg_id="m1", metadata={"turn": 2},
    )
    frame = _ui_msg_to_ws_msg(msg, SESSION)
    assert frame is not None
    assert frame.model_dump() == {
        "type": "text",
        "content": "Hel",
        "speaker": "Brain",
        "is_user": False,
        "is_final": False,
        "msg_id": "m1",
        "session_id": SESSION,
        "metadata": {"turn": 2, "step_id": "m1_text_2"},
        "attachments": [],
    }


def test_thought_frame_becomes_update():
    msg = DisplayMessage(
        speaker="Brain", text="thinking...", is_user=False, is_final=False,
        msg_id="m1", update_type=UpdateType.THOUGHT, metadata={"turn": 1},
    )
    frame = _ui_msg_to_ws_msg(msg, SESSION)
    assert frame is not None
    assert frame.model_dump() == {
        "type": "update",
        "content": "thinking...",
        "speaker": "Brain",
        "is_user": False,
        "is_final": False,
        "msg_id": "m1",
        "session_id": SESSION,
        "metadata": {
            "turn": 1,
            "step_id": "m1_thought_1",
            "update_type": "UpdateType.THOUGHT",
        },
        "attachments": [],
    }


def test_tool_frame_step_id_includes_index():
    msg = DisplayMessage(
        speaker="Brain", text="", is_user=False, is_final=False, msg_id="m1",
        update_type=UpdateType.TOOL,
        metadata={
            "turn": 0, "index": 2, "name": "calculate",
            "arguments": "{}", "status": "calling",
        },
    )
    frame = _ui_msg_to_ws_msg(msg, SESSION)
    assert frame is not None
    dumped = frame.model_dump()
    assert dumped["type"] == "update"
    assert dumped["metadata"]["update_type"] == "UpdateType.TOOL"
    assert dumped["metadata"]["step_id"] == "m1_tool_0_2"
    assert dumped["metadata"]["index"] == 2
    assert dumped["metadata"]["status"] == "calling"


def test_approval_frame_step_id_uses_approval_id():
    msg = DisplayMessage(
        speaker="Brain", text="Run command?", is_user=False, is_final=False,
        msg_id="m1", update_type=UpdateType.APPROVAL,
        metadata={"approval_id": "a1", "tool_name": "run_command", "tool_args": {}},
    )
    frame = _ui_msg_to_ws_msg(msg, SESSION)
    assert frame is not None
    dumped = frame.model_dump()
    assert dumped["metadata"]["step_id"] == "m1_approval_a1"
    assert dumped["metadata"]["update_type"] == "UpdateType.APPROVAL"


def test_worker_activity_frame():
    payload = {
        "task_id": "t1", "tool_name": "web_search",
        "tool_status": "executing", "tool_args": '{"query":"x"}',
    }
    frame = _worker_activity_to_ws_msg(payload, SESSION)
    assert frame is not None
    assert frame.model_dump() == {
        "type": "update",
        "content": "",
        "speaker": "Brain",
        "is_user": False,
        "is_final": False,
        "msg_id": "worker_t1",
        "session_id": SESSION,
        "metadata": {
            "update_type": "ACTIVITY.WORKER_ACTIVITY",
            "step_id": "worker_t1_tool_0_worker_t1",
            "task_id": "t1",
            "tool_name": "web_search",
            "tool_status": "executing",
            "tool_args": '{"query":"x"}',
        },
        "attachments": [],
    }


def test_worker_event_frame_completed():
    payload = {
        "event": "completed", "task_id": "t1", "output": "done",
        "parent_msg_id": "m9", "description": "searching",
    }
    frame = _worker_event_to_ws_msg(payload, SESSION)
    assert frame is not None
    assert frame.model_dump() == {
        "type": "update",
        "content": "done",
        "speaker": "Brain",
        "is_user": False,
        "is_final": True,
        "msg_id": "m9",
        "session_id": SESSION,
        "metadata": {
            "update_type": "ACTIVITY.TOOL",
            "step_id": "m9_tool_0_worker_t1",
            "name": "agent",
            "arguments": json.dumps(
                {"description": "searching", "background": True},
                ensure_ascii=False,
            ),
            "status": "success",
            "turn": 0,
            "index": 0,
        },
        "attachments": [],
    }


def test_attachment_frame():
    payload = {
        "msg_id": "m1",
        "caption": "a photo",
        "blocks": [ImageBlock(source="media://s1/x.jpg", mime_type="image/jpeg")],
    }
    frame = _attachment_payload_to_ws_msg(payload, SESSION)
    assert frame is not None
    assert frame.model_dump() == {
        "type": "attachment",
        "content": "a photo",
        "speaker": "Brain",
        "is_user": False,
        "is_final": True,
        "msg_id": "m1",
        "session_id": SESSION,
        "metadata": {},
        "attachments": [
            {
                "kind": "image",
                "url": "/api/media/s1/x.jpg",
                "mime_type": "image/jpeg",
                "caption": "a photo",
            }
        ],
    }


def test_ready_signal_frame_shape():
    # The ready frame is built inside websocket_endpoint; its exact shape
    # was WebsocketMessage(type=SIGNAL, content="ready", session_id=...,
    # metadata={capabilities, pipeline_sample_rate, conversation_id?}).
    frame = signal_frame(
        "ready",
        session_id=SESSION,
        metadata={"capabilities": ["asr"], "pipeline_sample_rate": 24000},
    )
    assert frame.model_dump() == {
        "type": "signal",
        "content": "ready",
        "speaker": None,
        "is_user": False,
        "is_final": False,
        "msg_id": None,
        "session_id": SESSION,
        "metadata": {"capabilities": ["asr"], "pipeline_sample_rate": 24000},
        "attachments": [],
    }
