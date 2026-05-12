"""ORM row types — internal to the persistence layer.

These are **not** domain types. Each store maps between ORM rows
(``*Row``) and the frozen dataclasses exported from its own module
(``ChannelData``, ``JobDefinition``, etc.). Callers never see these.
"""

from __future__ import annotations

from .channels import ChannelReadStateRow, ChannelRow
from .connector_dynamic_allowlist import ConnectorDynamicAllowlistRow
from .connector_identities import ConnectorIdentityRow
from .conversations import ConversationRow
from .jobs import JobRow, JobRunRow
from .speakers import EmbeddingRow, SpeakerRow

__all__ = [
    "ChannelReadStateRow",
    "ChannelRow",
    "ConnectorDynamicAllowlistRow",
    "ConnectorIdentityRow",
    "ConversationRow",
    "EmbeddingRow",
    "JobRow",
    "JobRunRow",
    "SpeakerRow",
]
