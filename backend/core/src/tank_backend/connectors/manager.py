"""ConnectorManager — lifecycle + dispatch for configured connectors.

Owns a collection of :class:`Connector` instances (one per configured
platform account), routes their inbound messages through the session
mapper into the existing :class:`ConnectionManager`, and wires outbound
streaming replies through a per-session :class:`StreamConsumer`.

The manager is additive: the existing WebSocket entrypoint at
``api/router.py`` continues to work unchanged. A connector-free deploy
behaves exactly as today.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..core.content import ImageBlock, TextBlock
from .exceptions import DuplicateConnectorError
from .stream_consumer import StreamConsumer

if TYPE_CHECKING:
    from collections.abc import Iterable

    from ..api.manager import ConnectionManager
    from ..core.assistant import Assistant
    from ..core.content import ContentBlock
    from .base import (
        Attachment,
        Connector,
        Identity,
        MessageEvent,
    )
    from .session_mapper import SessionMapper

logger = logging.getLogger("ConnectorManager")


class ConnectorManager:
    """Registers connectors, starts them at lifespan startup, tears them
    down at shutdown, and routes messages in both directions.

    Thread model: connector inbound callbacks may arrive on any thread
    (the platform SDK's loop). :meth:`_on_inbound` is an ``async`` method
    that runs on the FastAPI event loop — connectors schedule it with
    ``asyncio.run_coroutine_threadsafe`` or await it directly if they
    already live on the main loop.
    """

    def __init__(
        self,
        connection_manager: ConnectionManager,
        session_mapper: SessionMapper,
    ) -> None:
        self._conn_mgr = connection_manager
        self._session_mapper = session_mapper
        self._connectors: dict[str, Connector] = {}
        # Track StreamConsumers so we can GC them when sessions end.
        # Keyed by (instance_name, session_id).
        self._consumers: dict[tuple[str, str], StreamConsumer] = {}

    # ── Registration ────────────────────────────────────────────────

    def register(self, connector: Connector) -> None:
        """Add a :class:`Connector` instance. Must be called before
        :meth:`start_all`.
        """
        if connector.instance_name in self._connectors:
            raise DuplicateConnectorError(
                f"Connector instance '{connector.instance_name}' already registered"
            )
        connector.set_message_handler(
            # Bind the connector at registration time so the handler knows
            # its source when events arrive.
            self._make_inbound_handler(connector),
        )
        self._connectors[connector.instance_name] = connector
        logger.info(
            "Registered connector '%s' (platform=%s)",
            connector.instance_name, connector.platform,
        )

    def _make_inbound_handler(self, connector: Connector):
        async def handler(event: MessageEvent) -> None:
            await self._on_inbound(connector, event)
        return handler

    def iter_connectors(self) -> Iterable[Connector]:
        return self._connectors.values()

    def get(self, instance_name: str) -> Connector | None:
        return self._connectors.get(instance_name)

    # ── Lifecycle ───────────────────────────────────────────────────

    async def start_all(self) -> None:
        """Start every registered connector. Failures are logged but do
        not abort — other connectors keep starting."""
        for connector in self._connectors.values():
            try:
                await connector.start()
                logger.info("Started connector '%s'", connector.instance_name)
            except Exception:
                logger.exception(
                    "Failed to start connector '%s'", connector.instance_name,
                )

    async def stop_all(self) -> None:
        """Stop every connector and release per-session consumers."""
        for connector in self._connectors.values():
            try:
                await connector.stop()
                logger.info("Stopped connector '%s'", connector.instance_name)
            except Exception:
                logger.exception(
                    "Failed to stop connector '%s'", connector.instance_name,
                )
        self._consumers.clear()

    # ── Dispatch ────────────────────────────────────────────────────

    async def _on_inbound(
        self, source: Connector, event: MessageEvent,
    ) -> None:
        """Route an inbound platform message to the right Assistant."""
        identity = event.identity

        try:
            session_id = self._session_mapper.resolve(identity)
        except Exception:
            logger.exception(
                "SessionMapper.resolve failed for %s/%s via '%s'",
                identity.platform, identity.external_id, source.instance_name,
            )
            return

        assistant, is_new = await self._conn_mgr.get_or_create_assistant(session_id)

        if is_new:
            self._attach_outbound_stream(assistant, source, identity, session_id)

        blocks = self._attachments_to_blocks(event.attachments)

        user_display = identity.display_name or identity.external_id
        try:
            assistant.process_input(
                text=event.text,
                user=user_display,
                attachments=blocks,
            )
        except Exception:
            logger.exception(
                "Assistant.process_input raised for session %s via '%s'",
                session_id, source.instance_name,
            )

    # ── Outbound wiring ────────────────────────────────────────────

    def _attach_outbound_stream(
        self,
        assistant: Assistant,
        source: Connector,
        identity: Identity,
        session_id: str,
    ) -> None:
        """Subscribe a :class:`StreamConsumer` to the Assistant's Bus
        so outbound ``ui_message`` events flow back through ``source``.
        """
        consumer = StreamConsumer(connector=source, identity=identity)
        assistant._bus.subscribe("ui_message", consumer.on_ui_message)  # noqa: SLF001
        key = (source.instance_name, session_id)
        self._consumers[key] = consumer
        logger.debug(
            "Attached StreamConsumer: connector=%s session=%s",
            source.instance_name, session_id,
        )

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _attachments_to_blocks(
        attachments: tuple[Attachment, ...],
    ) -> list[ContentBlock] | None:
        """Convert platform-agnostic attachments to Tank content blocks.

        Only inline-reachable kinds are mapped for Phase 2:

        - ``text`` → :class:`TextBlock`
        - ``image`` with a string URL → :class:`ImageBlock` (URL source)
        - ``image`` with bytes → skipped (Phase 3 integrates MediaStore)
        - ``audio`` / ``file`` → skipped (Phase 3+)

        Returns ``None`` when nothing survived the filter so
        ``Assistant.process_input(attachments=None)`` stays the common
        zero-overhead path.
        """
        if not attachments:
            return None

        blocks: list[ContentBlock] = []
        for att in attachments:
            if att.kind == "text" and isinstance(att.data, str):
                blocks.append(TextBlock(text=att.data))
            elif att.kind == "image" and isinstance(att.data, str):
                blocks.append(ImageBlock(
                    source=att.data,
                    mime_type=att.mime_type or "image/png",
                ))
            else:
                logger.debug(
                    "ConnectorManager: dropping unsupported attachment "
                    "(kind=%s, data=%s) — handled in Phase 3+",
                    att.kind, type(att.data).__name__,
                )
        return blocks or None
