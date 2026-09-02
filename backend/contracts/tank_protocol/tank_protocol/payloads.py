"""Per-type payload field sets — the typed knowledge that keeps the lenient
envelope honest (protocol plan §4.3).

The wire stays a loose envelope: extra fields are ignored, ``metadata`` is
free-form. What this module adds is a machine-checked statement of which
envelope fields and which ``metadata`` keys are *meaningful* for each
message type. ``validate_envelope`` reports violations as strings — senders
log them at construction time, receivers may log them on ingest — but never
raises: a warning must not break a voice conversation.
"""

from __future__ import annotations

from .enums import MessageType
from .envelope import WebsocketMessage

__all__ = [
    "ENVELOPE_FIELDS",
    "KNOWN_SIGNALS",
    "METADATA_KEYS",
    "validate_envelope",
]

# Envelope fields each message type may legitimately set (non-default).
# Anything else set on a frame of this type is a construction bug.
ENVELOPE_FIELDS: dict[MessageType, frozenset[str]] = {
    MessageType.SIGNAL: frozenset({"content", "msg_id", "session_id", "metadata"}),
    MessageType.TRANSCRIPT: frozenset(
        {"content", "speaker", "is_user", "is_final", "msg_id", "session_id", "metadata"}
    ),
    MessageType.TEXT: frozenset(
        {"content", "speaker", "is_user", "is_final", "msg_id", "session_id", "metadata"}
    ),
    MessageType.UPDATE: frozenset(
        {"content", "speaker", "is_user", "is_final", "msg_id", "session_id", "metadata"}
    ),
    MessageType.INPUT: frozenset({"content", "metadata"}),
    MessageType.ATTACHMENT: frozenset(
        {
            "content",
            "speaker",
            "is_final",
            "msg_id",
            "session_id",
            "metadata",
            "attachments",
        }
    ),
    MessageType.CHANNEL_NOTIFICATION: frozenset({"metadata"}),
    MessageType.CONVERSATION_METADATA_UPDATED: frozenset(
        {"is_final", "session_id", "metadata"}
    ),
}

# Signal names seen on the wire. Advisory documentation (rule 2: unknown
# signals are warn-and-ignore, not errors) — extend when adding a signal.
# Outbound: ready, processing_started, processing_ended, speech_detected,
# recognition_failed, error, conversation_ready, pong, session_reset_failed,
# conversation_resumed, conversation_resume_failed, conversation_created,
# channels_subscribed, channels_unsubscribed, channel_audio_start,
# channel_audio_end. Inbound: the rest.
KNOWN_SIGNALS: frozenset[str] = frozenset(
    {
        # outbound
        "ready",
        "processing_started",
        "processing_ended",
        "speech_detected",
        "recognition_failed",
        "error",
        "conversation_ready",
        "pong",
        "session_reset_failed",
        "conversation_resumed",
        "conversation_resume_failed",
        "conversation_created",
        "channels_subscribed",
        "channels_unsubscribed",
        "channel_audio_start",
        "channel_audio_end",
        # inbound
        "disconnect",
        "wake",
        "idle",
        "interrupt",
        "end_of_utterance",
        "audio_format",
        "ping",
        "resume_conversation",
        "new_conversation",
        "subscribe_channels",
        "unsubscribe_channels",
        "stop_channel_audio",
    }
)

# Known ``metadata`` keys per message type. The exception to strictness:
# ``signal: pong`` echoes whatever the client's ping carried, and
# ``signal: channel_audio_start`` passes through connector-specific keys —
# unknown-key warnings for those are expected and ignorable.
METADATA_KEYS: dict[MessageType, frozenset[str]] = {
    MessageType.SIGNAL: frozenset(
        {
            "capabilities",
            "pipeline_sample_rate",
            "conversation_id",
            "title",
            "error",
            "channels",
            "channel_slug",
            "sample_rate",
        }
    ),
    MessageType.TRANSCRIPT: frozenset({"step_id"}),
    MessageType.TEXT: frozenset({"turn", "step_id"}),
    MessageType.UPDATE: frozenset(
        {
            "update_type",
            "step_id",
            "task_id",
            "tool_name",
            "tool_status",
            "tool_args",
            "name",
            "arguments",
            "status",
            "turn",
            "index",
            "approval_id",
        }
    ),
    MessageType.INPUT: frozenset({"user_id", "attachments"}),
    MessageType.ATTACHMENT: frozenset(),
    MessageType.CHANNEL_NOTIFICATION: frozenset(
        {
            "channel_slug",
            "channel_name",
            "event_type",
            "job_name",
            "run_id",
            "messages",
            "message_preview",
        }
    ),
    MessageType.CONVERSATION_METADATA_UPDATED: frozenset({"conversation_id", "title"}),
}

_FIELDS_WITH_DEFAULTS = frozenset(
    {"content", "is_user", "is_final", "metadata", "attachments"}
)


def _field_is_set(msg: WebsocketMessage, field: str) -> bool:
    value = getattr(msg, field)
    if field in _FIELDS_WITH_DEFAULTS:
        return bool(value)
    return value is not None


def validate_envelope(msg: WebsocketMessage) -> list[str]:
    """Return human-readable violations for a frame; empty list means clean.

    Two categories: ``field:`` (an envelope field set that is not meaningful
    for this message type) and ``metadata:`` (a metadata key not documented
    for this type). Both are advisory — see module docstring.
    """
    violations: list[str] = []
    allowed = ENVELOPE_FIELDS[msg.type]
    for name in (
        "content",
        "speaker",
        "is_user",
        "is_final",
        "msg_id",
        "session_id",
        "metadata",
        "attachments",
    ):
        if name not in allowed and _field_is_set(msg, name):
            violations.append(f"field: {name} is not meaningful for {msg.type.value}")
    known_keys = METADATA_KEYS[msg.type]
    for key in msg.metadata:
        if key not in known_keys:
            violations.append(
                f"metadata: key {key!r} is not documented for {msg.type.value}"
            )
    return violations
