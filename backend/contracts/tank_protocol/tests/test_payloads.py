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


def test_capabilities_ack_metadata_keys_are_documented():
    # P1-2 negotiation ack: server → client on signal:capabilities.
    msg = WebsocketMessage(
        type=MessageType.SIGNAL,
        content="capabilities",
        metadata={"enabled": ["opus"], "opus": {"uplink": {}, "downlink": {}}},
    )
    assert validate_envelope(msg) == []


def test_validation_never_raises_on_any_type():
    for msg_type in MessageType:
        msg = WebsocketMessage(type=msg_type)
        assert isinstance(validate_envelope(msg), list)


def test_config_frame_fields_are_documented():
    # P1-3: config rides metadata.config; content stays empty.
    msg = WebsocketMessage(
        type=MessageType.CONFIG,
        session_id="s1",
        metadata={"config": {"voice": None}},
    )
    assert validate_envelope(msg) == []

    bad = WebsocketMessage(type=MessageType.CONFIG, content="oops")
    assert any(v.startswith("field: content") for v in validate_envelope(bad))

    bad_meta = WebsocketMessage(type=MessageType.CONFIG)
    bad_meta.metadata["patch"] = {}
    assert validate_envelope(bad_meta) == [
        "metadata: key 'patch' is not documented for config"
    ]


def test_context_inject_frame_fields_are_documented():
    msg = WebsocketMessage(
        type=MessageType.CONTEXT_INJECT,
        content="note",
        session_id="s1",
        metadata={"role": "system"},
    )
    assert validate_envelope(msg) == []

    bare = WebsocketMessage(type=MessageType.CONTEXT_INJECT, content="note")
    assert validate_envelope(bare) == []  # role defaults server-side

    bad = WebsocketMessage(type=MessageType.CONTEXT_INJECT, content="note")
    bad.metadata["priority"] = 1
    assert validate_envelope(bad) == [
        "metadata: key 'priority' is not documented for context_inject"
    ]
