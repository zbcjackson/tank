"""``echo_image`` — a minimum-viable outbound image tool.

Phase 16 ships this as the first real caller of Tank's outbound-image
path. The tool takes a ``url`` (and an optional ``caption``) and
returns a :class:`ToolResult` whose content includes an
:class:`ImageBlock` — :meth:`ToolManager.execute_tool` picks that up
and posts an ``outbound_attachment`` bus event, which
:class:`~tank_backend.connectors.manager._ImageDispatcher` delivers
through the user's connector.

Naming is deliberately narrow: this tool doesn't generate images, it
just *echoes back* one the user (or the LLM) already has a URL for.
That keeps the first image-producing tool honest about its role and
free of any external API costs. A future Phase 17+ would add
chart/matplotlib rendering and/or image-generation tools.

Usage from the LLM side::

    echo_image(url="https://example.com/cat.jpg", caption="Here's the cat:")

Usage through Tank's chat surface (user speaks to the assistant):

    "show me https://example.com/cat.jpg please"

The LLM picks up the URL and calls ``echo_image``; the user sees the
image with the caption in their Slack/Telegram/Discord channel.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from ..core.content import ImageBlock, TextBlock
from .base import BaseTool, ToolInfo, ToolParameter, ToolResult

logger = logging.getLogger(__name__)


# MIME guesses per URL extension. We don't block unknown extensions —
# connectors happily send ``image/*`` attachments and the end
# platforms (Slack/Telegram/Discord) detect format from the bytes
# themselves. The hint is only for metadata correctness when an LLM
# examines the result.
_EXTENSION_TO_MIME: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".heic": "image/heic",
}


def _guess_mime(url: str) -> str:
    """Best-effort MIME from a URL's path suffix.

    Defaults to ``image/jpeg`` when the extension is missing or
    unrecognised — the most common real-world case, and a safe choice
    because connectors forward the bytes unchanged.
    """
    try:
        path = urlparse(url).path.lower()
    except Exception:
        path = url.lower()
    for ext, mime in _EXTENSION_TO_MIME.items():
        if path.endswith(ext):
            return mime
    return "image/jpeg"


class EchoImageTool(BaseTool):
    """Echo an image URL back to the user as an inline attachment."""

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="echo_image",
            description=(
                "Send an image from a URL back to the user as an "
                "inline attachment in their chat. Use this when the "
                "user shares a link to a picture and wants to see it "
                "rendered, or when you want to visually accompany a "
                "text response with an image you already have a URL "
                "for. This tool does NOT generate or modify images — "
                "it only forwards an existing URL."
            ),
            parameters=[
                ToolParameter(
                    name="url",
                    type="string",
                    description=(
                        "Absolute URL of the image to display "
                        "(https://…). Must point at an image file; "
                        "web pages that embed images won't work."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="caption",
                    type="string",
                    description=(
                        "Optional human-readable caption to show "
                        "alongside the image. Leave blank for no "
                        "caption."
                    ),
                    required=False,
                ),
            ],
        )

    async def execute(
        self, url: str, caption: str = "",
    ) -> ToolResult:
        if not url or not isinstance(url, str):
            return ToolResult(
                content="echo_image: missing or invalid `url`",
                display="Missing image URL",
                error=True,
            )

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return ToolResult(
                content=(
                    f"echo_image: only http(s) URLs are supported; "
                    f"got scheme={parsed.scheme!r}"
                ),
                display=f"Unsupported URL scheme: {parsed.scheme}",
                error=True,
            )

        mime = _guess_mime(url)
        display = caption.strip() or "Sent image"
        logger.info(
            "echo_image: url=%s mime=%s caption=%r", url, mime, display,
        )

        # Content goes back to the LLM so it can reason about what it
        # just showed the user. Keep text + image in the same block
        # list so models see them as one turn.
        content_blocks = [
            TextBlock(text=caption or f"[image displayed from {url}]"),
            ImageBlock(source=url, mime_type=mime),
        ]

        return ToolResult(
            content=content_blocks,
            display=display,
        )
