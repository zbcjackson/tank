"""Tests for the Feishu / Lark connector plugin.

Structured the same way the Slack and Discord plugin suites are: factory
validation up top, then capabilities, then per-feature classes
(identity construction, inbound dispatch, outbound send, approval
flow). Long-connection-specific tests (the lark.ws.Client thread
hop, _disconnect on stop) get their own ``TestLifecycle`` group.

The lark SDK's WebSocket client + API client are mocked at the
construction seam — we never open a real connection or hit Feishu's
servers, but we exercise the connector's translation logic against
realistic event/payload shapes.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from tank_contracts.connector import Attachment, Identity, MessageEvent

from connector_feishu import FeishuConnector, create_connector


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestCreateConnector:
    def test_factory_happy_path(self) -> None:
        """Factory accepts an instance + config and produces a
        :class:`FeishuConnector` with the supplied app credentials."""
        c = create_connector({
            "instance": "my-bot",
            "config": {"app_id": "cli_a", "app_secret": "s"},
        })
        assert isinstance(c, FeishuConnector)
        assert c.instance_name == "my-bot"
        assert c._app_id == "cli_a"  # noqa: SLF001
        assert c._app_secret == "s"  # noqa: SLF001

    def test_factory_uses_platform_default_instance_name(self) -> None:
        """Empty instance falls back to the platform name — same shape
        validate_spec returns when ``instance`` is missing or empty."""
        c = create_connector({
            "instance": "",
            "config": {"app_id": "cli_a", "app_secret": "s"},
        })
        assert c.instance_name == "feishu"

    def test_factory_rejects_missing_app_id(self) -> None:
        with pytest.raises(ValueError, match="FEISHU_APP_ID"):
            create_connector({
                "instance": "x",
                "config": {"app_secret": "s"},
            })

    def test_factory_rejects_missing_app_secret(self) -> None:
        with pytest.raises(ValueError, match="FEISHU_APP_SECRET"):
            create_connector({
                "instance": "x",
                "config": {"app_id": "cli_a"},
            })

    def test_factory_rejects_non_mapping_config(self) -> None:
        with pytest.raises(ValueError, match="connector-feishu"):
            create_connector({"instance": "x", "config": "not-a-mapping"})


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


class TestCapabilities:
    def test_capabilities_match_feishu_reality(self) -> None:
        """Pin the capability flags so an accidental flip in the
        constructor is caught by tests rather than mysterious runtime
        rejections later."""
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        caps = c.capabilities

        # Streaming edits supported — Feishu's send rate ≈ 50/min,
        # default cadence stays under that.
        assert caps.supports_edits is True
        assert caps.edit_min_interval_ms >= 1000
        # Hard cap on text content (Feishu allows up to 30 000 chars).
        assert caps.max_message_length == 30_000
        # v1 surface: text + image both ways.
        assert caps.supports_images_in is True
        assert caps.supports_images_out is True
        # Voice-in via lark's ``audio`` msg_type. Voice-out deferred
        # (needs file_key upload).
        assert caps.supports_voice_in is True
        assert caps.supports_voice_out is True
        # Feishu has no public typing-indicator API.
        assert caps.supports_typing_indicator is False

    def test_platform_is_feishu(self) -> None:
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        assert c.platform == "feishu"


# ---------------------------------------------------------------------------
# Identity / inbound translation
# ---------------------------------------------------------------------------


def _mock_message_event(
    *,
    chat_type: str = "p2p",
    chat_id: str = "oc_chat_1",
    sender_open_id: str = "ou_sender_1",
    sender_type: str = "user",
    message_type: str = "text",
    content: dict | None = None,
    message_id: str = "om_msg_1",
    tenant_key: str = "t_1",
):
    """Build a MagicMock shaped like ``P2ImMessageReceiveV1``.

    Mirrors the real lark event shape closely enough that the
    connector's ``_dispatch_message`` reads out the same fields it
    would in production. The structure is:

        data.event.message.{message_id, chat_id, chat_type, message_type, content}
        data.event.sender.sender_id.open_id
        data.event.sender.sender_type
    """
    event = MagicMock()
    event.message = MagicMock()
    event.message.message_id = message_id
    event.message.chat_id = chat_id
    event.message.chat_type = chat_type
    event.message.message_type = message_type
    event.message.content = json.dumps(content or {"text": "hello"})

    event.sender = MagicMock()
    event.sender.sender_type = sender_type
    event.sender.tenant_key = tenant_key
    event.sender.sender_id = MagicMock()
    event.sender.sender_id.open_id = sender_open_id

    data = MagicMock()
    data.event = event
    return data


class TestInboundIdentity:
    """Identity construction maps Feishu's chat_type into Tank's
    ``feishu:user:`` (DM) or ``feishu:chat:`` (group) prefixes — the
    same shape SessionMapper expects for all four connectors."""

    async def test_dm_emits_user_prefix(self) -> None:
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)
        c.set_message_handler(handler)

        data = _mock_message_event(
            chat_type="p2p",
            chat_id="oc_dm",
            sender_open_id="ou_alice",
            content={"text": "hi"},
        )
        await c._dispatch_message(data)  # noqa: SLF001
        # Text messages are buffered for bundling; flush manually
        await c._flush_pending_text("feishu:user:ou_alice")  # noqa: SLF001

        assert len(received) == 1
        identity = received[0].identity
        assert identity.platform == "feishu"
        assert identity.external_id == "feishu:user:ou_alice"
        assert identity.is_group is False
        # Metadata carries the raw IDs so outbound can address back.
        assert identity.metadata["open_id"] == "ou_alice"
        assert identity.metadata["chat_id"] == "oc_dm"
        assert identity.metadata["chat_type"] == "p2p"

    async def test_group_emits_chat_prefix(self) -> None:
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        received: list[MessageEvent] = []
        c.set_message_handler(
            lambda e: received.append(e) or _aio_noop(),
        )

        data = _mock_message_event(
            chat_type="group",
            chat_id="oc_grp",
            sender_open_id="ou_bob",
            content={"text": "hi all"},
        )
        await c._dispatch_message(data)  # noqa: SLF001
        # Text messages are buffered for bundling; flush manually
        await c._flush_pending_text("feishu:chat:oc_grp")  # noqa: SLF001

        identity = received[0].identity
        assert identity.external_id == "feishu:chat:oc_grp"
        assert identity.is_group is True


async def _aio_noop() -> None:
    """Tiny awaitable so handler lambdas can short-circuit."""
    return None


# ---------------------------------------------------------------------------
# Inbound filtering
# ---------------------------------------------------------------------------


class TestInboundFiltering:
    """Skip messages we shouldn't react to: bot-authored (loop guard),
    missing sender (system events), unsupported msg_type."""

    async def test_bot_messages_dropped(self) -> None:
        """Anything with ``sender_type != 'user'`` is dropped to avoid
        loops with our own replies — same conservative default as the
        Discord and Slack connectors."""
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        received: list[MessageEvent] = []
        c.set_message_handler(
            lambda e: received.append(e) or _aio_noop(),
        )
        data = _mock_message_event(sender_type="app")
        await c._dispatch_message(data)  # noqa: SLF001
        assert received == []

    async def test_missing_sender_dropped(self) -> None:
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        c.set_message_handler(lambda e: _aio_noop())
        data = _mock_message_event()
        data.event.sender = None
        # Must not raise.
        await c._dispatch_message(data)  # noqa: SLF001

    async def test_unsupported_msg_type_dropped(self) -> None:
        """Sticker / file / system messages outside text/image/audio
        get dropped silently — Tank can't represent them."""
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        received: list[MessageEvent] = []
        c.set_message_handler(
            lambda e: received.append(e) or _aio_noop(),
        )
        data = _mock_message_event(message_type="sticker")
        await c._dispatch_message(data)  # noqa: SLF001
        assert received == []

    async def test_malformed_content_dropped_gracefully(self) -> None:
        """Non-JSON ``content`` (shouldn't happen in practice, but a
        misbehaving SDK release could send it) doesn't crash —
        defensive parse with ``json.loads`` fails fast and skips the
        message."""
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        received: list[MessageEvent] = []
        c.set_message_handler(
            lambda e: received.append(e) or _aio_noop(),
        )
        data = _mock_message_event()
        data.event.message.content = "not-json"
        await c._dispatch_message(data)  # noqa: SLF001
        assert received == []


