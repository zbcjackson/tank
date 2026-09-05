"""JSON Schema export + codegen entry point.

Committed artifacts derived from this package:

- ``schema/tank_protocol.schema.json`` → web generates ``protocol.ts`` from it
  (``cd web && pnpm generate:protocol``)
- ``device/test/test_native/test_ws_message/golden_frames.h`` → one real wire
  frame per outbound message type, asserted against the C++ parser

Regenerate both:

.. code-block:: bash

    cd backend && uv run python -m tank_protocol.schema \\
        --schema-out contracts/tank_protocol/schema/tank_protocol.schema.json \\
        --golden-out ../device/test/test_native/test_ws_message/golden_frames.h

``scripts/check_protocol_sync.py`` regenerates into a temp dir and fails on
any diff against the committed files.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .envelope import WebsocketAttachment, WebsocketMessage
from .factories import (
    attachment,
    capabilities_ack,
    channel_notification,
    context_inject,
    conversation_metadata_updated,
    session_config,
    signal,
    text,
    transcript,
    update,
)
from .handshake import handshake_metadata
from .payloads import ENVELOPE_FIELDS, METADATA_KEYS

__all__ = [
    "build_schema_document",
    "generate_golden_frames_header",
    "main",
]


def _strip_field_titles(node: Any) -> None:
    """Drop per-field ``title`` keys so downstream code generators inline
    primitives instead of emitting one named alias per envelope field."""
    if isinstance(node, dict):
        node.pop("title", None)
        for value in node.values():
            _strip_field_titles(value)
    elif isinstance(node, list):
        for item in node:
            _strip_field_titles(item)


# Wire truth the raw pydantic schema cannot express: the server serializes
# every defaulted field on every frame (explicit ``null`` for unset
# optionals), and clients rely on these five always being present. The
# remaining fields stay optional/nullable — clients tolerate their absence.
_WIRE_REQUIRED = ["type", "content", "is_user", "is_final", "metadata"]


def build_schema_document() -> dict[str, Any]:
    """The committed JSON Schema document.

    Root is the envelope schema (what ``json-schema-to-typescript`` consumes);
    ``x-tank-*`` keys carry the payload field sets for human/CI reference.
    """
    doc = WebsocketMessage.model_json_schema()
    for props in (
        doc.get("properties", {}),
        *(d.get("properties", {}) for d in doc.get("$defs", {}).values()),
    ):
        _strip_field_titles(props)
    doc["required"] = list(_WIRE_REQUIRED)
    # Same wire truth for the nested attachment object: every field is
    # serialized, so clients see kind/mime_type/caption on each item.
    attachment_def = doc.get("$defs", {}).get("WebsocketAttachment")
    if attachment_def is not None:
        attachment_def["required"] = ["kind", "url", "mime_type", "caption"]
    doc["x-tank-version"] = __version__
    doc["x-tank-payload-fields"] = {
        msg_type.value: {
            "envelope": sorted(fields),
            "metadata": sorted(METADATA_KEYS[msg_type]),
        }
        for msg_type, fields in ENVELOPE_FIELDS.items()
    }
    return doc


def _golden_frames() -> list[tuple[str, str]]:
    """(constant name, wire JSON) for one frame of each outbound type."""
    return [
        (
            "TANK_GOLDEN_SIGNAL",
            signal(
                "ready",
                session_id="sess-golden",
                metadata={
                    "capabilities": ["asr", "tts", "speaker_id"],
                    **handshake_metadata(),
                },
            ).model_dump_json(),
        ),
        (
            "TANK_GOLDEN_SIGNAL_CAPABILITIES_ACK",
            capabilities_ack(["opus"], session_id="sess-golden").model_dump_json(),
        ),
        (
            "TANK_GOLDEN_TRANSCRIPT",
            transcript(
                "你好",
                speaker="User",
                is_user=True,
                is_final=True,
                msg_id="u_golden",
                session_id="sess-golden",
            ).model_dump_json(),
        ),
        (
            "TANK_GOLDEN_TEXT",
            text(
                "Hello",
                speaker="Brain",
                msg_id="m_golden",
                session_id="sess-golden",
            ).model_dump_json(),
        ),
        (
            "TANK_GOLDEN_UPDATE",
            update(
                "UpdateType.TOOL",
                msg_id="m_golden",
                session_id="sess-golden",
                metadata={"step_id": "m_golden_tool_0", "status": "calling"},
            ).model_dump_json(),
        ),
        (
            "TANK_GOLDEN_ATTACHMENT",
            attachment(
                [WebsocketAttachment(url="/api/media/sess-golden/golden.jpg")],
                content="a photo",
                msg_id="m_golden",
                session_id="sess-golden",
            ).model_dump_json(),
        ),
        (
            "TANK_GOLDEN_CHANNEL_NOTIFICATION",
            channel_notification(
                metadata={
                    "channel_slug": "jobs",
                    "channel_name": "Jobs",
                    "event_type": "job_delivery",
                    "job_name": "golden",
                    "run_id": "run_golden",
                    "messages": [],
                    "message_preview": "",
                }
            ).model_dump_json(),
        ),
        (
            "TANK_GOLDEN_CONVERSATION_METADATA",
            conversation_metadata_updated(
                session_id="sess-golden",
                metadata={"conversation_id": "conv_golden", "title": "Golden"},
            ).model_dump_json(),
        ),
        (
            "TANK_GOLDEN_CONFIG",
            session_config(
                {"instructions": "Reply in French", "vad": {"speech_threshold": 0.7}},
                session_id="sess-golden",
            ).model_dump_json(),
        ),
        (
            "TANK_GOLDEN_CONTEXT_INJECT",
            context_inject(
                "Note from retrieval: the user prefers metric units.",
                role="system",
                session_id="sess-golden",
            ).model_dump_json(),
        ),
    ]


_HEADER_COMMENT = """// Auto-generated by `python -m tank_protocol.schema` — DO NOT EDIT.
// One real wire frame per outbound message type, the P1-2 capabilities-ack
// signal variant, and an unknown-field-tolerance frame. The native test
// suite asserts the C++ parser against these; regenerate from the
// tank_protocol package, never by hand.
"""


def generate_golden_frames_header() -> str:
    """Render the golden frames as an includable C++ header."""
    lines = [_HEADER_COMMENT, "#pragma once", ""]
    for name, wire in _golden_frames():
        lines.append(f'static const char* const {name} = R"JSON({wire})JSON";')
    lines.append("")
    lines.append(
        'static const char* const TANK_GOLDEN_UNKNOWN_FIELD = '
        'R"JSON({"type":"text","content":"future","a_future_field":123})JSON";'
    )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tank_protocol.schema",
        description="Export JSON Schema and device golden frames.",
    )
    parser.add_argument("--schema-out", type=Path, help="Path for the schema JSON")
    parser.add_argument(
        "--golden-out", type=Path, help="Path for the device golden frames header"
    )
    args = parser.parse_args(argv)
    if not args.schema_out and not args.golden_out:
        parser.error("at least one of --schema-out / --golden-out is required")
    if args.schema_out:
        import json

        args.schema_out.parent.mkdir(parents=True, exist_ok=True)
        args.schema_out.write_text(
            json.dumps(build_schema_document(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.schema_out}")
    if args.golden_out:
        args.golden_out.parent.mkdir(parents=True, exist_ok=True)
        args.golden_out.write_text(
            generate_golden_frames_header(), encoding="utf-8"
        )
        print(f"wrote {args.golden_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
