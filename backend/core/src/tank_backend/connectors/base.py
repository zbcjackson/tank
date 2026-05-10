"""Core abstractions for the Connectors framework.

A *connector* is one configured instance of a platform adapter (e.g. a
specific Telegram bot, a specific Slack workspace). It receives inbound
messages from its platform, dispatches them to Tank's Assistant, and
delivers Assistant replies back to the platform.

Design goals:
- Transport-agnostic: no HTTP/WebSocket/long-poll assumptions in the base
  contract. Each concrete adapter picks its own transport.
- Testable without network: the :class:`FakeConnector` (in ``fake.py``)
  exercises every seam of the framework.
- Decoupled from Assistant: the manager wires inbound/outbound; connectors
  never touch the pipeline or Bus directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Literal

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Identity & inbound events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Identity:
    """Platform-specific user/chat identity.

    The ``(platform, external_id)`` pair is the lookup key the
    :class:`SessionMapper` uses to resume the right conversation. The
    ``external_id`` should be canonicalized by the connector — e.g. a
    Telegram connector might emit ``"tg:chat:12345"`` for group chat
    12345 and ``"tg:user:67890"`` for a DM with user 67890 — so two
    different connector extensions never clash inside one platform.

    ``display_name`` is advisory only; it appears in logs and is passed
    to ``Assistant.process_input(user=...)`` so the LLM sees a friendly
    attribution.
    """

    platform: str
    external_id: str
    display_name: str = ""
    is_group: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Attachment:
    """Platform-agnostic inbound/outbound attachment envelope.

    The manager translates inbound :class:`Attachment` s into Tank
    :class:`ContentBlock` s before handing them to
    :meth:`Assistant.process_input`. Outbound attachments flow the other
    way — the connector converts them to platform-native uploads.

    ``data`` is either raw bytes (binary content) or a string (URL /
    inline text). ``mime_type`` disambiguates.
    """

    kind: Literal["image", "audio", "file", "text"]
    data: bytes | str
    mime_type: str = ""
    filename: str = ""


@dataclass(frozen=True)
class MessageEvent:
    """An inbound message from a platform.

    Connectors construct these and call their registered handler. The
    :class:`ConnectorManager` is the handler — it routes the event to
    the right Assistant and wires up outbound streaming.
    """

    identity: Identity
    text: str = ""
    attachments: tuple[Attachment, ...] = ()
    reply_to_message_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Outbound results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SendResult:
    """Outcome of a send/edit call.

    Successful sends populate ``message_id`` so the caller can edit it
    later (streaming). Failures populate ``error`` with a short reason;
    ``ok=False`` with no error is reserved for "feature not supported".
    """

    ok: bool
    message_id: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Capability flags
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConnectorCapabilities:
    """Feature flags describing what a specific connector instance supports.

    The :class:`StreamConsumer` reads these to pick a send strategy:

    - ``supports_edits=True`` → edit-transport: one send, then periodic
      edits as tokens arrive, final edit on completion.
    - ``supports_edits=False`` → final-only: buffer all text, one send
      at completion.

    Rate-limited platforms should set ``edit_min_interval_ms`` to at
    least the minimum edit interval they tolerate (Telegram: 1000,
    Slack: 500, WeChat: no edits at all → ``supports_edits=False``).
    """

    supports_edits: bool = False
    edit_min_interval_ms: int = 1000
    max_message_length: int = 4000
    supports_images_in: bool = False
    supports_images_out: bool = False
    supports_voice_in: bool = False
    supports_voice_out: bool = False
    supports_typing_indicator: bool = False


# ---------------------------------------------------------------------------
# Connector ABC
# ---------------------------------------------------------------------------


MessageHandler = Callable[[MessageEvent], Awaitable[None]]


class Connector(ABC):
    """Abstract platform adapter. One instance per configured account.

    Subclasses:

    - Set ``platform`` as a class attribute (``"telegram"``, etc.).
    - Populate ``capabilities`` in ``__init__``.
    - Implement ``start``/``stop``/``send``. Optionally override ``edit``
      and ``send_typing``.
    - Call ``self._on_message(event)`` whenever an inbound message
      arrives. The handler is set by the :class:`ConnectorManager` via
      ``set_message_handler``.
    """

    platform: ClassVar[str] = ""  # override in subclasses

    def __init__(self, instance_name: str, capabilities: ConnectorCapabilities) -> None:
        self.instance_name = instance_name
        self.capabilities = capabilities
        self._on_message: MessageHandler | None = None
        self._connected: bool = False

    # ── Lifecycle ───────────────────────────────────────────────────

    @abstractmethod
    async def start(self) -> None:
        """Open the connector's transport (long-poll, webhook, socket).

        Must set ``self._connected = True`` on success. Should be
        idempotent — calling ``start`` twice on an already-started
        connector is a no-op.
        """

    @abstractmethod
    async def stop(self) -> None:
        """Close the connector's transport cleanly.

        Must set ``self._connected = False``. Should be idempotent.
        """

    @property
    def connected(self) -> bool:
        return self._connected

    # ── Outbound ────────────────────────────────────────────────────

    @abstractmethod
    async def send(
        self,
        identity: Identity,
        text: str,
        *,
        reply_to: str | None = None,
        attachments: tuple[Attachment, ...] = (),
    ) -> SendResult:
        """Send a message to the given identity.

        ``reply_to`` is a platform-native message id if the send should
        be a reply/quote; connectors that don't support threading may
        ignore it.
        """

    async def edit(
        self,
        identity: Identity,
        message_id: str,
        text: str,
    ) -> SendResult:
        """Edit a previously sent message.

        Default implementation reports the feature as unsupported.
        Connectors with ``capabilities.supports_edits=True`` MUST
        override this.
        """
        return SendResult(ok=False, error="edits not supported by this connector")

    async def send_typing(self, identity: Identity) -> None:  # noqa: B027 — intentionally overridable no-op
        """Show a typing indicator to the given identity.

        Default implementation is a no-op. Connectors with
        ``capabilities.supports_typing_indicator=True`` SHOULD override.
        """

    # ── Inbound handler registration ─────────────────────────────────

    def set_message_handler(self, handler: MessageHandler) -> None:
        """Register the callback that receives inbound :class:`MessageEvent` s.

        The :class:`ConnectorManager` calls this during registration.
        Subclasses invoke ``self._on_message(event)`` from their inbound
        loop.
        """
        self._on_message = handler


__all__ = [
    "Attachment",
    "Connector",
    "ConnectorCapabilities",
    "Identity",
    "MessageEvent",
    "MessageHandler",
    "SendResult",
]