# ---------------------------------------------------------------------------
# Inbound text + attachments
# ---------------------------------------------------------------------------


class TestInboundText:
    async def test_text_message_reaches_handler(self) -> None:
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)
        c.set_message_handler(handler)

        data = _mock_message_event(content={"text": "hello tank"})
        await c._dispatch_message(data)  # noqa: SLF001
        # Text messages are buffered for bundling; flush manually
        await c._flush_pending_text("feishu:user:ou_sender_1")  # noqa: SLF001

        assert len(received) == 1
        assert received[0].text == "hello tank"
        assert received[0].attachments == ()


class TestInboundImage:
    async def test_image_attachment_resolved_via_resource_api(self) -> None:
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)
        c.set_message_handler(handler)

        # Mock the resource fetch path. Real resp objects have
        # ``success()``, ``code``, ``msg``, and ``file`` (BinaryIO).
        c._download_resource = AsyncMock(return_value=b"\x89PNG_fake")  # noqa: SLF001

        data = _mock_message_event(
            message_type="image",
            content={"image_key": "img_abc"},
        )
        await c._dispatch_message(data)  # noqa: SLF001

        assert len(received) == 1
        atts = received[0].attachments
        assert len(atts) == 1
        assert atts[0].kind == "image"
        assert atts[0].data == b"\x89PNG_fake"

    async def test_image_failure_skips_attachment_silently(self) -> None:
        """When the resource fetch fails, the inbound message still
        forwards (with no attachment) rather than dropping the user's
        turn entirely."""
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)
        c.set_message_handler(handler)

        c._download_resource = AsyncMock(return_value=None)  # noqa: SLF001

        data = _mock_message_event(
            message_type="image",
            content={"image_key": "img_abc"},
        )
        await c._dispatch_message(data)  # noqa: SLF001

        # Image dropped → no attachment, but message still forwards
        # so any associated text (none here) reaches Brain.
        assert len(received) == 1
        assert received[0].attachments == ()


class TestInboundAudio:
    async def test_audio_attachment_marked_as_audio_kind(self) -> None:
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)
        c.set_message_handler(handler)

        c._download_resource = AsyncMock(return_value=b"OggS_fake")  # noqa: SLF001

        data = _mock_message_event(
            message_type="audio",
            content={"file_key": "file_abc"},
        )
        await c._dispatch_message(data)  # noqa: SLF001

        assert len(received) == 1
        atts = received[0].attachments
        assert len(atts) == 1
        assert atts[0].kind == "audio"
        assert atts[0].mime_type == "audio/ogg"


# ---------------------------------------------------------------------------
# Outbound — send / edit
# ---------------------------------------------------------------------------


def _make_started_connector() -> FeishuConnector:
    """Build a FeishuConnector with the API client mocked, bypassing
    the real lifecycle. Tests that exercise outbound paths use this
    rather than awaiting ``start()`` (which would open a real WS)."""
    c = FeishuConnector(
        instance_name="t", app_id="cli_a", app_secret="s",
    )
    api = MagicMock()
    api.im = MagicMock()
    api.im.v1 = MagicMock()
    api.im.v1.message = MagicMock()
    c._api = api  # noqa: SLF001
    c._connected = True  # noqa: SLF001
    return c


