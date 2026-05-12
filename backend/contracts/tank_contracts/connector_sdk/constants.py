"""Shared constants for the Tank connector SDK.

These constants are the wire-format glue between Tank's
``tank_backend.connectors.ApprovalBroker`` and every platform-specific
connector plugin. Moving them out of each plugin's private namespace
guarantees all four parties (broker, Telegram, Slack, Discord) agree
on the same literal strings forever — a single-point-of-truth that
protects against one plugin drifting on e.g. ``"deny"`` vs
``"reject"``.

Plugins import from here; the broker imports from here; tests assert
against the imported constants rather than re-literalising them.
"""

from __future__ import annotations


# Prefix used on every approval-button wire payload: Telegram's
# ``callback_data``, Slack's ``action_id``, Discord's ``custom_id``.
# The full shape is ``{APPROVAL_ACTION_PREFIX}:{choice}:{approval_id}``.
APPROVAL_ACTION_PREFIX = "approve"

# The three choices an admin can click on an approval prompt. These are
# the wire strings that travel through the button payload — they're
# also the values the ``ApprovalBroker.resolve`` method accepts as its
# ``choice`` argument.
APPROVAL_CHOICE_ALLOW_ONCE = "allow_once"
APPROVAL_CHOICE_ALLOW_FOREVER = "allow_forever"
APPROVAL_CHOICE_DENY = "deny"

# Convenience set of valid choices — callers can test `choice in
# APPROVAL_VALID_CHOICES` without importing the individual constants.
APPROVAL_VALID_CHOICES: frozenset[str] = frozenset({
    APPROVAL_CHOICE_ALLOW_ONCE,
    APPROVAL_CHOICE_ALLOW_FOREVER,
    APPROVAL_CHOICE_DENY,
})


__all__ = [
    "APPROVAL_ACTION_PREFIX",
    "APPROVAL_CHOICE_ALLOW_FOREVER",
    "APPROVAL_CHOICE_ALLOW_ONCE",
    "APPROVAL_CHOICE_DENY",
    "APPROVAL_VALID_CHOICES",
]
