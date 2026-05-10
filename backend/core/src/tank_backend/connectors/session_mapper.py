"""SessionMapper — :class:`Identity` → Tank ``session_id``.

Maps a platform-native identity (``telegram`` chat 12345, say) to a
durable Tank session. First lookup for an unknown identity auto-creates
a :class:`ChannelStore` entry (which in turn creates the underlying
conversation), so every external chat becomes a first-class Tank
channel — visible in the UI, subject to NON_DESTRUCTIVE compaction, and
accessible via ``/api/channels``.

Returning users resolve to the same session; the framework never forks
conversations unless the external identity itself changes.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from ..channels.models import validate_slug
from .identity_store import ConnectorIdentityStore

if TYPE_CHECKING:
    from ..channels.store import ChannelStore
    from ..context.store import ConversationStore
    from .base import Identity

logger = logging.getLogger(__name__)


# Slug segments must match channels.models._SLUG_RE; the store validates
# the final result, but we sanitize defensively so we don't synthesize a
# slug the validator will reject.
_SLUG_INVALID_CHARS = re.compile(r"[^\w\-]", re.UNICODE)


def _sanitize_segment(value: str) -> str:
    """Lowercase and strip anything that would fail slug validation."""
    s = _SLUG_INVALID_CHARS.sub("-", value.strip().lower())
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def derive_slug(identity: Identity) -> str:
    """Build a stable, human-readable slug from an :class:`Identity`.

    Format: ``<platform>-<external>``. Falls back to a padded form if
    either piece is too short to satisfy the validator (≥3 chars
    start-and-end with a word char).
    """
    platform = _sanitize_segment(identity.platform) or "connector"
    external = _sanitize_segment(identity.external_id) or "unknown"
    slug = f"{platform}-{external}"
    # The validator caps slugs at 50 chars; truncate preserving the
    # platform prefix so different external_ids don't collide.
    if len(slug) > 50:
        # Keep "<platform>-" prefix, truncate external portion.
        head = f"{platform}-"
        remaining = 50 - len(head)
        # If the platform prefix itself is too long, truncate the whole slug.
        slug = slug[:50] if remaining < 3 else head + external[:remaining]
    # Guarantee minimum length (validator requires ≥3 with start/end word chars).
    if len(slug) < 3:
        slug = (slug + "-x")[:50]
    return slug


class SessionMapper:
    """Resolve a connector :class:`Identity` to a durable session id.

    First call for a new identity auto-creates a :class:`ChannelStore`
    channel and records the mapping; subsequent calls return the stored
    ``session_id``.
    """

    def __init__(
        self,
        identity_store: ConnectorIdentityStore,
        channel_store: ChannelStore,
        conversation_store: ConversationStore,
    ) -> None:
        self._identity_store = identity_store
        self._channel_store = channel_store
        self._conversation_store = conversation_store

    def resolve(self, identity: Identity) -> str:
        """Return the ``session_id`` for this identity, creating one on first sight."""
        existing = self._identity_store.get(identity.platform, identity.external_id)
        if existing is not None:
            return existing.session_id

        slug = derive_slug(identity)
        # Defensive: validate once so failures surface with a clear error.
        validate_slug(slug)

        channel = self._channel_store.get(slug)
        if channel is None:
            display = identity.display_name or slug
            channel = self._channel_store.create(
                slug=slug,
                name=display,
                conversation_store=self._conversation_store,
                description=f"{identity.platform}: {identity.external_id}",
            )
            logger.info(
                "SessionMapper: auto-created channel '%s' for identity %s/%s",
                slug, identity.platform, identity.external_id,
            )

        record = self._identity_store.put_if_absent(
            platform=identity.platform,
            external_id=identity.external_id,
            session_id=channel.conversation_id,
        )
        return record.session_id