class TestSendText:
    async def test_send_text_happy_path(self) -> None:
        c = _make_started_connector()
        # Mock acreate to return a successful response with a
        # message_id. Real responses are typed but the connector only
        # touches success(), code, msg, data.message_id.
        resp = MagicMock()
        resp.success = MagicMock(return_value=True)
        resp.data = MagicMock()
        resp.data.message_id = "om_sent_1"
        c._api.im.v1.message.acreate = AsyncMock(return_value=resp)  # noqa: SLF001

        identity = Identity(
            platform="feishu",
            external_id="feishu:user:ou_alice",
            metadata={"open_id": "ou_alice"},
        )
        result = await c.send(identity=identity, text="hello")

        assert result.ok is True
        assert result.message_id == "om_sent_1"

        # The send call's request body carries the right
        # receive_id_type and the JSON-encoded text content.
        call = c._api.im.v1.message.acreate.call_args  # noqa: SLF001
        req = call.args[0]
        # The lark builder produces a request whose internals we
        # inspect via the type's attributes — easier to grep for the
        # payload than to walk private fields.
        payload = json.loads(req.request_body.content)
        assert payload == {"text": "hello"}

    async def test_send_text_truncates_at_max_length(self) -> None:
        c = _make_started_connector()
        resp = MagicMock()
        resp.success = MagicMock(return_value=True)
        resp.data = MagicMock()
        resp.data.message_id = "x"
        c._api.im.v1.message.acreate = AsyncMock(return_value=resp)  # noqa: SLF001

        long_text = "x" * 50_000
        identity = Identity(
            platform="feishu", external_id="feishu:user:ou_alice",
            metadata={"open_id": "ou_alice"},
        )
        await c.send(identity=identity, text=long_text)

        req = c._api.im.v1.message.acreate.call_args.args[0]  # noqa: SLF001
        payload = json.loads(req.request_body.content)
        # 30 000-char cap with single-character ellipsis tail.
        assert len(payload["text"]) == 30_000
        assert payload["text"].endswith("…")

    async def test_send_text_routes_group_to_chat_id(self) -> None:
        """Group identities use ``chat_id`` as receive_id_type, not
        ``open_id`` — Feishu rejects open_id targets that aren't users."""
        c = _make_started_connector()
        resp = MagicMock()
        resp.success = MagicMock(return_value=True)
        resp.data = MagicMock()
        resp.data.message_id = "x"
        c._api.im.v1.message.acreate = AsyncMock(return_value=resp)  # noqa: SLF001

        identity = Identity(
            platform="feishu",
            external_id="feishu:chat:oc_grp",
            is_group=True,
            metadata={"chat_id": "oc_grp"},
        )
        await c.send(identity=identity, text="hi all")

        req = c._api.im.v1.message.acreate.call_args.args[0]  # noqa: SLF001
        # receive_id_type sits on the request-level builder.
        # The lark builder stores it on a field; assert via repr.
        assert "chat_id" in repr(req.receive_id_type)

    async def test_send_text_classifies_api_error(self) -> None:
        """A non-success response surfaces as ``feishu:<code>:<msg>``
        so logs/StreamConsumer can tell terminal from transient."""
        c = _make_started_connector()
        resp = MagicMock()
        resp.success = MagicMock(return_value=False)
        resp.code = 99991663
        resp.msg = "bot not in chat"
        c._api.im.v1.message.acreate = AsyncMock(return_value=resp)  # noqa: SLF001

        identity = Identity(
            platform="feishu", external_id="feishu:user:ou_a",
            metadata={"open_id": "ou_a"},
        )
        result = await c.send(identity=identity, text="hi")

        assert result.ok is False
        assert "feishu:99991663" in result.error
        assert "bot not in chat" in result.error

    async def test_send_text_classifies_raised_exception(self) -> None:
        c = _make_started_connector()
        c._api.im.v1.message.acreate = AsyncMock(  # noqa: SLF001
            side_effect=RuntimeError("synthetic"),
        )

        identity = Identity(
            platform="feishu", external_id="feishu:user:ou_a",
            metadata={"open_id": "ou_a"},
        )
        result = await c.send(identity=identity, text="hi")

        assert result.ok is False
        assert result.error.startswith("feishu:")

    async def test_send_when_not_connected_returns_error(self) -> None:
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        # ``_api`` is None — never started.
        result = await c.send(
            identity=Identity(
                platform="feishu", external_id="feishu:user:ou_a",
                metadata={},
            ),
            text="hi",
        )
        assert result.ok is False
        assert "not_connected" in result.error


# ---------------------------------------------------------------------------
# Outbound — image upload + send
# ---------------------------------------------------------------------------


class TestImageUpload:
    """Phase 21 wired the ``_upload_image`` path so chart_tool /
    echo_image actually deliver images to Feishu users. Phase 20 v1
    deliberately stubbed it out (returning ``""`` so the caller
    surfaced ``feishu:upload_failed``); these tests pin the new
    happy path + the failure modes the implementation handles.
    """

    async def test_upload_image_returns_image_key_on_success(self) -> None:
        c = _make_started_connector()
        # Mock the lark image.acreate response. The real type has
        # success(), code, msg, data.image_key — match those.
        resp = MagicMock()
        resp.success = MagicMock(return_value=True)
        resp.data = MagicMock()
        resp.data.image_key = "img_v3_abc123"
        c._api.im.v1.image = MagicMock()  # noqa: SLF001
        c._api.im.v1.image.acreate = AsyncMock(return_value=resp)  # noqa: SLF001

        key = await c._upload_image(b"\x89PNG_fake_bytes")  # noqa: SLF001
        assert key == "img_v3_abc123"

        # The acreate call carried image_type="message" + a BytesIO.
        req = c._api.im.v1.image.acreate.call_args.args[0]  # noqa: SLF001
        assert req.request_body.image_type == "message"
        # Verify the BytesIO carries our payload — read all bytes.
        req.request_body.image.seek(0)
        assert req.request_body.image.read() == b"\x89PNG_fake_bytes"

    async def test_upload_image_empty_bytes_returns_empty(self) -> None:
        """Defensive: passing empty bytes (a bug upstream) must
        short-circuit before hitting the lark API. Returns empty
        string so the caller surfaces ``feishu:upload_failed``."""
        c = _make_started_connector()
        c._api.im.v1.image = MagicMock()  # noqa: SLF001
        c._api.im.v1.image.acreate = AsyncMock()  # noqa: SLF001

        key = await c._upload_image(b"")  # noqa: SLF001
        assert key == ""
        # acreate not even called.
        c._api.im.v1.image.acreate.assert_not_awaited()  # noqa: SLF001

    async def test_upload_image_no_api_returns_empty(self) -> None:
        """Edge: ``_upload_image`` called before ``start()`` has
        wired the lark client. Must not crash on ``None.im``."""
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        # ``_api`` is None — never started.
        key = await c._upload_image(b"\x89PNG")  # noqa: SLF001
        assert key == ""

    async def test_upload_image_classifies_lark_error(self) -> None:
        """Non-success response surfaces as empty string so the
        caller's ``feishu:upload_failed`` reaches the user. The
        error code/msg flow into the warn log so operators can
        diagnose."""
        c = _make_started_connector()
        resp = MagicMock()
        resp.success = MagicMock(return_value=False)
        resp.code = 230002
        resp.msg = "image too large"
        c._api.im.v1.image = MagicMock()  # noqa: SLF001
        c._api.im.v1.image.acreate = AsyncMock(return_value=resp)  # noqa: SLF001

        key = await c._upload_image(b"x" * 1024)  # noqa: SLF001
        assert key == ""

    async def test_upload_image_handles_raised_exception(self) -> None:
        """Exceptions on the upload path get caught + logged; the
        empty-string return lets the caller surface a clean error
        rather than a 500."""
        c = _make_started_connector()
        c._api.im.v1.image = MagicMock()  # noqa: SLF001
        c._api.im.v1.image.acreate = AsyncMock(  # noqa: SLF001
            side_effect=RuntimeError("network down"),
        )

        key = await c._upload_image(b"\x89PNG")  # noqa: SLF001
        assert key == ""

    async def test_upload_image_missing_image_key_in_response(self) -> None:
        """Defensive: a success response with no image_key (shouldn't
        happen but lark's response shape allows it) returns empty
        string rather than ``None`` (which would crash the caller's
        f-string)."""
        c = _make_started_connector()
        resp = MagicMock()
        resp.success = MagicMock(return_value=True)
        resp.data = MagicMock()
        resp.data.image_key = None
        c._api.im.v1.image = MagicMock()  # noqa: SLF001
        c._api.im.v1.image.acreate = AsyncMock(return_value=resp)  # noqa: SLF001

        key = await c._upload_image(b"\x89PNG")  # noqa: SLF001
        assert key == ""


