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


@dataclass
class FakeApprovalPrompt:
    """One entry in :attr:`FakeConnector.approval_prompts`.

    Phase 10 tests assert on this list to verify the broker routed the
    approval request through the connector's button-send path — the
    broker drops the pending entry if ``send_approval_prompt`` raises,
    so observing the record is how we confirm "the prompt was sent."
    """

    admin_identity: Identity
    approval_id: str
    sender: Identity
    preview: str


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
        # Phase 10: recorded approval-prompt invocations. Tests exercising
        # the REQUIRE_APPROVAL flow assert on this list to verify the
        # broker actually routed the request through here.
        self.approval_prompts: list[FakeApprovalPrompt] = []

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

    # Phase 10: record approval-prompt invocations so tests can assert
    # the broker routed the request correctly. Overriding the default
    # ABC (which raises :class:`NotImplementedError`) lets
    # ``REQUIRE_APPROVAL`` flows work end-to-end in the test harness.
    async def send_approval_prompt(
        self,
        *,
        admin_identity: Identity,
        approval_id: str,
        sender: Identity,
        preview: str,
    ) -> None:
        self.approval_prompts.append(FakeApprovalPrompt(
            admin_identity=admin_identity,
            approval_id=approval_id,
            sender=sender,
            preview=preview,
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
