"""Title generation observer — runs LLM titling out-of-band.

Subscribes to ``conversation_title_needed`` bus messages (posted by Brain
after the first assistant turn) and dispatches the ``TitleGenerator``
on the assistant's event loop. Successful generation emits a
``ui_message`` carrying ``ConversationMetadataUpdate`` so the WebSocket
forwarder can push the new title to the matching session.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ...core.events import ConversationMetadataUpdate
from ..bus import Bus, BusMessage

if TYPE_CHECKING:
    from ...context.title_generator import TitleGenerator

logger = logging.getLogger(__name__)


class TitleGenerationObserver:
    """Bridge from ``conversation_title_needed`` bus events to TitleGenerator."""

    def __init__(
        self,
        bus: Bus,
        generator: TitleGenerator,
        loop: asyncio.AbstractEventLoop | None = None,
        on_title_generated: Callable[[str, str], Any] | None = None,
    ) -> None:
        self._bus = bus
        self._generator = generator
        self._loop = loop
        self._on_title_generated = on_title_generated
        bus.subscribe("conversation_title_needed", self._on_message)

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind to the asyncio loop the generator should run on.

        Called once from ``Assistant.start()`` after the loop is known.
        """
        self._loop = loop

    def _on_message(self, message: BusMessage) -> None:
        payload = message.payload or {}
        conversation_id = payload.get("conversation_id")
        if not isinstance(conversation_id, str) or not conversation_id:
            return
        loop = self._loop
        if loop is None or not loop.is_running():
            logger.debug(
                "Title generation skipped: no running loop for %s",
                conversation_id,
            )
            return
        asyncio.run_coroutine_threadsafe(
            self._generate_and_publish(conversation_id), loop,
        )

    async def _generate_and_publish(self, conversation_id: str) -> None:
        try:
            title = await self._generator.generate(conversation_id)
        except Exception:
            logger.warning(
                "TitleGenerator raised for %s", conversation_id, exc_info=True,
            )
            return
        if not title:
            return
        if self._on_title_generated is not None:
            self._on_title_generated(conversation_id, title)
        self._bus.post(BusMessage(
            type="ui_message",
            source="title_generator",
            payload=ConversationMetadataUpdate(
                conversation_id=conversation_id, title=title,
            ),
            timestamp=time.time(),
        ))