class TestSendImageEndToEnd:
    """End-to-end: ``send`` with an image attachment now reaches the
    Feishu chat. Pre-Phase-21 these tests would have asserted
    ``feishu:upload_failed`` because ``_upload_image`` was a stub;
    post-Phase-21 they exercise the full send flow."""

    async def test_send_image_uploads_and_messages(self) -> None:
        c = _make_started_connector()
        # Successful upload returns an image_key.
        upload_resp = MagicMock()
        upload_resp.success = MagicMock(return_value=True)
        upload_resp.data = MagicMock()
        upload_resp.data.image_key = "img_v3_xyz"
        c._api.im.v1.image = MagicMock()  # noqa: SLF001
        c._api.im.v1.image.acreate = AsyncMock(return_value=upload_resp)  # noqa: SLF001

        # Successful message send (image msg_type) returns msg id.
        send_resp = MagicMock()
        send_resp.success = MagicMock(return_value=True)
        send_resp.data = MagicMock()
        send_resp.data.message_id = "om_image_msg"
        c._api.im.v1.message.acreate = AsyncMock(return_value=send_resp)  # noqa: SLF001

        identity = Identity(
            platform="feishu", external_id="feishu:user:ou_a",
            metadata={"open_id": "ou_a"},
        )
        attachment = Attachment(
            kind="image", data=b"\x89PNG_fake", mime_type="image/png",
        )

        result = await c.send(
            identity=identity, text="", attachments=(attachment,),
        )

        assert result.ok is True
        assert result.message_id == "om_image_msg"

        # Image upload happened.
        c._api.im.v1.image.acreate.assert_awaited_once()  # noqa: SLF001
        # Then the message send carried the upload's image_key.
        send_calls = c._api.im.v1.message.acreate.call_args_list  # noqa: SLF001
        # Last call is the image message; with no caption text, only
        # one call total.
        last_req = send_calls[-1].args[0]
        last_payload = json.loads(last_req.request_body.content)
        assert last_payload == {"image_key": "img_v3_xyz"}

    async def test_send_image_with_caption_sends_text_then_image(
        self,
    ) -> None:
        """When the image attachment carries caption text, send the
        text first, then the image. Feishu doesn't support inline
        captions on image messages, so we split them. Order matches
        Phase 15's caption-on-first-attachment expectation: text
        renders adjacent to the image."""
        c = _make_started_connector()

        upload_resp = MagicMock()
        upload_resp.success = MagicMock(return_value=True)
        upload_resp.data = MagicMock()
        upload_resp.data.image_key = "img_v3_xyz"
        c._api.im.v1.image = MagicMock()  # noqa: SLF001
        c._api.im.v1.image.acreate = AsyncMock(return_value=upload_resp)  # noqa: SLF001

        text_resp = MagicMock()
        text_resp.success = MagicMock(return_value=True)
        text_resp.data = MagicMock()
        text_resp.data.message_id = "om_text"
        image_resp = MagicMock()
        image_resp.success = MagicMock(return_value=True)
        image_resp.data = MagicMock()
        image_resp.data.message_id = "om_image"

        # Two consecutive acreate calls — text, then image.
        c._api.im.v1.message.acreate = AsyncMock(  # noqa: SLF001
            side_effect=[text_resp, image_resp],
        )

        identity = Identity(
            platform="feishu", external_id="feishu:user:ou_a",
            metadata={"open_id": "ou_a"},
        )
        attachment = Attachment(
            kind="image", data=b"\x89PNG", mime_type="image/png",
        )

        result = await c.send(
            identity=identity,
            text="here you go:",
            attachments=(attachment,),
        )
        assert result.ok is True
        # Final result carries the image's message_id.
        assert result.message_id == "om_image"

        # Two message sends in order: text, then image.
        send_calls = c._api.im.v1.message.acreate.call_args_list  # noqa: SLF001
        assert len(send_calls) == 2
        text_payload = json.loads(send_calls[0].args[0].request_body.content)
        image_payload = json.loads(send_calls[1].args[0].request_body.content)
        assert text_payload == {"text": "here you go:"}
        assert image_payload == {"image_key": "img_v3_xyz"}

    async def test_send_image_upload_failure_returns_clear_error(
        self,
    ) -> None:
        """When ``_upload_image`` returns empty (failure), the caller
        surfaces ``feishu:upload_failed`` so the user sees a clean
        error rather than a successful send with a missing image."""
        c = _make_started_connector()
        upload_resp = MagicMock()
        upload_resp.success = MagicMock(return_value=False)
        upload_resp.code = 230002
        upload_resp.msg = "image too large"
        c._api.im.v1.image = MagicMock()  # noqa: SLF001
        c._api.im.v1.image.acreate = AsyncMock(return_value=upload_resp)  # noqa: SLF001

        identity = Identity(
            platform="feishu", external_id="feishu:user:ou_a",
            metadata={"open_id": "ou_a"},
        )
        attachment = Attachment(
            kind="image", data=b"x" * 1024, mime_type="image/png",
        )
        result = await c.send(
            identity=identity, text="", attachments=(attachment,),
        )
        assert result.ok is False
        assert "feishu:upload_failed" in result.error


