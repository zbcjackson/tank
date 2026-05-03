"""ChannelStore — SQLite-backed persistence for channel metadata."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .models import ChannelData, ChannelSummary, _humanize_slug, validate_slug

if TYPE_CHECKING:
    from ..context.store import ConversationStore

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS channels (
    slug            TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    auto_created    INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""


class ChannelStore:
    """SQLite-backed store for channel metadata.

    Messages are stored via the ConversationStore (channel -> conversation_id).
    This store only manages the channel -> conversation_id mapping and metadata.
    """

    def __init__(self, db_path: str | Path) -> None:
        path = Path(db_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()

    # ── CRUD ──────────────────────────────────────────────────────────

    def create(
        self,
        slug: str,
        name: str,
        conversation_store: ConversationStore,
        description: str = "",
    ) -> ChannelData:
        """Create a new channel with an underlying conversation."""
        validate_slug(slug)
        if self.get(slug) is not None:
            raise ValueError(f"Channel '{slug}' already exists")

        now = datetime.now(timezone.utc).isoformat()
        from ..context.conversation import ConversationData

        conversation = ConversationData.new(
            system_prompt=f"You are responding in the channel '{name}'."
        )
        conversation_store.save(conversation)

        channel = ChannelData(
            slug=slug,
            name=name,
            conversation_id=conversation.id,
            description=description,
            auto_created=False,
            created_at=now,
            updated_at=now,
        )
        self._insert(channel)
        logger.info("Created channel '%s' (conversation_id=%s)", slug, conversation.id)
        return channel

    def get(self, slug: str) -> ChannelData | None:
        """Get a channel by slug, or None if not found."""
        row = self._conn.execute(
            "SELECT slug, name, conversation_id, description, auto_created, "
            "created_at, updated_at FROM channels WHERE slug = ?",
            (slug,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_channel(row)

    def get_by_conversation_id(self, conversation_id: str) -> ChannelData | None:
        """Reverse lookup: find the channel that owns a conversation_id, or None."""
        row = self._conn.execute(
            "SELECT slug, name, conversation_id, description, auto_created, "
            "created_at, updated_at FROM channels WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_channel(row)

    def get_or_create(
        self,
        slug: str,
        name: str | None = None,
        conversation_store: ConversationStore | None = None,
    ) -> ChannelData:
        """Get existing channel, or auto-create if it doesn't exist."""
        existing = self.get(slug)
        if existing is not None:
            return existing

        if conversation_store is None:
            raise ValueError(
                f"Channel '{slug}' does not exist and no conversation_store provided"
            )

        validate_slug(slug)
        display_name = name or _humanize_slug(slug)
        now = datetime.now(timezone.utc).isoformat()
        from ..context.conversation import ConversationData

        conversation = ConversationData.new(
            system_prompt=f"You are responding in the channel '{display_name}'."
        )
        conversation_store.save(conversation)

        channel = ChannelData(
            slug=slug,
            name=display_name,
            conversation_id=conversation.id,
            auto_created=True,
            created_at=now,
            updated_at=now,
        )
        self._insert(channel)
        logger.info("Auto-created channel '%s' (conversation_id=%s)", slug, conversation.id)
        return channel

    def list_channels(
        self, conversation_store: ConversationStore | None = None,
    ) -> list[ChannelSummary]:
        """List all channels, most recently updated first."""
        rows = self._conn.execute(
            "SELECT slug, name, description, conversation_id, updated_at "
            "FROM channels ORDER BY updated_at DESC"
        ).fetchall()

        summaries: list[ChannelSummary] = []
        for slug, name, description, conv_id, updated_at in rows:
            msg_count = 0
            last_msg_at = updated_at
            if conversation_store is not None:
                conv = conversation_store.load(conv_id)
                if conv is not None:
                    msg_count = len(conv.messages)
                    # Best-effort last message timestamp from conversation start_time
                    last_msg_at = conv.start_time.isoformat()
            summaries.append(
                ChannelSummary(
                    slug=slug,
                    name=name,
                    description=description,
                    message_count=msg_count,
                    last_message_at=last_msg_at,
                )
            )
        return summaries

    def update(self, slug: str, **kwargs: Any) -> ChannelData | None:
        """Update channel name and/or description. Returns updated channel or None."""
        channel = self.get(slug)
        if channel is None:
            return None

        name = kwargs.get("name", channel.name)
        description = kwargs.get("description", channel.description)
        now = datetime.now(timezone.utc).isoformat()

        self._conn.execute(
            "UPDATE channels SET name = ?, description = ?, updated_at = ? WHERE slug = ?",
            (name, description, now, slug),
        )
        self._conn.commit()
        return ChannelData(
            slug=channel.slug,
            name=name,
            conversation_id=channel.conversation_id,
            description=description,
            auto_created=channel.auto_created,
            created_at=channel.created_at,
            updated_at=now,
        )

    def delete(
        self, slug: str, conversation_store: ConversationStore | None = None,
    ) -> bool:
        """Delete a channel and optionally its underlying conversation."""
        channel = self.get(slug)
        if channel is None:
            return False

        if conversation_store is not None:
            conversation_store.delete(channel.conversation_id)

        self._conn.execute("DELETE FROM channels WHERE slug = ?", (slug,))
        self._conn.commit()
        logger.info("Deleted channel '%s'", slug)
        return True

    def promote_conversation(
        self,
        conversation_id: str,
        slug: str,
        name: str,
        conversation_store: ConversationStore | None = None,
    ) -> ChannelData:
        """Wrap an existing conversation as a channel."""
        validate_slug(slug)
        if self.get(slug) is not None:
            raise ValueError(f"Channel '{slug}' already exists")

        # Verify the conversation exists
        if conversation_store is not None:
            conv = conversation_store.load(conversation_id)
            if conv is None:
                raise ValueError(f"Conversation '{conversation_id}' not found")

        now = datetime.now(timezone.utc).isoformat()
        channel = ChannelData(
            slug=slug,
            name=name,
            conversation_id=conversation_id,
            auto_created=False,
            created_at=now,
            updated_at=now,
        )
        self._insert(channel)
        logger.info(
            "Promoted conversation '%s' to channel '%s'", conversation_id, slug,
        )
        return channel

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    # ── Internal ──────────────────────────────────────────────────────

    def _insert(self, channel: ChannelData) -> None:
        self._conn.execute(
            "INSERT INTO channels (slug, name, conversation_id, description, "
            "auto_created, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                channel.slug,
                channel.name,
                channel.conversation_id,
                channel.description,
                int(channel.auto_created),
                channel.created_at,
                channel.updated_at,
            ),
        )
        self._conn.commit()

    @staticmethod
    def _row_to_channel(row: tuple[Any, ...]) -> ChannelData:
        slug, name, conv_id, description, auto_created, created_at, updated_at = row
        return ChannelData(
            slug=slug,
            name=name,
            conversation_id=conv_id,
            description=description,
            auto_created=bool(auto_created),
            created_at=created_at,
            updated_at=updated_at,
        )
