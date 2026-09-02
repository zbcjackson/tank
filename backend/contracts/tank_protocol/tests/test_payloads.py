"""Per-type payload field-set validation."""

from __future__ import annotations

from tank_protocol import (
    MessageType,
    WebsocketMessage,
    validate_envelope,
)


def test_clean_frames_produce_no_violations():
    frames = [
        WebsocketMessage(type=MessageType.SIGNAL, content="ready", session_id="s1"),
        WebsocketMessage(
            type=MessageType.TRANSCRIPT,
            content="hi",
            speaker="User",
            is_user=True,
            is_final=True,
            msg_id="u1",
        ),
        WebsocketMessage(type=MessageType.TEXT, content="hello", msg_id="m1"),
        WebsocketMessage(
            type=MessageType.UPDATE,
            metadata={"update_type": "UpdateType.THINKING", "step_id": "s"},
            msg_id="m1",
        ),
        WebsocketMessage(type=MessageType.INPUT, content="typed"),
        WebsocketMessage(
            type=MessageType.CHANNEL_NOTIFICATION,
            metadata={"channel_slug": "jobs"},
        ),
        WebsocketMessage(
            type=MessageType.CONVERSATION_METADATA_UPDATED,
            session_id="s1",
            metadata={"conversation_id": "c1", "title": "T"},
        ),
    ]
    for frame in frames:
        assert validate_envelope(frame) == [], (frame.type, validate_envelope(frame))


def test_wrong_envelope_field_is_reported():
    violating = WebsocketMessage(type=MessageType.CHANNEL_NOTIFICATION)
    violating.content = "oops"
    violations = validate_envelope(violating)
    assert any(v.startswith("field: content") for v in violations)


def test_default_valued_fields_are_not_violations():
    clean = WebsocketMessage(type=MessageType.CHANNEL_NOTIFICATION)
    assert validate_envelope(clean) == []


def test_unknown_metadata_key_is_reported():
    msg = WebsocketMessage(type=MessageType.TEXT, content="hi")
    msg.metadata["secret_key"] = 1
    violations = validate_envelope(msg)
    assert violations == ["metadata: key 'secret_key' is not documented for text"]


def test_validation_never_raises_on_any_type():
    for msg_type in MessageType:
        msg = WebsocketMessage(type=msg_type)
        assert isinstance(validate_envelope(msg), list)
