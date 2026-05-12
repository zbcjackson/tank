"""Unit tests for :class:`ApprovalBroker`.

The broker sits between :class:`ConnectorManager`'s allowlist gate and
the connector's SDK-level button-click handler. Tests here exercise:

- ``request`` parks a pending entry and invokes ``send_approval_prompt``.
- ``resolve`` handles the three admin choices (once / forever / deny).
- Stale ``approval_id`` and non-admin clickers are no-ops.
- The preview helper truncates long messages sensibly.
- ``send_approval_prompt`` raising :class:`NotImplementedError` drops
  the pending entry so operators see the misconfiguration in logs.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from tank_contracts.connector import Identity, MessageEvent

from tank_backend.connectors.approval import (
    CHOICE_ALLOW_FOREVER,
    CHOICE_ALLOW_ONCE,
    CHOICE_DENY,
    ApprovalBroker,
    _preview_text,
)


def _sender(ext_id: str = "tg:user:99", name: str = "Alice") -> Identity:
    return Identity(
        platform="telegram",
        external_id=ext_id,
        display_name=name,
        is_group=False,
        metadata={},
    )


def _event(text: str = "hi tank", **ident_kw) -> MessageEvent:
    return MessageEvent(identity=_sender(**ident_kw), text=text)


def _admin(ext_id: str = "tg:user:42") -> Identity:
    return Identity(
        platform="telegram",
        external_id=ext_id,
        display_name="Admin",
        is_group=False,
        metadata={"user_id": 42},
    )


@pytest.fixture()
def broker_fixture():
    """Minimal broker + fakes. Returns ``(broker, connector, dispatch_calls,
    dynamic_store, one_shot_passes)`` for the test to drive."""
    connector = MagicMock()
    connector.instance_name = "t"
    connector.platform = "telegram"
    connector.send = AsyncMock()
    connector.send_approval_prompt = AsyncMock()

    dispatch_calls: list[tuple] = []

    async def dispatch(source, event) -> None:
        dispatch_calls.append((source, event))

    dynamic_store = MagicMock()
    dynamic_store.grant = MagicMock()

    one_shot_passes: set[str] = set()

    broker = ApprovalBroker(
        instance_name="t",
        admin_external_ids={"tg:user:42"},
        dynamic_store=dynamic_store,
        dispatch=dispatch,
        one_shot_passes=one_shot_passes,
    )
    return broker, connector, dispatch_calls, dynamic_store, one_shot_passes


class TestRequest:
    async def test_parks_pending_and_sends_prompt(self, broker_fixture) -> None:
        broker, connector, _, _, _ = broker_fixture
        aid = await broker.request(connector, _event())

        assert aid is not None
        assert len(aid) == 16   # token_hex(8) → 16 chars
        assert broker.pending_count == 1
        connector.send_approval_prompt.assert_awaited_once()
        kw = connector.send_approval_prompt.call_args.kwargs
        assert kw["approval_id"] == aid
        assert kw["admin_identity"].external_id == "tg:user:42"
        assert kw["sender"].external_id == "tg:user:99"
        assert kw["preview"] == "hi tank"

    async def test_no_admins_returns_none_and_drops_request(self) -> None:
        """When admin_external_ids is empty the broker refuses to park
        a request — operators need the loud warning, not a silent pile
        of pending entries no one can ever approve."""
        broker = ApprovalBroker(
            instance_name="t",
            admin_external_ids=set(),
            dynamic_store=MagicMock(),
            dispatch=AsyncMock(),
            one_shot_passes=set(),
        )
        connector = MagicMock()
        connector.instance_name = "t"
        connector.platform = "telegram"
        connector.send_approval_prompt = AsyncMock()

        aid = await broker.request(connector, _event())
        assert aid is None
        assert broker.pending_count == 0
        connector.send_approval_prompt.assert_not_awaited()

    async def test_not_implemented_drops_entry(self) -> None:
        """Connectors that don't implement ``send_approval_prompt``
        raise :class:`NotImplementedError`; the broker logs + drops the
        pending entry so it doesn't leak."""
        broker = ApprovalBroker(
            instance_name="t",
            admin_external_ids={"tg:user:42"},
            dynamic_store=MagicMock(),
            dispatch=AsyncMock(),
            one_shot_passes=set(),
        )
        connector = MagicMock()
        connector.instance_name = "t"
        connector.platform = "fake"
        connector.send_approval_prompt = AsyncMock(
            side_effect=NotImplementedError("test"),
        )

        aid = await broker.request(connector, _event())
        assert aid is None
        assert broker.pending_count == 0

    async def test_send_exception_also_drops_entry(self) -> None:
        broker = ApprovalBroker(
            instance_name="t",
            admin_external_ids={"tg:user:42"},
            dynamic_store=MagicMock(),
            dispatch=AsyncMock(),
            one_shot_passes=set(),
        )
        connector = MagicMock()
        connector.instance_name = "t"
        connector.platform = "telegram"
        connector.send_approval_prompt = AsyncMock(
            side_effect=RuntimeError("network"),
        )

        aid = await broker.request(connector, _event())
        assert aid is None
        assert broker.pending_count == 0