class TestUrlImageDownload:
    """Item 1: URL-based outbound images. When echo_image or chart_tool
    returns a public http(s):// URL, the connector downloads the bytes
    then uploads via _upload_image."""

    async def test_url_image_downloads_and_uploads(self) -> None:
        """Happy path: URL string in att.data triggers download, then
        the downloaded bytes go through _upload_image → send."""
        c = _make_started_connector()

        # Mock the download path
        c._download_url_image = AsyncMock(return_value=b"\x89PNG_from_url")  # noqa: SLF001

        # Mock upload + send
        upload_resp = MagicMock()
        upload_resp.success = MagicMock(return_value=True)
        upload_resp.data = MagicMock()
        upload_resp.data.image_key = "img_url_xyz"
        c._api.im.v1.image = MagicMock()  # noqa: SLF001
        c._api.im.v1.image.acreate = AsyncMock(return_value=upload_resp)  # noqa: SLF001

        send_resp = MagicMock()
        send_resp.success = MagicMock(return_value=True)
        send_resp.data = MagicMock()
        send_resp.data.message_id = "om_url_img"
        c._api.im.v1.message.acreate = AsyncMock(return_value=send_resp)  # noqa: SLF001

        identity = Identity(
            platform="feishu", external_id="feishu:user:ou_a",
            metadata={"open_id": "ou_a"},
        )
        # URL string as data — the path echo_image produces
        attachment = Attachment(
            kind="image", data="https://example.com/cat.jpg",
            mime_type="image/jpeg",
        )

        result = await c.send(
            identity=identity, text="", attachments=(attachment,),
        )

        assert result.ok is True
        # Download was called with the URL
        c._download_url_image.assert_awaited_once_with(  # noqa: SLF001
            "https://example.com/cat.jpg",
        )

    async def test_url_download_failure_returns_error(self) -> None:
        """When the URL download fails (network error, 404, etc.),
        surface a clean error rather than crashing."""
        c = _make_started_connector()
        c._download_url_image = AsyncMock(return_value=None)  # noqa: SLF001

        identity = Identity(
            platform="feishu", external_id="feishu:user:ou_a",
            metadata={"open_id": "ou_a"},
        )
        attachment = Attachment(
            kind="image", data="https://example.com/broken.jpg",
            mime_type="image/jpeg",
        )

        result = await c.send(
            identity=identity, text="", attachments=(attachment,),
        )

        assert result.ok is False
        assert "url_image_download_failed" in result.error

    async def test_non_url_string_returns_error(self) -> None:
        """A string that isn't http(s):// (e.g. a file path or
        media:// URI) returns a clear error rather than attempting
        a download."""
        c = _make_started_connector()

        identity = Identity(
            platform="feishu", external_id="feishu:user:ou_a",
            metadata={"open_id": "ou_a"},
        )
        attachment = Attachment(
            kind="image", data="media://s1/x.png",
            mime_type="image/png",
        )

        result = await c.send(
            identity=identity, text="", attachments=(attachment,),
        )

        assert result.ok is False
        assert "unsupported_image_source" in result.error


class TestEdit:
    async def test_edit_happy_path(self) -> None:
        c = _make_started_connector()
        resp = MagicMock()
        resp.success = MagicMock(return_value=True)
        # Phase 21 follow-up: edit() now uses ``aupdate`` (text-message
        # capable), not ``apatch`` (card-only). The previous code
        # path 400'd on every streaming text edit with "This message
        # is NOT a card" until we switched.
        c._api.im.v1.message.aupdate = AsyncMock(return_value=resp)  # noqa: SLF001

        result = await c.edit(
            identity=Identity(
                platform="feishu", external_id="feishu:user:ou_a",
                metadata={},
            ),
            message_id="om_x",
            text="updated",
        )
        assert result.ok is True
        assert result.message_id == "om_x"

        # Edit body carries the same JSON-text shape send uses, plus
        # the explicit ``msg_type=text`` the aupdate API requires.
        req = c._api.im.v1.message.aupdate.call_args.args[0]  # noqa: SLF001
        payload = json.loads(req.request_body.content)
        assert payload == {"text": "updated"}
        assert req.request_body.msg_type == "text"

    async def test_edit_classifies_api_error(self) -> None:
        c = _make_started_connector()
        resp = MagicMock()
        resp.success = MagicMock(return_value=False)
        resp.code = 230015
        resp.msg = "edit window expired"
        c._api.im.v1.message.aupdate = AsyncMock(return_value=resp)  # noqa: SLF001

        result = await c.edit(
            identity=Identity(
                platform="feishu", external_id="feishu:user:ou_a",
                metadata={},
            ),
            message_id="om_x",
            text="updated",
        )
        assert result.ok is False
        assert "feishu:230015" in result.error

    async def test_edit_when_not_connected_returns_error(self) -> None:
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        result = await c.edit(
            identity=Identity(
                platform="feishu", external_id="feishu:user:ou_a",
                metadata={},
            ),
            message_id="om_x",
            text="x",
        )
        assert result.ok is False
        assert "not_connected" in result.error

    async def test_edit_without_message_id_returns_error(self) -> None:
        c = _make_started_connector()
        result = await c.edit(
            identity=Identity(
                platform="feishu", external_id="feishu:user:ou_a",
                metadata={},
            ),
            message_id="",
            text="x",
        )
        assert result.ok is False
        assert "no_message_id" in result.error


# ---------------------------------------------------------------------------
# Approval prompts (Phase 10) + card actions
# ---------------------------------------------------------------------------


