"""The wire envelope — field-for-field identical to the pre-extraction
``tank_backend.api.schemas`` models so existing clients need no migration.

Every field is serialized on every frame (``model_dump_json`` emits all
nine fields, with explicit ``null`` for unset optionals); clients must
tolerate unknown fields (see README evolution rule 2).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .enums import MessageType

__all__ = ["MessageType", "WebsocketAttachment", "WebsocketMessage"]


class WebsocketAttachment(BaseModel):
    """One assistant-sent media item delivered alongside a chat reply.

    Only ``image`` kinds are emitted today; the schema is shaped for
    future audio / document / video without needing another wire-format
    change. ``url`` is always a path the browser can fetch directly:
    ``media://`` URIs are rewritten to ``/api/media/<session>/<file>``
    server-side; ``http(s)://`` URIs pass through unchanged.
    """

    kind: str = "image"
    url: str
    mime_type: str = "image/jpeg"
    caption: str | None = None


class WebsocketMessage(BaseModel):
    """Base schema for all WebSocket messages."""

    type: MessageType
    content: str = ""
    speaker: str | None = None
    is_user: bool = False
    is_final: bool = False
    msg_id: str | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Assistant-sent attachments. Empty for every frame type except
    # ATTACHMENT.
    attachments: list[WebsocketAttachment] = Field(default_factory=list)
