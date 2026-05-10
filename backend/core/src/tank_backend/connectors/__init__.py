"""Connectors framework — platform-agnostic message adapters.

See :mod:`tank_backend.connectors.base` for the core abstractions.
"""

from __future__ import annotations

from .base import (
    Attachment,
    Connector,
    ConnectorCapabilities,
    Identity,
    MessageEvent,
    MessageHandler,
    SendResult,
)
from .fake import FakeConnector, FakeSendRecord
from .identity_store import ConnectorIdentityRecord, ConnectorIdentityStore
from .manager import ConnectorManager
from .session_mapper import SessionMapper, derive_slug
from .stream_consumer import StreamConsumer

__all__ = [
    "Attachment",
    "Connector",
    "ConnectorCapabilities",
    "ConnectorIdentityRecord",
    "ConnectorIdentityStore",
    "ConnectorManager",
    "FakeConnector",
    "FakeSendRecord",
    "Identity",
    "MessageEvent",
    "MessageHandler",
    "SendResult",
    "SessionMapper",
    "StreamConsumer",
    "derive_slug",
]