class TestApprovalPrompt:
    """``send_approval_prompt`` renders a 3-button interactive card
    whose button ``value.action`` field carries the standard
    ``approve:<choice>:<approval_id>`` payload. Clicks come back to
    ``_on_card_action`` which delegates to ``_dispatch_card_action``."""

    async def test_renders_card_with_three_buttons(self) -> None:
        c = _make_started_connector()
        c._api.im.v1.message.acreate = AsyncMock(  # noqa: SLF001
            return_value=MagicMock(success=MagicMock(return_value=True)),
        )

        admin = Identity(
            platform="feishu", external_id="feishu:user:ou_admin",
            metadata={"open_id": "ou_admin"},
        )
        sender = Identity(
            platform="feishu", external_id="feishu:user:ou_alice",
            display_name="Alice",
            metadata={"open_id": "ou_alice"},
        )

        await c.send_approval_prompt(
            admin_identity=admin,
            approval_id="abc1234567890def",
            sender=sender,
            preview="hello tank",
        )

        c._api.im.v1.message.acreate.assert_awaited_once()  # noqa: SLF001
        req = c._api.im.v1.message.acreate.call_args.args[0]  # noqa: SLF001
        card = json.loads(req.request_body.content)

        # Find the action element + its three buttons.
        action_elem = next(
            e for e in card["elements"] if e.get("tag") == "action"
        )
        buttons = action_elem["actions"]
        assert len(buttons) == 3

        # Each button carries the expected ``approve:<choice>:<id>``
        # action payload — same shape every other connector uses, so
        # the SDK codec round-trips cleanly.
        actions = sorted(b["value"]["action"] for b in buttons)
        assert actions == [
            "approve:allow_forever:abc1234567890def",
            "approve:allow_once:abc1234567890def",
            "approve:deny:abc1234567890def",
        ]

        # The card text uses the SDK helper's standard prompt body
        # (Alice's external_id appears in the rendered text).
        body_div = next(
            e for e in card["elements"] if e.get("tag") == "div"
        )
        assert "Alice" in body_div["text"]["content"]
        assert "feishu:user:ou_alice" in body_div["text"]["content"]
        assert "hello tank" in body_div["text"]["content"]

    async def test_unparseable_admin_identity_is_silent_noop(self) -> None:
        c = _make_started_connector()
        c._api.im.v1.message.acreate = AsyncMock()  # noqa: SLF001

        # external_id with no open_id and no metadata fallback.
        bad_admin = Identity(
            platform="feishu", external_id="totally-malformed",
            metadata={},
        )
        await c.send_approval_prompt(
            admin_identity=bad_admin,
            approval_id="abc",
            sender=Identity(
                platform="feishu", external_id="feishu:user:ou_x",
                metadata={},
            ),
            preview="x",
        )
        # No send attempted — just a warning log.
        c._api.im.v1.message.acreate.assert_not_awaited()  # noqa: SLF001


class TestCardAction:
    @staticmethod
    def _mock_card_event(
        *,
        action_value: str = "approve:allow_forever:abc",
        operator_open_id: str = "ou_admin",
        message_id: str = "om_card",
    ):
        data = MagicMock()
        data.action = MagicMock()
        data.action.value = {"action": action_value}
        data.operator = MagicMock()
        data.operator.open_id = operator_open_id
        data.open_message_id = message_id
        return data

    @staticmethod
    def _make_pending(sender_open_id: str = "ou_alice") -> MagicMock:
        pending = MagicMock()
        pending.event.identity = Identity(
            platform="feishu",
            external_id=f"feishu:user:{sender_open_id}",
            display_name="Alice",
            metadata={"open_id": sender_open_id},
        )
        return pending

    async def test_card_action_dispatches_to_broker(self) -> None:
        c = _make_started_connector()
        broker = MagicMock()
        broker.resolve = AsyncMock(return_value=self._make_pending())
        c.set_approval_broker(broker)
        # Patch isn't needed for the *dispatch* path because
        # ``_on_card_action`` only hops the loop — the dispatch
        # itself runs ``_dispatch_card_action`` which is what we
        # exercise directly.
        c._api.im.v1.message.apatch = AsyncMock(  # noqa: SLF001
            return_value=MagicMock(success=MagicMock(return_value=True)),
        )

        data = self._mock_card_event(
            action_value="approve:allow_forever:abc1234567890def",
        )
        await c._dispatch_card_action(data)  # noqa: SLF001

        broker.resolve.assert_awaited_once()
        args = broker.resolve.call_args.args
        assert args[0] == "abc1234567890def"
        assert args[1] == "allow_forever"
        clicker = args[2]
        assert clicker.platform == "feishu"
        assert clicker.external_id == "feishu:user:ou_admin"

    async def test_card_action_edits_card_to_outcome_on_success(
        self,
    ) -> None:
        """After ``broker.resolve`` returns a non-None pending, the
        card gets patched to a single text element showing the
        outcome — same UX contract as the other connectors."""
        c = _make_started_connector()
        broker = MagicMock()
        broker.resolve = AsyncMock(return_value=self._make_pending())
        c.set_approval_broker(broker)

        c._api.im.v1.message.apatch = AsyncMock(  # noqa: SLF001
            return_value=MagicMock(success=MagicMock(return_value=True)),
        )

        data = self._mock_card_event(
            action_value="approve:allow_forever:abc",
        )
        await c._dispatch_card_action(data)  # noqa: SLF001

        c._api.im.v1.message.apatch.assert_awaited_once()  # noqa: SLF001
        req = c._api.im.v1.message.apatch.call_args.args[0]  # noqa: SLF001
        new_card = json.loads(req.request_body.content)
        # Only one element after the edit — the outcome line.
        assert len(new_card["elements"]) == 1
        outcome_text = new_card["elements"][0]["text"]["content"]
        assert "Approved forever" in outcome_text
        assert "Alice" in outcome_text

    async def test_stale_resolve_does_not_edit_card(self) -> None:
        """``broker.resolve`` returns ``None`` for stale or non-admin
        clicks. The connector must leave the card alone in that case."""
        c = _make_started_connector()
        broker = MagicMock()
        broker.resolve = AsyncMock(return_value=None)
        c.set_approval_broker(broker)

        c._api.im.v1.message.apatch = AsyncMock()  # noqa: SLF001

        data = self._mock_card_event(action_value="approve:deny:abc")
        await c._dispatch_card_action(data)  # noqa: SLF001

        c._api.im.v1.message.apatch.assert_not_awaited()  # noqa: SLF001

    async def test_malformed_action_payload_is_noop(self) -> None:
        c = _make_started_connector()
        broker = MagicMock()
        broker.resolve = AsyncMock()
        c.set_approval_broker(broker)

        data = self._mock_card_event(action_value="not-an-approval-action")
        await c._dispatch_card_action(data)  # noqa: SLF001
        broker.resolve.assert_not_awaited()

    async def test_no_broker_attached_silently_returns(self) -> None:
        """Card click before the broker is attached is dropped silently
        — same path other connectors take during a restart window."""
        c = _make_started_connector()
        if hasattr(c, "_broker"):
            delattr(c, "_broker")
        data = self._mock_card_event()
        # Must not raise.
        await c._dispatch_card_action(data)  # noqa: SLF001


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    """The lark.ws.Client calls block on a private event loop, so the
    real start() runs the client on a worker thread via
    ``asyncio.to_thread``. Tests mock at the construction seam — the
    SDK builders are patched so no real WS opens."""

    async def test_start_creates_clients_and_spawns_runner(self) -> None:
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )

        with patch(
            "connector_feishu.connector.lark.Client",
        ) as client_cls, patch(
            "connector_feishu.connector.lark.ws.Client",
        ) as ws_cls, patch(
            "connector_feishu.connector.lark.EventDispatcherHandler",
        ) as ev_cls, patch(
            "asyncio.to_thread",
            new=AsyncMock(return_value=None),
        ):
            ws = MagicMock()
            ws_cls.return_value = ws
            api = MagicMock()
            client_cls.builder.return_value.app_id.return_value.app_secret.return_value.log_level.return_value.build.return_value = api
            ev_cls.builder.return_value.register_p2_im_message_receive_v1.return_value.register_p2_card_action_trigger.return_value.build.return_value = MagicMock()

            await c.start()
            try:
                assert c.connected
                assert c._api is api  # noqa: SLF001
                assert c._ws is ws  # noqa: SLF001
            finally:
                # Avoid the real ``stop`` (which would try to schedule
                # _disconnect on a private lark loop) — flip the flags
                # manually since this is an isolated unit test.
                c._connected = False  # noqa: SLF001
                c._api = None  # noqa: SLF001
                c._ws = None  # noqa: SLF001

    async def test_double_start_is_no_op(self) -> None:
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        c._connected = True  # noqa: SLF001 — pretend we already started
        with patch(
            "connector_feishu.connector.lark.Client",
        ) as client_cls:
            await c.start()
            client_cls.builder.assert_not_called()

    async def test_stop_before_start_is_no_op(self) -> None:
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        # Must not raise.
        await c.stop()
        assert not c.connected


