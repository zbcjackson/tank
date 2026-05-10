"""Core abstractions for the Connectors framework.

The ABCs and value types now live in ``tank_contracts.connector`` so
plugin packages can depend on the public contract alone. This module is
a thin re-export kept so existing ``tank_backend.connectors.base``
imports continue to work.
"""

from __future__ import annotations

from tank_contracts.connector import (
    Attachment,
    Connector,
    ConnectorCapabilities,
    Identity,
    MessageEvent,
    MessageHandler,
    SendResult,
)

__all__ = [
    "Attachment",
    "Connector",
    "ConnectorCapabilities",
    "Identity",
    "MessageEvent",
    "MessageHandler",
    "SendResult",
]