class TestResolveHappyPaths:
    async def test_allow_once_adds_to_one_shot_set_and_replays(
        self, broker_fixture,
    ) -> None:
        broker, connector, dispatch_calls, _, one_shot_passes = broker_fixture
        aid = await broker.request(connector, _event())

        await broker.resolve(aid, CHOICE_ALLOW_ONCE, _admin())

        assert "tg:user:99" in one_shot_passes
        assert len(dispatch_calls) == 1
        assert dispatch_calls[0][1].text == "hi tank"
        assert broker.pending_count == 0

    async def test_allow_forever_grants_and_replays(
        self, broker_fixture,
    ) -> None:
        broker, connector, dispatch_calls, dynamic_store, _ = broker_fixture
        aid = await broker.request(connector, _event())

        await broker.resolve(aid, CHOICE_ALLOW_FOREVER, _admin())

        dynamic_store.grant.assert_called_once()
        call_kw = dynamic_store.grant.call_args.kwargs
        assert call_kw["instance_name"] == "t"
        assert call_kw["platform"] == "telegram"
        assert call_kw["external_id"] == "tg:user:99"
        assert call_kw["granted_by"] == "tg:user:42"
        assert len(dispatch_calls) == 1

    async def test_deny_sends_reply_no_dispatch_no_grant(
        self, broker_fixture,
    ) -> None:
        broker, connector, dispatch_calls, dynamic_store, _ = broker_fixture
        aid = await broker.request(connector, _event())

        await broker.resolve(aid, CHOICE_DENY, _admin())

        connector.send.assert_awaited()
        reply = connector.send.call_args.kwargs["text"].lower()
        assert "not authorised" in reply
        assert dispatch_calls == []
        dynamic_store.grant.assert_not_called()
        assert broker.pending_count == 0


class TestResolveEdgeCases:
    async def test_stale_approval_id_is_noop(self, broker_fixture) -> None:
        broker, _, dispatch_calls, dynamic_store, _ = broker_fixture
        await broker.resolve("deadbeef" * 2, CHOICE_ALLOW_FOREVER, _admin())
        assert dispatch_calls == []
        dynamic_store.grant.assert_not_called()

    async def test_non_admin_clicker_is_rejected(self, broker_fixture) -> None:
        """Phase 10 security gate: even though Telegram / Slack /
        Discord buttons can be clicked by anyone who sees them, the
        broker only honours clicks from configured admins. The pending
        entry is still popped (so a real admin can't re-approve it),
        but no replay + no grant."""
        broker, connector, dispatch_calls, dynamic_store, _ = broker_fixture
        aid = await broker.request(connector, _event())

        not_admin = Identity(
            platform="telegram",
            external_id="tg:user:1000",  # not in admin set
            metadata={},
        )
        await broker.resolve(aid, CHOICE_ALLOW_FOREVER, not_admin)

        dynamic_store.grant.assert_not_called()
        assert dispatch_calls == []
        # Pending entry was popped — deliberate so a real admin can't
        # double-approve. Any further click on that button id no-ops
        # via the stale-id path.
        assert broker.pending_count == 0

    async def test_unknown_choice_keeps_pending_entry(
        self, broker_fixture,
    ) -> None:
        """Bad choice strings bail out *before* popping the entry, so
        a real admin can retry. Ordering matters: validate first."""
        broker, connector, dispatch_calls, _, _ = broker_fixture
        aid = await broker.request(connector, _event())
        await broker.resolve(aid, "maybe", _admin())
        assert broker.pending_count == 1
        assert dispatch_calls == []


class TestPreviewHelper:
    def test_short_text_preserved_verbatim(self) -> None:
        assert _preview_text(_event(text="hi")) == "hi"

    def test_long_text_truncated_with_ellipsis(self) -> None:
        long = " ".join(["word"] * 80)
        out = _preview_text(_event(text=long))
        assert len(out) <= 200
        assert out.endswith("…")

    def test_empty_text_reports_placeholder(self) -> None:
        assert _preview_text(_event(text="")) == "[empty message]"

    def test_empty_text_with_attachments_reports_count(self) -> None:
        from tank_contracts.connector import Attachment

        event = MessageEvent(
            identity=_sender(),
            text="",
            attachments=(
                Attachment(kind="image", data=b"x", mime_type="image/png"),
                Attachment(kind="image", data=b"y", mime_type="image/png"),
            ),
        )
        out = _preview_text(event)
        assert "2 attachment" in out


class TestAdminExternalIdsProperty:
    def test_exposes_immutable_view(self, broker_fixture) -> None:
        broker, _, _, _, _ = broker_fixture
        ids = broker.admin_external_ids
        assert ids == frozenset({"tg:user:42"})
        assert isinstance(ids, frozenset)