# ---------------------------------------------------------------------------
# lark module-global event-loop monkey-patch
# ---------------------------------------------------------------------------


class TestLarkLoopMonkeyPatch:
    """Phase 20 follow-up: ``lark.ws.Client.start`` calls
    ``run_until_complete`` on a module-global ``loop`` that lark
    captures at import time via ``asyncio.get_event_loop()``. When
    Tank's main loop is that captured value, the SDK raises
    ``RuntimeError: this event loop is already running``.

    The fix in ``_run_ws`` spawns a real OS thread, creates a fresh
    loop inside it, and monkey-patches ``lark_oapi.ws.client.loop``
    to that thread-local loop *before* calling ``ws.start()``. These
    tests pin three invariants so a future refactor (e.g. someone
    swapping back to ``asyncio.to_thread``) gets caught at unit-test
    speed instead of only via live verification:

    1. The module-global loop is swapped to a *different* loop
       inside the thread before ``ws.start()`` runs.
    2. The originally-captured loop is restored on thread exit, so
       multiple lark.ws.Client instances elsewhere in the process
       don't trample each other.
    3. ``ws.start()`` actually runs on the thread (the whole point
       of the indirection — keeping Tank's main loop free).
    """

    async def test_module_global_loop_swapped_before_start(self) -> None:
        """The lark thread monkey-patches ``lark_oapi.ws.client.loop``
        to a thread-owned loop *before* invoking ``ws.start()``.
        ``ws.start`` records what ``loop`` it sees so the test can
        assert the swap took effect at the right moment."""
        import lark_oapi.ws.client as lark_ws_module

        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )

        # Make ``ws.start`` capture the module-global loop the moment
        # it runs, then return immediately so the thread joins without
        # blocking the test. The capture lets us prove the swap happened
        # before ``start`` was called.
        captured_loops: list[Any] = []

        def fake_start() -> None:
            captured_loops.append(lark_ws_module.loop)

        ws = MagicMock()
        ws.start = fake_start
        c._ws = ws  # noqa: SLF001

        await c._run_ws()  # noqa: SLF001

        assert len(captured_loops) == 1
        loop_during_start = captured_loops[0]
        # The thread's loop is *not* the main test loop. If the swap
        # didn't happen we'd see Tank's main loop here — which is the
        # bug shape we're guarding against.
        assert loop_during_start is not asyncio.get_running_loop()

    async def test_module_global_loop_restored_on_thread_exit(self) -> None:
        """After the lark thread exits, ``lark_oapi.ws.client.loop``
        is restored to whatever it was before the thread started.
        Without this, a second ``FeishuConnector`` instance (or any
        other lark.ws.Client elsewhere in the process) would inherit
        the *previous* thread's now-closed loop."""
        import lark_oapi.ws.client as lark_ws_module

        original_loop = lark_ws_module.loop

        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        ws = MagicMock()
        ws.start = MagicMock()  # returns immediately
        c._ws = ws  # noqa: SLF001

        await c._run_ws()  # noqa: SLF001

        # After the thread joined, the module-global is restored.
        assert lark_ws_module.loop is original_loop

    async def test_ws_start_runs_on_thread_owned_loop(self) -> None:
        """The thread-owned loop is exposed via ``self._ws_loop`` so
        ``stop()`` can schedule ``_disconnect`` on the right loop.
        Pin that exposure plus the no-loop-mismatch invariant."""
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        ws = MagicMock()
        ws.start = MagicMock()
        c._ws = ws  # noqa: SLF001

        await c._run_ws()  # noqa: SLF001

        # ``_ws_loop`` is populated and is NOT the main loop.
        assert c._ws_loop is not None  # noqa: SLF001
        assert c._ws_loop is not asyncio.get_running_loop()  # noqa: SLF001
        # ``_ws_thread`` is populated too — ``stop()`` reads it to
        # know whether the thread is alive when scheduling
        # ``_disconnect``.
        assert c._ws_thread is not None  # noqa: SLF001

    async def test_start_failure_still_restores_module_global(self) -> None:
        """If ``ws.start`` raises (e.g. the auth token is bad and lark
        rejects the connect), the ``finally`` clause must still
        restore the module-global. Otherwise a process that retries
        from a fresh connector would inherit the failed-thread's
        now-closed loop and double-fault."""
        import lark_oapi.ws.client as lark_ws_module

        original_loop = lark_ws_module.loop

        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        ws = MagicMock()
        ws.start = MagicMock(side_effect=RuntimeError("synthetic auth fail"))
        c._ws = ws  # noqa: SLF001

        # The exception is logged inside the thread; ``_run_ws``
        # itself returns normally because ``thread.join`` doesn't
        # propagate exceptions raised inside the worker.
        await c._run_ws()  # noqa: SLF001

        assert lark_ws_module.loop is original_loop


