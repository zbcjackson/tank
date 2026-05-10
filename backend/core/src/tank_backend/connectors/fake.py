"""FakeConnector — in-process test double for the Connectors framework.

Used by the Phase 2 e2e test and by any future test that needs to
exercise the inbound/outbound wiring without a real network.

Inbound: tests push events via :meth:`inject_inbound` /
:meth:`inject_edit_as_inbound`. The connector forwards them to its
registered handler.

Outbound: sends/edits are recorded in :attr:`outbox` so tests can assert
on exactly what would have been delivered to the platform.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .base import (
    Attachment,
    Connector,
    ConnectorCapabilities,
    Identity,
    MessageEvent,
    SendResult,
)

logger = logging.getLogger(__name__)


@dataclass
class FakeSendRecord:
    """One entry in :attr:`FakeConnector.outbox`."""

    kind: str                 # "send" | "edit" | "typing"
    identity: Identity
    message_id: str | None = None  # the platform-assigned id for sends/edits
    text: str = ""
    reply_to: str | None = None
    attachments: tuple[Attachment, ...] = ()
    # Sequence counter — useful when asserting order in tests.
    sequence: int = 0


class FakeConnector(Connector):
    """In-process connector. Inbound + outbox, no network."""

    platform = "fake"

    def __init__(
        self,
        instance_name: str = "fake",
        *,
        capabilities: ConnectorCapabilities | None = None,
        fail_send: bool = False,
        fail_edit: bool = False,
    ) -> None:
        caps = capabilities or ConnectorCapabilities(
            supports_edits=True,
            edit_min_interval_ms=0,          # no rate limit for tests
            max_message_length=4000,
            supports_images_in=True,
            supports_images_out=True,
            supports_typing_indicator=True,
        )
        super().__init__(instance_name=instance_name, capabilities=caps)
        self.outbox: list[FakeSendRecord] = []
        self._next_message_id = 1
        self._fail_send = fail_send
        self._fail_edit = fail_edit

    # ── Lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        self._connected = True

    async def stop(self) -> None:
        self._connected = False

    # ── Outbound (recorded) ─────────────────────────────────────────

    async def send(
        self,
        identity: Identity,
        text: str,
        *,
        reply_to: str | None = None,
        attachments: tuple[Attachment, ...] = (),
    ) -> SendResult:
        if self._fail_send:
            return SendResult(ok=False, error="forced send failure")
        message_id = str(self._next_message_id)
        self._next_message_id += 1
        self.outbox.append(FakeSendRecord(
            kind="send",
            identity=identity,
            message_id=message_id,
            text=text,
            reply_to=reply_to,
            attachments=attachments,
            sequence=len(self.outbox),
        ))
        return SendResult(ok=True, message_id=message_id)

    async def edit(
        self,
        identity: Identity,
        message_id: str,
        text: str,
    ) -> SendResult:
        if self._fail_edit:
            return SendResult(ok=False, error="forced edit failure")
        self.outbox.append(FakeSendRecord(
            kind="edit",
            identity=identity,
            message_id=message_id,
            text=text,
            sequence=len(self.outbox),
        ))
        return SendResult(ok=True, message_id=message_id)

    async def send_typing(self, identity: Identity) -> None:
        self.outbox.append(FakeSendRecord(
            kind="typing",
            identity=identity,
            sequence=len(self.outbox),
        ))

    # ── Inbound injection helpers for tests ─────────────────────────

    async def inject_inbound(
        self,
        identity: Identity,
        text: str = "",
        attachments: tuple[Attachment, ...] = (),
        reply_to_message_id: str | None = None,
    ) -> None:
        """Deliver an inbound :class:`MessageEvent` to the registered handler.

        Raises :class:`RuntimeError` if no handler is set (i.e. the
        connector wasn't registered with a :class:`ConnectorManager`).
        """
        if self._on_message is None:
            raise RuntimeError(
                f"FakeConnector '{self.instance_name}': no handler registered; "
                "register via ConnectorManager before injecting",
            )
        event = MessageEvent(
            identity=identity,
            text=text,
            attachments=attachments,
            reply_to_message_id=reply_to_message_id,
        )
        await self._on_message(event)

    # ── Assertion helpers ──────────────────────────────────────────

    def sends(self) -> list[FakeSendRecord]:
        return [r for r in self.outbox if r.kind == "send"]

    def edits(self) -> list[FakeSendRecord]:
        return [r for r in self.outbox if r.kind == "edit"]

    def clear_outbox(self) -> None:
        self.outbox.clear()


@dataclass
class FakeConnectorConfig:
    """Optional helper for tests that want a structured config."""

    instance_name: str = "fake"
    supports_edits: bool = True
    fail_send: bool = False
    fail_edit: bool = False
    extra_capabilities: dict = field(default_factory=dict)
