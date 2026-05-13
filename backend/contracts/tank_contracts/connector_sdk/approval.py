"""Approval-prompt helpers shared across connector plugins.

The approval workflow (Phase 10) sends an admin a three-button prompt
whenever an unknown sender messages a connector. Every plugin renders
the same prompt text and encodes its buttons with the same
``approve:<choice>:<approval_id>`` wire format; this module centralises
both so the broker, Telegram, Slack, and Discord are guaranteed to
agree forever.

* :func:`build_prompt_text` — the one human-readable prompt. Plugins
  wrap it in platform-specific markup (Slack's ``*bold*``, Telegram's
  plain text, Discord's Markdown) but the content is identical.

* :func:`encode_action` / :func:`decode_action` — the two-way wire
  codec for button payloads. ``decode_action`` returns ``None`` on any
  malformed input so callers can drop bad clicks with one guard.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .constants import (
    APPROVAL_ACTION_PREFIX,
    APPROVAL_CHOICE_ALLOW_FOREVER,
    APPROVAL_CHOICE_ALLOW_ONCE,
    APPROVAL_CHOICE_DENY,
)

if TYPE_CHECKING:
    from ..connector import Identity


def build_prompt_text(sender: Identity, preview: str) -> str:
    """Render the admin-facing approval prompt body.

    Returns the exact three-line text every connector uses today —
    centralised here so future copy edits land in one place:

    .. code-block:: text

        New sender wants to talk to me:
        • <display name> (<external_id>)
        • message preview: <preview>

    When the sender has no ``display_name`` we drop the parenthesised
    form and show just the ``external_id`` — otherwise admins see
    redundant parentheses around the same identifier.

    The preview is included verbatim. Callers that want to cap its
    length should do so before calling (see
    :func:`.text.truncate_for_platform`) — the SDK stays dumb here so
    platform-specific caption limits don't leak into the prompt-text
    helper.
    """
    if sender.display_name:
        sender_label = f"{sender.display_name} ({sender.external_id})"
    else:
        sender_label = sender.external_id

    return (
        "New sender wants to talk to me:\n"
        f"• {sender_label}\n"
        f"• message preview: {preview}"
    )


def encode_action(choice: str, approval_id: str) -> str:
    """Pack ``(choice, approval_id)`` into a single wire string.

    The result fits Telegram's 64-byte ``callback_data`` cap comfortably
    (16 prefix chars max + 16 approval_id chars = well under limit) and
    is legal for Slack's ``action_id`` + Discord's ``custom_id`` both.
    """
    return f"{APPROVAL_ACTION_PREFIX}:{choice}:{approval_id}"


def decode_action(raw: str) -> tuple[str, str] | None:
    """Parse ``approve:<choice>:<approval_id>`` back into its parts.

    Returns ``(choice, approval_id)`` on valid input, or ``None`` for
    any malformed payload — wrong prefix, wrong arity, empty choice,
    empty approval_id. Returning ``None`` rather than raising lets
    callers drop malformed clicks silently:

    .. code-block:: python

        decoded = decode_action(raw)
        if decoded is None:
            return
        choice, approval_id = decoded

    The single ``maxsplit=2`` split is intentional — ``approval_id`` is
    opaque and may contain additional ``:`` characters if future phases
    want to extend it. Only the prefix and choice positions are fixed.
    """
    parts = raw.split(":", 2)
    if len(parts) != 3:
        return None
    prefix, choice, approval_id = parts
    if prefix != APPROVAL_ACTION_PREFIX:
        return None
    if not choice or not approval_id:
        return None
    return choice, approval_id


__all__ = [
    "build_outcome_text",
    "build_prompt_text",
    "decode_action",
    "encode_action",
]


# ---------------------------------------------------------------------------
# Approval-outcome rendering (post-click confirmation)
# ---------------------------------------------------------------------------


# Glyphs chosen to echo the button labels in ``build_prompt_text``'s
# sibling view so an admin sees a visually consistent pair (prompt
# button ``✅`` matches outcome ``✅``). Plain emoji works across
# Telegram, Slack, and Discord renderers without markup quirks.
_OUTCOME_GLYPHS: dict[str, str] = {
    APPROVAL_CHOICE_ALLOW_ONCE: "✅",
    APPROVAL_CHOICE_ALLOW_FOREVER: "🔓",
    APPROVAL_CHOICE_DENY: "🚫",
}

_OUTCOME_VERBS: dict[str, str] = {
    APPROVAL_CHOICE_ALLOW_ONCE: "Approved once",
    APPROVAL_CHOICE_ALLOW_FOREVER: "Approved forever",
    APPROVAL_CHOICE_DENY: "Denied",
}


def build_outcome_text(
    *,
    sender: Identity,
    choice: str,
    admin: Identity | None = None,
) -> str:
    """Render the admin-facing confirmation for a resolved approval.

    Every connector calls this after ``broker.resolve`` succeeds, then
    edits the original prompt message to swap out the buttons for this
    text. Admin sees:

    .. code-block:: text

        ✅ Approved once for Alice (tg:user:99) by Admin

    When ``admin`` is ``None`` the ``by ...`` suffix is omitted. That
    path exists for test paths that resolve without a real admin
    identity — real clicks always carry one.

    Unknown choices render as a fallback "Resolved: <raw>" so a future
    broker that grows new verdict types doesn't throw a ``KeyError``
    from the button-click handler — a weird-but-visible label is
    strictly better than an exception that leaves the buttons frozen.
    """
    glyph = _OUTCOME_GLYPHS.get(choice, "ℹ️")
    verb = _OUTCOME_VERBS.get(choice, f"Resolved: {choice}")

    sender_label = (
        f"{sender.display_name} ({sender.external_id})"
        if sender.display_name
        else sender.external_id
    )

    text = f"{glyph} {verb} for {sender_label}"
    if admin is not None:
        admin_label = admin.display_name or admin.external_id
        text = f"{text} by {admin_label}"
    return text
