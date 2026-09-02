"""Constructor factories — the single sanctioned path for building outbound
frames (protocol plan W7).

Signatures take primitives only: this package must never import backend
internals. Callers map their own domain types (``DisplayMessage``,
``SignalMessage``, ...) onto these parameters. Field defaults mirror the
18 pre-existing construction sites so factory output is wire-identical.
"""

from __future__ import annotations

import logging
from typing import Any

from .enums import MessageType
from .envelope import WebsocketAttachment, WebsocketMessage
from .payloads import validate_envelope

logger = logging.getLogger(__name__)

__all__ = [
    "attachment",
    "channel_notification",
    "conversation_metadata_updated",
    "signal",
    "text",
    "transcript",
    "update",
]


def _build(msg_type: MessageType, **fields: Any) -> WebsocketMessage:
    msg = WebsocketMessage(type=msg_type, **fields)
    for violation in validate_envelope(msg):
        # Advisory only — see payloads.validate_envelope.
        logger.warning("protocol: %s (type=%s)", violation, msg.type.value)
    return msg


def signal(
    content: str,
    *,
    msg_id: str | None = None,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> WebsocketMessage:
    """Control signal frame (ready, interrupt, pong, ...)."""
    return _build(
        MessageType.SIGNAL,
        content=content,
        msg_id=msg_id,
        session_id=session_id,
        metadata=metadata or {},
    )


def transcript(
    content: str,
    *,
    speaker: str | None = None,
    is_user: bool = True,
    is_final: bool = False,
    msg_id: str | None = None,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> WebsocketMessage:
    """ASR result — partials stream with ``is_final=False``."""
    return _build(
        MessageType.TRANSCRIPT,
        content=content,
        speaker=speaker,
        is_user=is_user,
        is_final=is_final,
        msg_id=msg_id,
        session_id=session_id,
        metadata=metadata or {},
    )


def text(
    content: str,
    *,
    speaker: str | None = None,
    is_final: bool = False,
    msg_id: str | None = None,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> WebsocketMessage:
    """LLM response delta; ``msg_id`` (+ ``turn`` via UI layer) streams steps."""
    return _build(
        MessageType.TEXT,
        content=content,
        speaker=speaker,
        is_final=is_final,
        msg_id=msg_id,
        session_id=session_id,
        metadata=metadata or {},
    )


def update(
    update_type: str,
    *,
    content: str = "",
    speaker: str | None = "Brain",
    is_final: bool = False,
    msg_id: str | None = None,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> WebsocketMessage:
    """UI update (thinking / tool / approval / worker activity).

    ``update_type`` is the final wire string (e.g. ``"UpdateType.TOOL"``,
    ``"ACTIVITY.TOOL"``) and lands in ``metadata["update_type"]`` — always
    authoritative, overwriting any same-named key in ``metadata``.
    """
    merged = {**(metadata or {}), "update_type": update_type}
    return _build(
        MessageType.UPDATE,
        content=content,
        speaker=speaker,
        is_final=is_final,
        msg_id=msg_id,
        session_id=session_id,
        metadata=merged,
    )


def attachment(
    attachments: list[WebsocketAttachment],
    *,
    content: str = "",
    speaker: str | None = "Brain",
    msg_id: str | None = None,
    session_id: str | None = None,
) -> WebsocketMessage:
    """Assistant-sent media; always ``is_final=True`` (never streamed)."""
    return _build(
        MessageType.ATTACHMENT,
        content=content,
        speaker=speaker,
        is_final=True,
        msg_id=msg_id,
        session_id=session_id,
        attachments=attachments,
    )


def channel_notification(
    *,
    metadata: dict[str, Any] | None = None,
) -> WebsocketMessage:
    """Channel message push (job deliveries etc.); broadcast, no session."""
    return _build(MessageType.CHANNEL_NOTIFICATION, metadata=metadata or {})


def conversation_metadata_updated(
    *,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> WebsocketMessage:
    """Out-of-band conversation metadata change (new title etc.)."""
    return _build(
        MessageType.CONVERSATION_METADATA_UPDATED,
        is_final=True,
        session_id=session_id,
        metadata=metadata or {},
    )
