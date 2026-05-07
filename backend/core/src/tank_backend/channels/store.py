"""ChannelStore — ORM-backed persistence for channel metadata.

Messages are stored via the :class:`ConversationStore` (channel →
conversation_id). This store only manages the slug → conversation_id
mapping, metadata, and per-channel read state.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from ..persistence import Database
from ..persistence.models import ChannelReadStateRow, ChannelRow
from .models import ChannelData, ChannelSummary, _humanize_slug, validate_slug

if TYPE_CHECKING:
    from ..context.store import ConversationStore

logger = logging.getLogger(__name__)


class ChannelStore:
    """ORM-backed store for channel metadata."""

    def __init__(self, db: Database) -> None:
        self._db = db

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
        with self._db.session() as s:
            row = s.get(ChannelRow, slug)
            return None if row is None else _row_to_channel(row)

    def get_by_conversation_id(self, conversation_id: str) -> ChannelData | None:
        """Reverse lookup: find the channel that owns a conversation_id, or None."""
        with self._db.session() as s:
            row = s.execute(
                select(ChannelRow).where(ChannelRow.conversation_id == conversation_id)
            ).scalar_one_or_none()
            return None if row is None else _row_to_channel(row)

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
        with self._db.session() as s:
            rows = s.execute(
                select(
                    ChannelRow.slug,
                    ChannelRow.name,
                    ChannelRow.description,
                    ChannelRow.conversation_id,
                    ChannelRow.updated_at,
                ).order_by(ChannelRow.updated_at.desc())
            ).all()
            read_state = self._get_read_state(s)

        summaries: list[ChannelSummary] = []
        for slug, name, description, conv_id, updated_at in rows:
            msg_count = 0
            last_msg_at = updated_at
            if conversation_store is not None:
                conv = conversation_store.load(conv_id)
                if conv is not None:
                    msg_count = len(conv.messages)
                    last_msg_at = conv.start_time.isoformat()
            last_read = read_state.get(slug, 0)
            unread = max(0, msg_count - last_read)
            summaries.append(
                ChannelSummary(
                    slug=slug,
                    name=name,
                    description=description,
                    message_count=msg_count,
                    last_message_at=last_msg_at,
                    unread_count=unread,
                )
            )
        return summaries

    def update(self, slug: str, **kwargs: str) -> ChannelData | None:
        """Update channel name and/or description. Returns updated channel or None."""
        now = datetime.now(timezone.utc).isoformat()
        with self._db.session() as s:
            row = s.get(ChannelRow, slug)
            if row is None:
                return None
            if "name" in kwargs:
                row.name = kwargs["name"]
            if "description" in kwargs:
                row.description = kwargs["description"]
            row.updated_at = now
            return _row_to_channel(row)

    def delete(
        self, slug: str, conversation_store: ConversationStore | None = None,
    ) -> bool:
        """Delete a channel and optionally its underlying conversation."""
        channel = self.get(slug)
        if channel is None:
            return False

        if conversation_store is not None:
            conversation_store.delete(channel.conversation_id)

        with self._db.session() as s:
            s.execute(delete(ChannelRow).where(ChannelRow.slug == slug))
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

    # ── Read tracking ───────────────────────────────────────────────

    def mark_read(
        self, slug: str, conversation_store: ConversationStore | None = None,
    ) -> None:
        """Mark a channel as read by recording the current message count."""
        channel = self.get(slug)
        if channel is None:
            return

        msg_count = 0
        if conversation_store is not None:
            conv = conversation_store.load(channel.conversation_id)
            if conv is not None:
                msg_count = len(conv.messages)

        with self._db.session() as s:
            existing = s.get(ChannelReadStateRow, slug)
            if existing is None:
                s.add(ChannelReadStateRow(
                    slug=slug, last_read_message_count=msg_count,
                ))
            else:
                existing.last_read_message_count = msg_count

    # ── Lifecycle ──────────────────────────────────────────────────

    def close(self) -> None:
        """No-op: the Database owns the engine lifecycle."""
        return

    # ── Internal ──────────────────────────────────────────────────────

    def _insert(self, channel: ChannelData) -> None:
        with self._db.session() as s:
            s.add(ChannelRow(
                slug=channel.slug,
                name=channel.name,
                conversation_id=channel.conversation_id,
                description=channel.description,
                auto_created=int(channel.auto_created),
                created_at=channel.created_at,
                updated_at=channel.updated_at,
            ))

    @staticmethod
    def _get_read_state(session) -> dict[str, int]:
        rows = session.execute(
            select(ChannelReadStateRow.slug, ChannelReadStateRow.last_read_message_count)
        ).all()
        return dict(rows)


def _row_to_channel(row: ChannelRow) -> ChannelData:
    return ChannelData(
        slug=row.slug,
        name=row.name,
        conversation_id=row.conversation_id,
        description=row.description,
        auto_created=bool(row.auto_created),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
