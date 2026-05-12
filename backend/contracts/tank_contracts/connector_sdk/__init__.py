"""Shared helpers for Tank connector plugins — the *Connector SDK*.

The Tank ``Connector`` ABC (in ``tank_contracts.connector``) is the
contract platform adapters must implement. The SDK in this subpackage
is the *convenience layer* around it — a collection of pure helpers
plus one lifecycle coordinator class that every in-tree connector
plugin uses today, and any future plugin can adopt to skip re-deriving
the patterns.

All symbols are re-exported at the top level of this subpackage so
plugins can write ``from tank_contracts.connector_sdk import ...``
without drilling into submodules.

**Scope of the SDK** (what it does):

- Factory validation (``validate_spec``, ``require_string_field``).
- Approval-prompt text + button-payload codec
  (``build_prompt_text``, ``encode_action``, ``decode_action``).
- Text truncation (``truncate_for_platform``).
- Background-task lifecycle (``BackgroundTaskRunner``).
- Shared wire-format constants (``APPROVAL_*``).

**What it explicitly doesn't do**:

- Own the ``Connector`` ABC — that still lives in
  ``tank_contracts.connector``.
- Wrap platform-specific SDK calls — each plugin's ``send``, ``edit``,
  ``_make_identity`` etc. stay in the plugin itself because their
  divergence from platform to platform is the whole point.
- Provide a ``BaseConnector`` superclass — composition via helper
  functions keeps the plugin code legible without the hidden coupling
  that comes with fat base classes.
"""

from __future__ import annotations

from .approval import build_prompt_text, decode_action, encode_action
from .constants import (
    APPROVAL_ACTION_PREFIX,
    APPROVAL_CHOICE_ALLOW_FOREVER,
    APPROVAL_CHOICE_ALLOW_ONCE,
    APPROVAL_CHOICE_DENY,
    APPROVAL_VALID_CHOICES,
)
from .factory import require_string_field, validate_spec
from .lifecycle import BackgroundTaskRunner
from .text import truncate_for_platform

__all__ = [
    "APPROVAL_ACTION_PREFIX",
    "APPROVAL_CHOICE_ALLOW_FOREVER",
    "APPROVAL_CHOICE_ALLOW_ONCE",
    "APPROVAL_CHOICE_DENY",
    "APPROVAL_VALID_CHOICES",
    "BackgroundTaskRunner",
    "build_prompt_text",
    "decode_action",
    "encode_action",
    "require_string_field",
    "truncate_for_platform",
    "validate_spec",
]
