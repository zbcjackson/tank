"""Tank client WebSocket wire contract — single source of truth.

See README.md for evolution rules. Dependencies: pydantic only.
"""

from .enums import MessageType
from .envelope import WebsocketAttachment, WebsocketMessage
from .factories import (
    attachment,
    channel_notification,
    conversation_metadata_updated,
    signal,
    text,
    transcript,
    update,
)
from .payloads import ENVELOPE_FIELDS, KNOWN_SIGNALS, METADATA_KEYS, validate_envelope

__version__ = "0.1.0"

__all__ = [
    "ENVELOPE_FIELDS",
    "KNOWN_SIGNALS",
    "METADATA_KEYS",
    "MessageType",
    "WebsocketAttachment",
    "WebsocketMessage",
    "__version__",
    "attachment",
    "channel_notification",
    "conversation_metadata_updated",
    "signal",
    "text",
    "transcript",
    "update",
    "validate_envelope",
]
