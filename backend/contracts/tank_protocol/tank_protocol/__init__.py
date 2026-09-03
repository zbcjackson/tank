"""Tank client WebSocket wire contract — single source of truth.

See README.md for evolution rules. Dependencies: pydantic only.
"""

# Defined before the submodule imports: handshake.py reads it via
# `from . import __version__` while the package is still initializing.
__version__ = "0.1.0"

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
from .handshake import KNOWN_PROTOCOL_FEATURES, handshake_metadata
from .payloads import (
    ENVELOPE_FIELDS,
    KNOWN_SIGNALS,
    METADATA_KEYS,
    validate_envelope,
)

__all__ = [
    "ENVELOPE_FIELDS",
    "KNOWN_PROTOCOL_FEATURES",
    "KNOWN_SIGNALS",
    "METADATA_KEYS",
    "MessageType",
    "WebsocketAttachment",
    "WebsocketMessage",
    "__version__",
    "attachment",
    "channel_notification",
    "conversation_metadata_updated",
    "handshake_metadata",
    "signal",
    "text",
    "transcript",
    "update",
    "validate_envelope",
]
