"""Connectors framework — platform-agnostic message adapters.

See :mod:`tank_backend.connectors.base` for the core abstractions.
"""

from __future__ import annotations

from .approval import (
    CHOICE_ALLOW_FOREVER,
    CHOICE_ALLOW_ONCE,
    CHOICE_DENY,
    VALID_CHOICES,
    ApprovalBroker,
    PendingApproval,
)
from .base import (
    Attachment,
    Connector,
    ConnectorCapabilities,
    Identity,
    MessageEvent,
    MessageHandler,
    SendResult,
)
from .dynamic_allowlist import DynamicAllowlistGrant, DynamicAllowlistStore
from .fake import FakeApprovalPrompt, FakeConnector, FakeSendRecord
from .identity_store import ConnectorIdentityRecord, ConnectorIdentityStore
from .manager import ConnectorManager
from .session_mapper import SessionMapper, derive_slug
from .stream_consumer import StreamConsumer

__all__ = [
    "CHOICE_ALLOW_FOREVER",
    "CHOICE_ALLOW_ONCE",
    "CHOICE_DENY",
    "VALID_CHOICES",
    "ApprovalBroker",
    "Attachment",
    "Connector",
    "ConnectorCapabilities",
    "ConnectorIdentityRecord",
    "ConnectorIdentityStore",
    "ConnectorManager",
    "DynamicAllowlistGrant",
    "DynamicAllowlistStore",
    "FakeApprovalPrompt",
    "FakeConnector",
    "FakeSendRecord",
    "Identity",
    "MessageEvent",
    "MessageHandler",
    "PendingApproval",
    "SendResult",
    "SessionMapper",
    "StreamConsumer",
    "derive_slug",
]
