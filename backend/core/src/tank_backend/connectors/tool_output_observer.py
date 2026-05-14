"""ToolOutputObserver — surface non-text tool results to the user.

Phase 17 refactor (extracted from :class:`ToolManager`). The observer
listens for ``tool_completed`` bus events that
:meth:`ToolManager.execute_tool` posts after every tool invocation,
inspects the returned :class:`ToolResult` for non-text
:class:`ContentBlock` s, and re-publishes them as
``outbound_attachment`` events that the existing
:class:`_ImageDispatcher` (connector side) and the WebSocket endpoint
(web-UI side) already consume.

Why a separate module
---------------------

Before the refactor, ``ToolManager.execute_tool`` knew about
``ImageBlock``, ``outbound_attachment`` payload shapes, and the
specific UI affordance of "image with caption." That violated the
Open/Closed Principle — adding a new content kind (audio, document)
meant editing :class:`ToolManager`, even though
:class:`ToolManager` 's actual responsibility is tool registry and
invocation, not the user-facing surface.

Pulling the logic into an observer that subscribes to a generic
``tool_completed`` event keeps :class:`ToolManager` closed for
modification and opens an extension point. Anything that wants to
react to "a tool just produced a result" — audit logging, telemetry,
attachment delivery, future content kinds — subscribes here without
touching the manager.

Wiring
------

:class:`Assistant._init_bus` constructs one observer per assistant
instance after both the bus and the tool manager are available. The
observer's lifetime matches the assistant's; no explicit cleanup is
needed because the bus's subscriber list is garbage-collected with
the assistant.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..core.content import ImageBlock
from ..pipeline.bus import BusMessage
from ..tools.base import ToolResult

if TYPE_CHECKING:
    from ..pipeline.bus import Bus

logger = logging.getLogger(__name__)


class ToolOutputObserver:
    """Convert ``tool_completed`` events into ``outbound_attachment`` events.

    The observer is a pure subscriber — no state, no I/O. Each
    incoming :class:`BusMessage` payload is expected to look like::

        {"tool_name": str, "result": ToolResult | str}

    For :class:`ToolResult` payloads carrying :class:`ImageBlock` s,
    one ``outbound_attachment`` event is published. For string-only
    results, error results, or results with no image content, the
    observer is a no-op so it doesn't wake the image dispatcher for
    nothing.

    String results from legacy tools are tolerated for the same
    reason :meth:`ToolResult.to_blocks` handles them: backward-compat
    with pre-multimodal tools that returned plain strings.
    """

    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        bus.subscribe("tool_completed", self._on_tool_completed)

    def _on_tool_completed(self, message: BusMessage) -> None:
        payload = message.payload or {}
        result = payload.get("result")
        tool_name = payload.get("tool_name") or "<unknown>"

        # ``ToolResult`` is the structured shape; strings (legacy tools)
        # have no image content by definition, so we exit early.
        if not isinstance(result, ToolResult):
            return

        blocks = result.to_blocks()
        image_blocks = [b for b in blocks if isinstance(b, ImageBlock)]
        if not image_blocks:
            return

        # Tool's ``display`` string becomes the caption — most tools
        # use ``display`` for the short human-readable summary, which
        # is exactly the right thing to render alongside an image.
        caption = result.display or None
        try:
            self._bus.post(
                BusMessage(
                    type="outbound_attachment",
                    source=f"tool:{tool_name}",
                    payload={
                        "msg_id": None,
                        "blocks": image_blocks,
                        "caption": caption,
                    },
                )
            )
        except Exception:
            # Don't let a bus publish failure cascade. The text result
            # already reached the LLM via the user-role follow-up
            # message; worst case the user doesn't see the image on
            # this turn.
            logger.exception(
                "ToolOutputObserver: failed to emit outbound_attachment "
                "for %s", tool_name,
            )


__all__ = ["ToolOutputObserver"]
