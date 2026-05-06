"""Channel subscription manager — tracks which sessions listen to which channels."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ChannelSubscriptionManager:
    """In-memory bidirectional mapping of sessions to channel subscriptions.

    Not persisted — clients re-subscribe on each WebSocket connect.
    Thread-safe within a single asyncio event loop (no lock needed).
    """

    def __init__(self) -> None:
        self._session_to_channels: dict[str, set[str]] = {}
        self._channel_to_sessions: dict[str, set[str]] = {}

    def subscribe(self, session_id: str, channel_slugs: list[str]) -> None:
        """Subscribe a session to one or more channels."""
        session_set = self._session_to_channels.setdefault(session_id, set())
        for slug in channel_slugs:
            session_set.add(slug)
            self._channel_to_sessions.setdefault(slug, set()).add(session_id)
        logger.debug("Session %s subscribed to %s", session_id, channel_slugs)

    def unsubscribe(self, session_id: str, channel_slugs: list[str]) -> None:
        """Unsubscribe a session from one or more channels."""
        session_set = self._session_to_channels.get(session_id)
        if session_set is None:
            return
        for slug in channel_slugs:
            session_set.discard(slug)
            channel_set = self._channel_to_sessions.get(slug)
            if channel_set is not None:
                channel_set.discard(session_id)
                if not channel_set:
                    del self._channel_to_sessions[slug]
        if not session_set:
            del self._session_to_channels[session_id]
        logger.debug("Session %s unsubscribed from %s", session_id, channel_slugs)

    def get_subscribers(self, channel_slug: str) -> set[str]:
        """Return all session IDs subscribed to a channel."""
        return self._channel_to_sessions.get(channel_slug, set()).copy()

    def get_subscriptions(self, session_id: str) -> set[str]:
        """Return all channel slugs a session is subscribed to."""
        return self._session_to_channels.get(session_id, set()).copy()

    def remove_session(self, session_id: str) -> None:
        """Remove all subscriptions for a session (on disconnect)."""
        slugs = self._session_to_channels.pop(session_id, set())
        for slug in slugs:
            channel_set = self._channel_to_sessions.get(slug)
            if channel_set is not None:
                channel_set.discard(session_id)
                if not channel_set:
                    del self._channel_to_sessions[slug]
        if slugs:
            logger.debug("Removed session %s from channels %s", session_id, slugs)
