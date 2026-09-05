"""Envelope round-trip + wire-shape locks.

The exact-JSON assertions are the wire-compatibility contract: they must
match what ``tank_backend.api.schemas`` emitted before the extraction, byte
for byte (all nine fields present, explicit ``null``).
"""

from __future__ import annotations

import json

from tank_protocol import MessageType, WebsocketAttachment, WebsocketMessage


def test_minimal_frame_dump_json_exact_shape():
    msg = WebsocketMessage(type=MessageType.SIGNAL, content="ready", session_id="s1")
    assert msg.model_dump_json() == (
        '{"type":"signal","content":"ready","speaker":null,"is_user":false,'
        '"is_final":false,"msg_id":null,"session_id":"s1","metadata":{},'
        '"attachments":[]}'
    )


def test_attachment_frame_dump_json_exact_shape():
    msg = WebsocketMessage(
        type=MessageType.ATTACHMENT,
        content="cap",
        speaker="Brain",
        is_final=True,
        msg_id="m1",
        session_id="s1",
        attachments=[WebsocketAttachment(url="/api/media/s1/x.jpg")],
    )
    assert msg.model_dump_json() == (
        '{"type":"attachment","content":"cap","speaker":"Brain","is_user":false,'
        '"is_final":true,"msg_id":"m1","session_id":"s1","metadata":{},'
        '"attachments":[{"kind":"image","url":"/api/media/s1/x.jpg",'
        '"mime_type":"image/jpeg","caption":null}]}'
    )


def test_roundtrip_dict_model_dict_identity():
    wire = {
        "type": "text",
        "content": "hi",
        "speaker": "Brain",
        "is_user": False,
        "is_final": True,
        "msg_id": "m1",
        "session_id": "s1",
        "metadata": {"turn": 0},
        "attachments": [],
    }
    assert WebsocketMessage(**wire).model_dump() == wire


def test_parse_ignores_unknown_fields():
    msg = WebsocketMessage.model_validate(
        {"type": "text", "content": "x", "a_future_field": 123}
    )
    assert msg.content == "x"


def test_message_type_values():
    assert {m.value for m in MessageType} == {
        "signal",
        "transcript",
        "text",
        "update",
        "input",
        "channel_notification",
        "attachment",
        "conversation_metadata_updated",
        "config",
        "context_inject",
    }


def test_metadata_defaults_to_fresh_dict():
    a = WebsocketMessage(type=MessageType.TEXT)
    b = WebsocketMessage(type=MessageType.TEXT)
    a.metadata["x"] = 1
    assert b.metadata == {}
    assert json.loads(a.model_dump_json())["metadata"] == {"x": 1}
