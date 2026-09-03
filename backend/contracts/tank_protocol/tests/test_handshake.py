"""Handshake model (protocol plan P1-1)."""

from __future__ import annotations

import json

from tank_protocol import (
    KNOWN_PROTOCOL_FEATURES,
    handshake_metadata,
    validate_envelope,
)


def test_handshake_metadata_carries_package_version():
    meta = handshake_metadata()
    assert meta["protocol_version"] == __import__("tank_protocol").__version__
    assert meta["protocol_features"] == []


def test_handshake_features_are_sorted_and_deduped():
    meta = handshake_metadata(["resume", "opus", "opus"])
    assert meta["protocol_features"] == ["opus", "resume"]


def test_known_features_cover_planned_phases():
    assert KNOWN_PROTOCOL_FEATURES == frozenset({"opus", "resume", "config"})


def test_ready_frame_with_handshake_metadata_is_clean():
    from tank_protocol import signal

    frame = signal(
        "ready",
        session_id="s1",
        metadata={"capabilities": {"asr": True}, **handshake_metadata(["opus"])},
    )
    assert validate_envelope(frame) == []
    wire = json.loads(frame.model_dump_json())
    assert wire["metadata"]["protocol_version"]
    assert wire["metadata"]["protocol_features"] == ["opus"]


def test_client_declaration_frame_is_clean():
    from tank_protocol import MessageType, signal

    frame = signal(
        "capabilities", session_id="s1", metadata={"enable": ["opus"]}
    )
    assert frame.type == MessageType.SIGNAL
    assert frame.content == "capabilities"
    assert validate_envelope(frame) == []
