"""Schema export + golden-frame header generation stability."""

from __future__ import annotations

import json

from tank_protocol import __version__
from tank_protocol.schema import (
    build_schema_document,
    generate_golden_frames_header,
)


def test_schema_document_contains_envelope_and_version():
    doc = build_schema_document()
    assert doc["title"] == "WebsocketMessage"
    assert doc["x-tank-version"] == __version__
    assert doc["properties"]["type"]["$ref"] == "#/$defs/MessageType"
    assert set(doc["$defs"]) == {"MessageType", "WebsocketAttachment"}
    assert doc["$defs"]["MessageType"]["enum"] == [
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
    ]


def test_schema_document_publishes_payload_field_sets():
    doc = build_schema_document()
    fields = doc["x-tank-payload-fields"]
    assert fields["attachment"]["envelope"] == [
        "attachments",
        "content",
        "is_final",
        "metadata",
        "msg_id",
        "session_id",
        "speaker",
    ]
    assert "update_type" in fields["update"]["metadata"]
    assert "user_id" in fields["input"]["metadata"]


def test_golden_header_covers_every_outbound_type_and_is_stable():
    header = generate_golden_frames_header()
    for constant in (
        "TANK_GOLDEN_SIGNAL",
        "TANK_GOLDEN_SIGNAL_CAPABILITIES_ACK",
        "TANK_GOLDEN_TRANSCRIPT",
        "TANK_GOLDEN_TEXT",
        "TANK_GOLDEN_UPDATE",
        "TANK_GOLDEN_ATTACHMENT",
        "TANK_GOLDEN_CHANNEL_NOTIFICATION",
        "TANK_GOLDEN_CONVERSATION_METADATA",
        "TANK_GOLDEN_CONFIG",
        "TANK_GOLDEN_CONTEXT_INJECT",
        "TANK_GOLDEN_UNKNOWN_FIELD",
    ):
        assert constant in header
    assert header.startswith("// Auto-generated")
    assert "#pragma once" in header
    # Generation is deterministic (committed artifacts diff-checked).
    assert header == generate_golden_frames_header()


def test_golden_frames_are_valid_wire_json():
    header = generate_golden_frames_header()
    frames = [
        line.split('R"JSON(', 1)[1].rsplit(")JSON", 1)[0]
        for line in header.splitlines()
        if "R\"JSON(" in line
    ]
    assert len(frames) == 11
    for raw in frames:
        parsed = json.loads(raw)
        assert "type" in parsed