# ---------------------------------------------------------------------------
# Text+image bundling
# ---------------------------------------------------------------------------


class TestTextImageBundling:
    """Item 2: Feishu delivers text + image as two separate events.
    The connector buffers text for a short window and merges with a
    subsequent image from the same sender."""

    async def test_text_then_image_merged_into_one_event(self) -> None:
        """The headline scenario: user sends text, then image within
        the bundle window. The handler receives ONE MessageEvent with
        both text and the image attachment."""
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)
        c.set_message_handler(handler)

        # Mock the resource download for the image event
        c._download_resource = AsyncMock(return_value=b"\x89PNG_merged")  # noqa: SLF001

        # 1. Text event arrives — gets buffered
        text_data = _mock_message_event(
            chat_type="p2p",
            sender_open_id="ou_alice",
            message_type="text",
            content={"text": "what's in this picture?"},
        )
        await c._dispatch_message(text_data)  # noqa: SLF001
        assert len(received) == 0  # buffered, not forwarded yet

        # 2. Image event from same sender arrives — merges
        image_data = _mock_message_event(
            chat_type="p2p",
            sender_open_id="ou_alice",
            message_type="image",
            content={"image_key": "img_abc"},
        )
        await c._dispatch_message(image_data)  # noqa: SLF001

        # One merged event with text + image
        assert len(received) == 1
        assert received[0].text == "what's in this picture?"
        assert len(received[0].attachments) == 1
        assert received[0].attachments[0].kind == "image"
        assert received[0].attachments[0].data == b"\x89PNG_merged"

    async def test_text_without_image_flushes_after_timer(self) -> None:
        """When no image follows within the window, the text forwards
        as a text-only event after the timer fires."""
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)
        c.set_message_handler(handler)

        text_data = _mock_message_event(
            chat_type="p2p",
            sender_open_id="ou_bob",
            message_type="text",
            content={"text": "just text"},
        )
        await c._dispatch_message(text_data)  # noqa: SLF001
        assert len(received) == 0  # buffered

        # Manually flush (simulates timer expiry)
        await c._flush_pending_text("feishu:user:ou_bob")  # noqa: SLF001

        assert len(received) == 1
        assert received[0].text == "just text"
        assert received[0].attachments == ()

    async def test_two_texts_in_a_row_flushes_first(self) -> None:
        """If the same sender sends two texts without an image between
        them, the first text is flushed immediately when the second
        arrives (the first wasn't followed by an image)."""
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)
        c.set_message_handler(handler)

        # First text
        data1 = _mock_message_event(
            chat_type="p2p",
            sender_open_id="ou_carol",
            message_type="text",
            content={"text": "first"},
        )
        await c._dispatch_message(data1)  # noqa: SLF001
        assert len(received) == 0  # buffered

        # Second text from same sender — flushes the first
        data2 = _mock_message_event(
            chat_type="p2p",
            sender_open_id="ou_carol",
            message_type="text",
            content={"text": "second"},
        )
        await c._dispatch_message(data2)  # noqa: SLF001

        # First text was flushed; second is now buffered
        assert len(received) == 1
        assert received[0].text == "first"

        # Flush the second
        await c._flush_pending_text("feishu:user:ou_carol")  # noqa: SLF001
        assert len(received) == 2
        assert received[1].text == "second"

    async def test_image_without_pending_text_forwards_immediately(
        self,
    ) -> None:
        """An image that arrives without a preceding text event
        forwards immediately as an image-only MessageEvent."""
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)
        c.set_message_handler(handler)

        c._download_resource = AsyncMock(return_value=b"\x89PNG_solo")  # noqa: SLF001

        image_data = _mock_message_event(
            chat_type="p2p",
            sender_open_id="ou_dave",
            message_type="image",
            content={"image_key": "img_solo"},
        )
        await c._dispatch_message(image_data)  # noqa: SLF001

        # Forwarded immediately — no text to merge
        assert len(received) == 1
        assert received[0].text == ""
        assert received[0].attachments[0].data == b"\x89PNG_solo"

    async def test_different_senders_dont_cross_bundle(self) -> None:
        """Text from sender A and image from sender B must NOT merge.
        Each sender's buffer is independent."""
        c = FeishuConnector(
            instance_name="t", app_id="cli_a", app_secret="s",
        )
        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)
        c.set_message_handler(handler)

        c._download_resource = AsyncMock(return_value=b"\x89PNG")  # noqa: SLF001

        # Text from Alice
        text_data = _mock_message_event(
            chat_type="p2p",
            sender_open_id="ou_alice",
            message_type="text",
            content={"text": "alice's text"},
        )
        await c._dispatch_message(text_data)  # noqa: SLF001

        # Image from Bob — should NOT merge with Alice's text
        image_data = _mock_message_event(
            chat_type="p2p",
            sender_open_id="ou_bob",
            message_type="image",
            content={"image_key": "img_bob"},
        )
        await c._dispatch_message(image_data)  # noqa: SLF001

        # Bob's image forwarded immediately (no pending text from Bob)
        assert len(received) == 1
        assert received[0].text == ""  # Bob's image, no text

        # Alice's text still buffered — flush it
        await c._flush_pending_text("feishu:user:ou_alice")  # noqa: SLF001
        assert len(received) == 2
        assert received[1].text == "alice's text"
        assert received[1].attachments == ()
