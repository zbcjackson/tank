"""Text helpers for connector plugins.

Each platform enforces a different per-message character limit —
Telegram 4096 for messages and 1024 for captions, Slack 40 000 overall,
Discord 2000. When a Tank reply exceeds the cap, the connector must
trim it before sending, and it must do so in a way that's visible to
the user (otherwise the reply silently loses its tail).

The three connectors today use identical "truncate and append ellipsis"
logic. This module lifts it so every plugin (and any future one) shares
the same convention.
"""

from __future__ import annotations


def truncate_for_platform(text: str, cap: int) -> str:
    """Truncate ``text`` to at most ``cap`` characters.

    When the text already fits, it's returned unchanged. When it
    doesn't, the tail is replaced with a single horizontal-ellipsis
    character (``"…"``) so the user sees evidence of the trim — a
    silent truncation would leave replies mysteriously cut off.

    Edge cases:

    - ``cap <= 0`` returns an empty string. The prior inlined logic
      would have silently produced nonsense (``text[:-1]`` for
      ``cap == 0``); formalising the guard prevents that trap from
      re-surfacing in future callers.
    - Exactly ``cap`` characters passes through untouched — the cap is
      inclusive.

    The ellipsis takes one character, so the truncated prefix is
    ``cap - 1`` chars of original content. That matches what operators
    configure when they say e.g. "Telegram messages cap at 4096": the
    final output is 4096 characters, of which the last is ``"…"``.
    """
    if cap <= 0:
        return ""
    if len(text) <= cap:
        return text
    return text[: cap - 1] + "…"


__all__ = ["truncate_for_platform"]
