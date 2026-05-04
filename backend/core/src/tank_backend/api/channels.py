"""Channels REST API — CRUD for persistent named conversations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..channels.models import slugify

if TYPE_CHECKING:
    from ..channels.store import ChannelStore
    from ..context.store import ConversationStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channels", tags=["channels"], redirect_slashes=False)

# Injected from server.py
_channel_store: ChannelStore | None = None
_conversation_store: ConversationStore | None = None


def set_channel_store(store: ChannelStore) -> None:
    global _channel_store  # noqa: PLW0603
    _channel_store = store


def set_conversation_store(store: ConversationStore | None) -> None:
    global _conversation_store  # noqa: PLW0603
    _conversation_store = store


def _get_channel_store() -> ChannelStore:
    if _channel_store is None:
        raise HTTPException(503, "Channel store not initialized")
    return _channel_store


def _get_conversation_store() -> ConversationStore | None:
    return _conversation_store


# ------------------------------------------------------------------
# Request / response models
# ------------------------------------------------------------------


class CreateChannelRequest(BaseModel):
    name: str
    slug: str | None = None
    description: str = ""


class UpdateChannelRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class PromoteRequest(BaseModel):
    conversation_id: str
    slug: str | None = None
    name: str


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get("")
def list_channels():
    """List all channels, most recently updated first."""
    store = _get_channel_store()
    conv_store = _get_conversation_store()
    channels = store.list_channels(conv_store)
    return [c.__dict__ for c in channels]


@router.post("", status_code=201)
def create_channel(req: CreateChannelRequest):
    """Create a new channel."""
    store = _get_channel_store()
    conv_store = _get_conversation_store()
    if conv_store is None:
        raise HTTPException(503, "Conversation store not initialized")

    slug = req.slug or slugify(req.name)
    try:
        channel = store.create(slug, req.name, conv_store, req.description)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    return channel.to_dict()


@router.get("/{slug}")
def get_channel(slug: str):
    """Get channel details by slug."""
    store = _get_channel_store()
    channel = store.get(slug)
    if channel is None:
        raise HTTPException(404, f"Channel '{slug}' not found")
    return channel.to_dict()


@router.put("/{slug}")
def update_channel(slug: str, req: UpdateChannelRequest):
    """Update channel name and/or description."""
    store = _get_channel_store()
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")
    channel = store.update(slug, **updates)
    if channel is None:
        raise HTTPException(404, f"Channel '{slug}' not found")
    return channel.to_dict()


@router.put("/{slug}/read", status_code=204)
def mark_channel_read(slug: str):
    """Mark a channel as read (clears unread indicator)."""
    store = _get_channel_store()
    channel = store.get(slug)
    if channel is None:
        raise HTTPException(404, f"Channel '{slug}' not found")
    conv_store = _get_conversation_store()
    store.mark_read(slug, conv_store)


@router.delete("/{slug}", status_code=204)
def delete_channel(slug: str):
    """Delete a channel and its underlying conversation."""
    store = _get_channel_store()
    conv_store = _get_conversation_store()
    if not store.delete(slug, conv_store):
        raise HTTPException(404, f"Channel '{slug}' not found")


@router.post("/promote", status_code=201)
def promote_conversation(req: PromoteRequest):
    """Promote an existing conversation to a channel."""
    store = _get_channel_store()
    conv_store = _get_conversation_store()
    slug = req.slug or slugify(req.name)
    try:
        channel = store.promote_conversation(
            conversation_id=req.conversation_id,
            slug=slug,
            name=req.name,
            conversation_store=conv_store,
        )
    except ValueError as e:
        if "already exists" in str(e):
            raise HTTPException(409, str(e)) from e
        if "not found" in str(e):
            raise HTTPException(404, str(e)) from e
        raise HTTPException(400, str(e)) from e
    return channel.to_dict()
