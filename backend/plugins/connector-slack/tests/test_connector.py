"""Unit tests for :class:`SlackConnector` and ``create_connector``.

All tests use mocks — no real slack_bolt AsyncApp is instantiated, no
HTTP calls fire. Covers factory validation, capabilities, lifecycle,
inbound translation (text + images), inbound subtype filtering,
outbound send / edit (happy paths, rate-limit, bad identity), composite
message-id encoding, and the DM vs channel identity split.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from slack_sdk.errors import SlackApiError
from tank_contracts.connector import Attachment, Identity, MessageEvent

from connector_slack import SlackConnector, create_connector
from connector_slack.connector import _decode_msg_id, _encode_msg_id


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestCreateConnector:
    def test_happy_path(self) -> None:
        c = create_connector({
            "instance": "my-bot",
            "config": {"bot_token": "xoxb-aaa", "app_token": "xapp-bbb"},
        })
        assert isinstance(c, SlackConnector)
        assert c.instance_name == "my-bot"
        assert c.platform == "slack"

    def test_missing_bot_token_raises(self) -> None:
        with pytest.raises(ValueError, match="bot_token"):
            create_connector({
                "instance": "x",
                "config": {"app_token": "xapp-t"},
            })

    def test_missing_app_token_raises(self) -> None:
        with pytest.raises(ValueError, match="app_token"):
            create_connector({
                "instance": "x",
                "config": {"bot_token": "xoxb-t"},
            })

    def test_empty_bot_token_rejected(self) -> None:
        with pytest.raises(ValueError, match="bot_token"):
            create_connector({
                "instance": "x",
                "config": {"bot_token": "   ", "app_token": "xapp-t"},
            })

    def test_empty_app_token_rejected(self) -> None:
        with pytest.raises(ValueError, match="app_token"):
            create_connector({
                "instance": "x",
                "config": {"bot_token": "xoxb-t", "app_token": ""},
            })

    def test_non_dict_config_raises(self) -> None:
        with pytest.raises(ValueError, match="mapping"):
            create_connector({"instance": "x", "config": "not-a-dict"})

    def test_empty_instance_name_falls_back_to_platform(self) -> None:
        c = create_connector({
            "config": {"bot_token": "xoxb-t", "app_token": "xapp-t"},
        })
        assert c.instance_name == "slack"


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


class TestCapabilities:
    def test_capabilities_match_slack_reality(self) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        caps = c.capabilities
        assert caps.supports_edits is True
        # Slack Tier 3 ≈ 50/min → 1400ms is safely under.
        assert caps.edit_min_interval_ms >= 1000
        # Slack's hard cap on chat.postMessage.
        assert caps.max_message_length == 40_000
        # Phase-7 scope: text + image in both directions.
        assert caps.supports_images_in is True
        assert caps.supports_images_out is True
        # Voice deferred.
        assert caps.supports_voice_in is False
        assert caps.supports_voice_out is False
        # Slack has no public typing indicator.
        assert caps.supports_typing_indicator is False


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class _LifecycleMocks:
    """Captures references to AsyncApp + AsyncSocketModeHandler mocks."""

    def __init__(self, app: MagicMock, handler: MagicMock) -> None:
        self.app = app
        self.handler = handler


@pytest.fixture()
def lifecycle_mocks():
    """Patch AsyncApp + AsyncSocketModeHandler so `start()` / `stop()`
    can be exercised without real Slack connectivity."""
    app = MagicMock(name="AsyncApp")
    # Bolt's event decorator returns a decorator; the inner registration
    # is fire-and-forget from our perspective.
    app.event.return_value = lambda fn: fn
    # slack_bolt's AsyncWebClient methods are all awaitable.
    app.client = MagicMock()
    app.client.chat_postMessage = AsyncMock()
    app.client.chat_update = AsyncMock()
    app.client.files_upload_v2 = AsyncMock()
    app.client.users_info = AsyncMock()

    handler = MagicMock(name="AsyncSocketModeHandler")
    # start_async blocks until disconnect; make it a slow coroutine we
    # can cancel so the task doesn't complete before stop() runs.
    async def _slow_start():
        await asyncio.sleep(60)
    handler.start_async = AsyncMock(side_effect=_slow_start)
    handler.close_async = AsyncMock()

    app_cls = MagicMock(return_value=app)
    handler_cls = MagicMock(return_value=handler)

    with (
        patch("connector_slack.connector.AsyncApp", app_cls),
        patch(
            "connector_slack.connector.AsyncSocketModeHandler", handler_cls,
        ),
        patch("connector_slack.connector._SHUTDOWN_TIMEOUT_S", 0.1),
    ):
        yield _LifecycleMocks(app=app, handler=handler)


class TestLifecycle:
    async def test_start_creates_app_handler_and_registers_handler(
        self, lifecycle_mocks,
    ) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        await c.start()
        try:
            assert c.connected
            # Event handler for 'message' was registered exactly once.
            lifecycle_mocks.app.event.assert_called_once_with("message")
            # Polling task was spawned.
            assert c._task is not None  # noqa: SLF001
            assert not c._task.done()  # noqa: SLF001
        finally:
            await c.stop()

    async def test_stop_closes_handler_and_drains_task(
        self, lifecycle_mocks,
    ) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        await c.start()
        await c.stop()
        lifecycle_mocks.handler.close_async.assert_awaited_once()
        assert not c.connected
        assert c._task is None  # noqa: SLF001
        assert c._handler is None  # noqa: SLF001
        assert c._app is None  # noqa: SLF001

    async def test_double_start_is_no_op(self, lifecycle_mocks) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        await c.start()
        try:
            lifecycle_mocks.handler.start_async.reset_mock()
            await c.start()
            # Not re-opened — still connected from the first start.
            lifecycle_mocks.handler.start_async.assert_not_called()
        finally:
            await c.stop()

    async def test_stop_before_start_is_no_op(self, lifecycle_mocks) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        await c.stop()  # must not raise
        lifecycle_mocks.handler.close_async.assert_not_called()

    async def test_cancel_on_slow_shutdown(self, lifecycle_mocks) -> None:
        """When the polling task refuses to drain in time, stop() falls
        back to ``task.cancel()`` so we never hang the ASGI lifespan."""
        # Make close_async hang briefly so the task doesn't drain on its own.
        async def _hang() -> None:
            await asyncio.sleep(10)
        lifecycle_mocks.handler.close_async.side_effect = _hang

        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        await c.start()
        task_ref = c._task  # noqa: SLF001
        assert task_ref is not None

        await c.stop()
        # With _SHUTDOWN_TIMEOUT_S=0.1 the task is cancelled rather than
        # awaited indefinitely.
        assert task_ref.cancelled() or task_ref.done()
        assert not c.connected


# ---------------------------------------------------------------------------
# Message-id encode / decode
# ---------------------------------------------------------------------------


class TestMessageIdCodec:
    def test_roundtrip(self) -> None:
        encoded = _encode_msg_id("C123", "1712345678.001")
        assert _decode_msg_id(encoded) == ("C123", "1712345678.001")

    def test_decode_rejects_missing_pipe(self) -> None:
        with pytest.raises(ValueError, match="slack message id"):
            _decode_msg_id("1712345678.001")

    def test_decode_rejects_empty_ts(self) -> None:
        with pytest.raises(ValueError):
            _decode_msg_id("C123|")

    def test_decode_rejects_empty_channel(self) -> None:
        with pytest.raises(ValueError):
            _decode_msg_id("|1712345678.001")


# ---------------------------------------------------------------------------
# Identity construction
# ---------------------------------------------------------------------------


def _make_event(
    *,
    user: str = "U100",
    channel: str = "C200",
    channel_type: str = "channel",
    text: str = "hi",
    ts: str = "1712345678.001",
    thread_ts: str | None = None,
    team: str = "T300",
    subtype: str | None = None,
    bot_id: str | None = None,
    files: list[dict] | None = None,
) -> dict:
    """Build a minimal Slack message event dict."""
    event: dict = {
        "type": "message",
        "user": user,
        "channel": channel,
        "channel_type": channel_type,
        "text": text,
        "ts": ts,
        "team": team,
    }
    if thread_ts is not None:
        event["thread_ts"] = thread_ts
    if subtype is not None:
        event["subtype"] = subtype
    if bot_id is not None:
        event["bot_id"] = bot_id
    if files is not None:
        event["files"] = files
    return event


class TestIdentityConstruction:
    async def test_dm_emits_slack_user_prefix(self) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        c._display_name_cache["U100"] = "Alice"  # skip users.info lookup  # noqa: SLF001

        identity = await c._make_identity(_make_event(  # noqa: SLF001
            user="U100", channel="D400", channel_type="im",
        ))
        assert identity.external_id == "slack:user:U100"
        assert identity.is_group is False
        assert identity.display_name == "Alice"
        assert identity.metadata["user"] == "U100"
        assert identity.metadata["channel"] == "D400"
        assert identity.metadata["channel_type"] == "im"

    async def test_channel_emits_slack_channel_prefix(self) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        c._display_name_cache["U100"] = "Alice"  # noqa: SLF001

        identity = await c._make_identity(_make_event(  # noqa: SLF001
            channel="C200", channel_type="channel",
        ))
        assert identity.external_id == "slack:channel:C200"
        assert identity.is_group is True

    async def test_group_is_group(self) -> None:
        """Private channels arrive as channel_type='group'."""
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        c._display_name_cache["U100"] = "Alice"  # noqa: SLF001

        identity = await c._make_identity(_make_event(  # noqa: SLF001
            channel="G500", channel_type="group",
        ))
        assert identity.external_id == "slack:channel:G500"
        assert identity.is_group is True

    async def test_mpim_is_group(self) -> None:
        """Multi-person DMs arrive as channel_type='mpim'."""
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        c._display_name_cache["U100"] = "Alice"  # noqa: SLF001

        identity = await c._make_identity(_make_event(  # noqa: SLF001
            channel="G600", channel_type="mpim",
        ))
        assert identity.external_id == "slack:channel:G600"
        assert identity.is_group is True

    async def test_thread_ts_stored_in_metadata(self) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        c._display_name_cache["U100"] = "Alice"  # noqa: SLF001

        identity = await c._make_identity(_make_event(  # noqa: SLF001
            channel_type="channel", thread_ts="1712345000.000",
        ))
        assert identity.metadata["thread_ts"] == "1712345000.000"

    async def test_display_name_lazy_cache(self) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        app = MagicMock()
        app.client = MagicMock()
        app.client.users_info = AsyncMock(return_value={
            "user": {"profile": {"display_name": "Alice"}},
        })
        c._app = app  # noqa: SLF001

        name1 = await c._resolve_display_name("U100")  # noqa: SLF001
        name2 = await c._resolve_display_name("U100")  # noqa: SLF001
        assert name1 == name2 == "Alice"
        # Cached → users.info hit exactly once.
        app.client.users_info.assert_awaited_once_with(user="U100")

    async def test_display_name_falls_back_to_user_id_on_error(self) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        app = MagicMock()
        app.client = MagicMock()
        err = SlackApiError(
            message="user_not_found",
            response=MagicMock(),
        )
        app.client.users_info = AsyncMock(side_effect=err)
        c._app = app  # noqa: SLF001

        assert await c._resolve_display_name("U404") == "U404"  # noqa: SLF001


# ---------------------------------------------------------------------------
# Inbound filtering
# ---------------------------------------------------------------------------


class TestInboundFiltering:
    async def test_bot_messages_dropped(self) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)

        c.set_message_handler(handler)
        await c._on_message_event(_make_event(bot_id="B0101"))  # noqa: SLF001
        assert received == []

    async def test_message_edit_subtype_dropped(self) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        received: list[MessageEvent] = []
        c.set_message_handler(lambda e: received.append(e) or asyncio.sleep(0))
        await c._on_message_event(_make_event(subtype="message_changed"))  # noqa: SLF001
        assert received == []

    async def test_message_deleted_subtype_dropped(self) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        received: list[MessageEvent] = []
        c.set_message_handler(lambda e: received.append(e) or asyncio.sleep(0))
        await c._on_message_event(_make_event(subtype="message_deleted"))  # noqa: SLF001
        assert received == []

    async def test_channel_join_subtype_dropped(self) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        received: list[MessageEvent] = []
        c.set_message_handler(lambda e: received.append(e) or asyncio.sleep(0))
        await c._on_message_event(_make_event(subtype="channel_join"))  # noqa: SLF001
        assert received == []

    async def test_no_handler_registered_drops_silently(self) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        # No set_message_handler call. Must not raise.
        await c._on_message_event(_make_event())  # noqa: SLF001

    async def test_happy_path_text_reaches_handler(self) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        c._display_name_cache["U100"] = "Alice"  # noqa: SLF001

        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)

        c.set_message_handler(handler)
        await c._on_message_event(_make_event(text="hello tank"))  # noqa: SLF001

        assert len(received) == 1
        assert received[0].text == "hello tank"
        assert received[0].identity.platform == "slack"


# ---------------------------------------------------------------------------
# Inbound images
# ---------------------------------------------------------------------------


class TestInboundImages:
    async def test_image_file_becomes_attachment(self) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        c._display_name_cache["U100"] = "Alice"  # noqa: SLF001

        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)

        c.set_message_handler(handler)

        # Patch _download_file directly — the aiohttp fetching logic
        # is exercised in TestFileDownload below.
        async def _fake_download(file_info: dict):
            return Attachment(
                kind="image", data=b"\x89PNG...",
                mime_type=file_info.get("mimetype") or "image/png",
            )
        c._download_file = _fake_download  # type: ignore[assignment]  # noqa: SLF001

        await c._on_message_event(_make_event(  # noqa: SLF001
            text="look",
            files=[{
                "mimetype": "image/png",
                "url_private": "https://files.slack.com/x",
            }],
        ))

        assert len(received) == 1
        assert len(received[0].attachments) == 1
        att = received[0].attachments[0]
        assert att.kind == "image"
        assert att.mime_type == "image/png"


class TestFileDownload:
    async def test_non_image_dropped_silently(self) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        result = await c._download_file({  # noqa: SLF001
            "mimetype": "application/pdf",
            "url_private": "https://x.example/y.pdf",
        })
        assert result is None

    async def test_missing_url_returns_none(self) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        result = await c._download_file({"mimetype": "image/png"})  # noqa: SLF001
        assert result is None

    async def test_oversized_image_rejected_by_declared_size(self) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        result = await c._download_file({  # noqa: SLF001
            "mimetype": "image/png",
            "url_private": "https://x/img.png",
            "size": 30 * 1024 * 1024,  # >25MB cap
        })
        assert result is None


# ---------------------------------------------------------------------------
# Outbound — send text
# ---------------------------------------------------------------------------


def _identity(
    *,
    channel: str = "C200",
    external_id: str = "slack:channel:C200",
    thread_ts: str | None = None,
) -> Identity:
    metadata: dict = {"channel": channel}
    if thread_ts is not None:
        metadata["thread_ts"] = thread_ts
    return Identity(
        platform="slack",
        external_id=external_id,
        metadata=metadata,
    )


@pytest.fixture()
def started_connector():
    """Yield a SlackConnector with ``_app`` set to a mock (skip lifecycle)."""
    c = SlackConnector(
        instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
    )
    app = MagicMock()
    app.client = MagicMock()
    c._app = app  # noqa: SLF001
    c._connected = True  # noqa: SLF001
    return c


class TestSendText:
    async def test_happy_path(self, started_connector) -> None:
        started_connector._app.client.chat_postMessage = AsyncMock(  # noqa: SLF001
            return_value={"ok": True, "ts": "1712345678.100", "channel": "C200"},
        )

        result = await started_connector.send(_identity(), "hello")

        assert result.ok is True
        assert result.message_id == "C200|1712345678.100"
        kwargs = started_connector._app.client.chat_postMessage.call_args.kwargs  # noqa: SLF001
        assert kwargs["channel"] == "C200"
        assert kwargs["text"] == "hello"
        # No thread_ts in metadata → no thread on outbound.
        assert "thread_ts" not in kwargs

    async def test_thread_ts_propagated(self, started_connector) -> None:
        started_connector._app.client.chat_postMessage = AsyncMock(  # noqa: SLF001
            return_value={"ok": True, "ts": "1712345678.200", "channel": "C200"},
        )

        await started_connector.send(
            _identity(thread_ts="1712345000.000"), "hello",
        )
        kwargs = started_connector._app.client.chat_postMessage.call_args.kwargs  # noqa: SLF001
        assert kwargs["thread_ts"] == "1712345000.000"

    async def test_truncates_at_40k(self, started_connector) -> None:
        started_connector._app.client.chat_postMessage = AsyncMock(  # noqa: SLF001
            return_value={"ok": True, "ts": "1", "channel": "C200"},
        )
        long = "x" * 50_000
        await started_connector.send(_identity(), long)
        sent = (
            started_connector._app.client.chat_postMessage.call_args.kwargs["text"]  # noqa: SLF001
        )
        assert len(sent) == 40_000
        assert sent.endswith("…")

    async def test_not_connected_returns_error(self) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        result = await c.send(_identity(), "hello")
        assert result.ok is False
        assert result.error == "not connected"

    async def test_missing_channel_metadata_returns_bad_identity(
        self, started_connector,
    ) -> None:
        bad = Identity(
            platform="slack",
            external_id="slack:channel:C200",
            metadata={},  # no channel key
        )
        result = await started_connector.send(bad, "hello")
        assert result.ok is False
        assert "bad_identity" in (result.error or "")

    async def test_rate_limited_classified_from_header(
        self, started_connector,
    ) -> None:
        response = MagicMock()
        response.headers = {"retry-after": "30"}
        response.get = MagicMock(return_value="ratelimited")
        err = SlackApiError(message="ratelimited", response=response)
        started_connector._app.client.chat_postMessage = AsyncMock(  # noqa: SLF001
            side_effect=err,
        )
        result = await started_connector.send(_identity(), "hello")
        assert result.ok is False
        assert result.error == "rate_limited:30"

    async def test_generic_api_error_returns_slack_prefix(
        self, started_connector,
    ) -> None:
        response = MagicMock()
        response.headers = {}
        response.get = MagicMock(return_value="channel_not_found")
        err = SlackApiError(message="channel_not_found", response=response)
        started_connector._app.client.chat_postMessage = AsyncMock(  # noqa: SLF001
            side_effect=err,
        )
        result = await started_connector.send(_identity(), "hello")
        assert result.ok is False
        assert result.error is not None
        assert result.error.startswith("slack:")

    async def test_missing_ts_in_response_surfaces_error(
        self, started_connector,
    ) -> None:
        started_connector._app.client.chat_postMessage = AsyncMock(  # noqa: SLF001
            return_value={"ok": True, "channel": "C200"},  # no ts
        )
        result = await started_connector.send(_identity(), "hello")
        assert result.ok is False
        assert result.error is not None
        assert "missing_ts" in result.error


# ---------------------------------------------------------------------------
# Outbound — send image
# ---------------------------------------------------------------------------


class TestSendImage:
    async def test_bytes_image_uses_files_upload_v2(
        self, started_connector,
    ) -> None:
        started_connector._app.client.files_upload_v2 = AsyncMock(  # noqa: SLF001
            return_value={"ok": True, "files": []},
        )
        started_connector._app.client.chat_postMessage = AsyncMock()  # noqa: SLF001

        att = Attachment(kind="image", data=b"\x89PNG...", mime_type="image/png")
        result = await started_connector.send(
            _identity(), "see this", attachments=(att,),
        )

        assert result.ok is True
        # No message_id exposed — image sends aren't edit-addressable.
        assert result.message_id is None

        kwargs = (
            started_connector._app.client.files_upload_v2.call_args.kwargs  # noqa: SLF001
        )
        assert kwargs["content"] == b"\x89PNG..."
        assert kwargs["channel"] == "C200"
        assert kwargs["initial_comment"] == "see this"
        # chat.postMessage was NOT used — image path only.
        started_connector._app.client.chat_postMessage.assert_not_awaited()  # noqa: SLF001

    async def test_empty_payload_rejected(self, started_connector) -> None:
        started_connector._app.client.files_upload_v2 = AsyncMock()  # noqa: SLF001
        att = Attachment(kind="image", data=b"", mime_type="image/png")
        result = await started_connector.send(
            _identity(), "", attachments=(att,),
        )
        assert result.ok is False
        assert result.error == "empty_payload"
        started_connector._app.client.files_upload_v2.assert_not_awaited()  # noqa: SLF001

    async def test_caption_truncated(self, started_connector) -> None:
        started_connector._app.client.files_upload_v2 = AsyncMock(  # noqa: SLF001
            return_value={"ok": True, "files": []},
        )
        att = Attachment(kind="image", data=b"\x89PNG", mime_type="image/png")
        long = "c" * 50_000
        await started_connector.send(
            _identity(), long, attachments=(att,),
        )
        comment = (
            started_connector._app.client.files_upload_v2.call_args.kwargs  # noqa: SLF001
            ["initial_comment"]
        )
        assert len(comment) == 40_000
        assert comment.endswith("…")

    async def test_upload_failure_surfaces_slack_error(
        self, started_connector,
    ) -> None:
        response = MagicMock()
        response.headers = {}
        response.get = MagicMock(return_value="file_uploads_disabled")
        err = SlackApiError(
            message="file_uploads_disabled", response=response,
        )
        started_connector._app.client.files_upload_v2 = AsyncMock(  # noqa: SLF001
            side_effect=err,
        )
        att = Attachment(kind="image", data=b"\x89PNG", mime_type="image/png")
        result = await started_connector.send(
            _identity(), "see this", attachments=(att,),
        )
        assert result.ok is False
        assert result.error is not None
        assert result.error.startswith("slack:")


# ---------------------------------------------------------------------------
# Outbound — edit
# ---------------------------------------------------------------------------


class TestEdit:
    async def test_happy_path(self, started_connector) -> None:
        started_connector._app.client.chat_update = AsyncMock(  # noqa: SLF001
            return_value={"ok": True},
        )
        msg_id = "C200|1712345678.100"
        result = await started_connector.edit(
            _identity(), msg_id, "edited text",
        )
        assert result.ok is True
        assert result.message_id == msg_id
        kwargs = started_connector._app.client.chat_update.call_args.kwargs  # noqa: SLF001
        assert kwargs["channel"] == "C200"
        assert kwargs["ts"] == "1712345678.100"
        assert kwargs["text"] == "edited text"

    async def test_bad_message_id_rejected(self, started_connector) -> None:
        started_connector._app.client.chat_update = AsyncMock()  # noqa: SLF001
        result = await started_connector.edit(
            _identity(), "not-a-composite", "text",
        )
        assert result.ok is False
        assert result.error is not None
        assert "bad_message_id" in result.error
        started_connector._app.client.chat_update.assert_not_awaited()  # noqa: SLF001

    async def test_rate_limited_classified(self, started_connector) -> None:
        response = MagicMock()
        response.headers = {"Retry-After": "7"}
        response.get = MagicMock(return_value="ratelimited")
        err = SlackApiError(message="ratelimited", response=response)
        started_connector._app.client.chat_update = AsyncMock(  # noqa: SLF001
            side_effect=err,
        )
        result = await started_connector.edit(
            _identity(), "C200|1712345678.100", "text",
        )
        assert result.ok is False
        assert result.error == "rate_limited:7"

    async def test_not_connected_returns_error(self) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        result = await c.edit(_identity(), "C|1", "text")
        assert result.ok is False
        assert result.error == "not connected"

    async def test_edit_truncates_long_text(self, started_connector) -> None:
        started_connector._app.client.chat_update = AsyncMock(  # noqa: SLF001
            return_value={"ok": True},
        )
        await started_connector.edit(
            _identity(), "C200|1712345678.100", "x" * 50_000,
        )
        sent = started_connector._app.client.chat_update.call_args.kwargs["text"]  # noqa: SLF001
        assert len(sent) == 40_000
