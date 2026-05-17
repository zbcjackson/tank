"""Unit tests for :class:`SlackConnector` and ``create_connector``.

All tests use mocks — no real slack_bolt AsyncApp is instantiated, no
HTTP calls fire. Covers factory validation, capabilities, lifecycle,
inbound translation (text + images), inbound subtype filtering,
outbound send / edit (happy paths, rate-limit, bad identity), composite
message-id encoding, and the DM vs channel identity split.
"""

from __future__ import annotations

import asyncio
import time
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
        # Phase 13: voice-in via ffmpeg sniffing of Slack's mixed
        # audio/webm / audio/mp4 / audio/mpeg payloads. Outbound
        # voice still deferred — no ``sendAudioMessage`` equivalent
        # in Slack's Web API today.
        assert caps.supports_voice_in is True
        assert caps.supports_voice_out is True
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
            # Polling task was spawned via the shared BackgroundTaskRunner.
            assert c._runner.running  # noqa: SLF001
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
        assert not c._runner.running  # noqa: SLF001
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
        assert c._runner.running  # noqa: SLF001

        await c.stop()
        # With _SHUTDOWN_TIMEOUT_S=0.1 the runner cancelled the task
        # rather than awaiting it indefinitely.
        assert not c._runner.running  # noqa: SLF001
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
        c._display_name_cache["U100"] = ("Alice", 9999999999.0)  # skip users.info lookup  # noqa: SLF001

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
        c._display_name_cache["U100"] = ("Alice", 9999999999.0)  # noqa: SLF001

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
        c._display_name_cache["U100"] = ("Alice", 9999999999.0)  # noqa: SLF001

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
        c._display_name_cache["U100"] = ("Alice", 9999999999.0)  # noqa: SLF001

        identity = await c._make_identity(_make_event(  # noqa: SLF001
            channel="G600", channel_type="mpim",
        ))
        assert identity.external_id == "slack:channel:G600"
        assert identity.is_group is True

    async def test_thread_ts_stored_in_metadata(self) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        c._display_name_cache["U100"] = ("Alice", 9999999999.0)  # noqa: SLF001

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
        c._display_name_cache["U100"] = ("Alice", 9999999999.0)  # noqa: SLF001

        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)

        c.set_message_handler(handler)
        await c._on_message_event(_make_event(text="hello tank"))  # noqa: SLF001

        assert len(received) == 1
        assert received[0].text == "hello tank"
        assert received[0].identity.platform == "slack"

    async def test_file_share_subtype_is_accepted(self) -> None:
        """Regression: real Slack messages carrying any file upload
        (image, audio, doc, video) arrive with ``subtype="file_share"``.
        The connector must forward them — a prior catch-all "drop
        unknown subtypes" guard silently ate the whole message along
        with its ``files`` array, which is why Slack voice-in and
        (presumably) image upload looked broken before the fix in
        this regression guard landed."""
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        c._display_name_cache["U100"] = ("Alice", 9999999999.0)  # noqa: SLF001

        # Patch _download_file so we don't hit the network; the event
        # just needs to reach the handler.
        async def _fake_download(file_info: dict):
            return Attachment(
                kind="audio",
                data=b"\x00" * 512,
                mime_type=file_info.get("mimetype") or "audio/webm",
            )
        c._download_file = _fake_download  # type: ignore[assignment]  # noqa: SLF001

        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)

        c.set_message_handler(handler)

        await c._on_message_event(_make_event(  # noqa: SLF001
            subtype="file_share",
            text="",
            files=[{
                "mimetype": "audio/webm",
                "url_private": "https://files.slack.com/x",
                "size": 1024,
            }],
        ))

        assert len(received) == 1
        assert len(received[0].attachments) == 1
        assert received[0].attachments[0].kind == "audio"

    async def test_unknown_subtype_still_dropped_defensively(self) -> None:
        """The catch-all drop for unknown subtypes stays — it's just
        no longer blanket. Anything not in ``_ACCEPTED_SUBTYPES`` or
        ``_IGNORED_SUBTYPES`` gets logged and dropped so new Slack
        message types don't silently slip through."""
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)

        c.set_message_handler(handler)

        # A subtype that isn't in either list — Slack adds new ones
        # periodically (``huddle_thread``, ``sh_room_created``, …).
        await c._on_message_event(_make_event(  # noqa: SLF001
            subtype="huddle_thread",
        ))
        assert received == []


# ---------------------------------------------------------------------------
# Inbound images
# ---------------------------------------------------------------------------


class TestInboundImages:
    async def test_image_file_becomes_attachment(self) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        c._display_name_cache["U100"] = ("Alice", 9999999999.0)  # noqa: SLF001

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
            subtype="file_share",
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
        """Non-image, non-audio mimes (documents, video, etc.) are
        dropped at the ``_download_file`` gate. Slack delivers PDFs,
        office docs, and video via the same ``files`` array as audio
        and images, so the mime filter is what separates supported
        kinds from everything else."""
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

    async def test_audio_mime_missing_url_returns_none(self) -> None:
        """Phase 13: audio files with no ``url_private`` (shouldn't
        happen in practice but defensive) fail the same way images do."""
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        result = await c._download_file({"mimetype": "audio/webm"})  # noqa: SLF001
        assert result is None

    async def test_oversized_audio_rejected_by_declared_size(self) -> None:
        """Phase 13: the same 25 MiB ceiling applies to audio — Slack
        allows much larger files in absolute terms, but anything over
        25 MB is a misclick for an ASR pipeline."""
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        result = await c._download_file({  # noqa: SLF001
            "mimetype": "audio/webm",
            "url_private": "https://x/voice.webm",
            "size": 30 * 1024 * 1024,  # >25MB cap
        })
        assert result is None


class TestAudioDownload:
    """Phase 13: voice-in. Slack delivers recorded audio through the
    same ``files`` array as images — the connector's ``_download_file``
    now accepts ``audio/*`` MIMEs, fetches with the bot-token auth
    header, and wraps the bytes as ``Attachment(kind="audio")``. The
    manager's ``_audio_to_text_block`` then routes the bytes through
    :func:`decode_any_audio` for ffmpeg-sniffed decoding."""

    @pytest.mark.parametrize(
        "mime",
        [
            "audio/webm",      # Slack desktop (Opus-in-WebM)
            "audio/mp4",       # Slack iOS (AAC-in-MP4)
            "audio/mpeg",      # Legacy MP3 uploads
            "audio/ogg",       # Mobile Chrome recordings sometimes
        ],
    )
    async def test_audio_mime_becomes_audio_attachment(
        self, mime: str,
    ) -> None:
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )

        async def _fake_download(file_info: dict) -> Attachment | None:
            return Attachment(
                kind="audio",
                data=b"\x00" * 1024,
                mime_type=file_info["mimetype"],
            )

        c._download_file = _fake_download  # type: ignore[assignment]  # noqa: SLF001

        event: dict = {
            "type": "message",
            # Real Slack payloads with file uploads carry
            # subtype="file_share". The connector must accept it so
            # the ``files`` array is processed.
            "subtype": "file_share",
            "channel": "D123",
            "channel_type": "im",
            "user": "U99",
            "ts": "1234567890.001",
            "files": [{
                "mimetype": mime,
                "url_private": "https://files.slack.com/T/x",
                "size": 4096,
            }],
        }

        received: list[MessageEvent] = []

        async def _handler(evt: MessageEvent) -> None:
            received.append(evt)

        c.set_message_handler(_handler)
        await c._on_message_event(event)  # noqa: SLF001

        assert len(received) == 1
        attachments = received[0].attachments
        assert len(attachments) == 1
        assert attachments[0].kind == "audio"
        assert attachments[0].mime_type == mime

    async def test_audio_file_caps_enforced_on_declared_size(self) -> None:
        """The 25 MiB cap on ``audio/*`` matches ``image/*``. Check
        both the declared-size gate and the post-read recheck hit."""
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        # Declared > cap → short-circuit before the HTTP GET.
        result = await c._download_file({  # noqa: SLF001
            "mimetype": "audio/webm",
            "url_private": "https://x/voice.webm",
            "size": 26 * 1024 * 1024,
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


# ---------------------------------------------------------------------------
# Phase 8 — Mention-only mode
# ---------------------------------------------------------------------------


class TestMentionOnly:
    """In public channels / groups / MPIMs, the ``mention_only`` flag
    narrows delivery to messages that mention the bot. DMs always get
    through regardless. The mention token is stripped from the forwarded
    text so the LLM doesn't see Slack's ``<@U0BOTID>`` syntax."""

    async def test_mention_only_false_forwards_every_channel_message(
        self,
    ) -> None:
        """Default behaviour (``mention_only=False``) is unchanged —
        channel messages forward regardless of mention."""
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
            mention_only=False,
        )
        c._display_name_cache["U100"] = ("Alice", 9999999999.0)  # noqa: SLF001

        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)

        c.set_message_handler(handler)
        await c._on_message_event(_make_event(  # noqa: SLF001
            text="hi tank", channel_type="channel",
        ))
        assert len(received) == 1

    async def test_mention_only_drops_non_mention_in_channel(self) -> None:
        """``mention_only=True`` filters channel messages that don't
        contain the bot's ``<@...>`` token."""
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
            mention_only=True,
        )
        c._bot_user_id = "U0BOTID"  # noqa: SLF001 — simulate auth.test resolution
        c._display_name_cache["U100"] = ("Alice", 9999999999.0)  # noqa: SLF001

        received: list[MessageEvent] = []
        c.set_message_handler(lambda e: received.append(e) or asyncio.sleep(0))

        await c._on_message_event(_make_event(  # noqa: SLF001
            text="hi everyone", channel_type="channel",
        ))
        # No mention → dropped.
        assert received == []

    async def test_mention_only_forwards_channel_message_when_mentioned(
        self,
    ) -> None:
        """The ``<@U0BOTID>`` mention token gates delivery; once present,
        the message forwards with the token stripped from the text."""
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
            mention_only=True,
        )
        c._bot_user_id = "U0BOTID"  # noqa: SLF001
        c._display_name_cache["U100"] = ("Alice", 9999999999.0)  # noqa: SLF001

        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)

        c.set_message_handler(handler)
        await c._on_message_event(_make_event(  # noqa: SLF001
            text="<@U0BOTID> what's the weather?", channel_type="channel",
        ))

        assert len(received) == 1
        # Mention token stripped — the LLM sees just the user's prompt.
        assert received[0].text == "what's the weather?"

    async def test_mention_only_always_forwards_dms(self) -> None:
        """DMs bypass the mention filter — the user is obviously talking
        to the bot, no ``@`` needed."""
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
            mention_only=True,
        )
        c._bot_user_id = "U0BOTID"  # noqa: SLF001
        c._display_name_cache["U100"] = ("Alice", 9999999999.0)  # noqa: SLF001

        received: list[MessageEvent] = []
        c.set_message_handler(lambda e: received.append(e) or asyncio.sleep(0))

        await c._on_message_event(_make_event(  # noqa: SLF001
            text="just a casual hello", channel_type="im",
        ))
        assert len(received) == 1
        # No mention token was present; text passes through unchanged.
        assert received[0].text == "just a casual hello"

    async def test_mention_only_without_bot_user_id_drops_channel_msgs(
        self,
    ) -> None:
        """Safe failure: if ``auth.test`` didn't resolve ``_bot_user_id``
        at start-up, the mention filter can't recognise any mention and
        so drops every channel message. Documented trade-off: silent
        channels (investigable) beats accidental allow-all."""
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
            mention_only=True,
        )
        # _bot_user_id left as None (auth.test failed or was never called)
        c._display_name_cache["U100"] = ("Alice", 9999999999.0)  # noqa: SLF001

        received: list[MessageEvent] = []
        c.set_message_handler(lambda e: received.append(e) or asyncio.sleep(0))

        await c._on_message_event(_make_event(  # noqa: SLF001
            text="<@UOTHER> hello", channel_type="channel",
        ))
        assert received == []


# ---------------------------------------------------------------------------
# Phase 8 — Display-name cache TTL
# ---------------------------------------------------------------------------


class TestDisplayNameTtl:
    """Cached display names go stale when users rename. The TTL catches
    those without forcing a ``users.info`` call on every inbound
    message."""

    async def test_cache_hit_within_ttl_does_not_refetch(self) -> None:
        """An entry with an expiry timestamp in the future is returned
        from cache without hitting the Slack API."""
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        # Seed with a far-future expiry: should always be a cache hit.
        c._display_name_cache["U42"] = ("Alice", 9999999999.0)  # noqa: SLF001
        # Attach a stub ``_app`` that would fail the test if called.
        app = MagicMock()
        app.client = MagicMock()
        app.client.users_info = AsyncMock(
            side_effect=AssertionError("users.info must not be called"),
        )
        c._app = app  # noqa: SLF001

        name = await c._resolve_display_name("U42")  # noqa: SLF001
        assert name == "Alice"
        app.client.users_info.assert_not_awaited()

    async def test_cache_expired_entry_is_refreshed(self) -> None:
        """A cached entry whose expiry is in the past triggers a fresh
        ``users.info`` call; the old name is replaced with the new one
        and re-cached with a new expiry."""
        c = SlackConnector(
            instance_name="t", bot_token="xoxb-t", app_token="xapp-t",
        )
        # Seed with expiry=0 (epoch) → definitively stale.
        c._display_name_cache["U42"] = ("OldName", 0.0)  # noqa: SLF001
        app = MagicMock()
        app.client = MagicMock()
        app.client.users_info = AsyncMock(return_value={
            "user": {"profile": {"display_name": "NewName"}},
        })
        c._app = app  # noqa: SLF001

        name = await c._resolve_display_name("U42")  # noqa: SLF001
        assert name == "NewName"
        app.client.users_info.assert_awaited_once_with(user="U42")

        # Cache was refreshed with a fresh expiry well in the future.
        cached_name, cached_expiry = c._display_name_cache["U42"]  # noqa: SLF001
        assert cached_name == "NewName"
        assert cached_expiry > time.time() + 3600  # at least one hour of freshness


# ---------------------------------------------------------------------------
# Phase 10 — Approval buttons (send_approval_prompt + _on_approval_action)
# ---------------------------------------------------------------------------


class TestApprovalPrompt:
    """Slack renders buttons via Block Kit. The ``action_id`` on each
    button encodes ``approve:<choice>:<approval_id>`` so the action
    handler can decode the click without consulting any other state."""

    async def test_renders_three_buttons_with_expected_action_ids(
        self, started_connector,
    ) -> None:
        started_connector._app.client.chat_postMessage = AsyncMock(  # noqa: SLF001
            return_value={"ok": True, "ts": "1", "channel": "D42"},
        )
        admin = Identity(
            platform="slack",
            external_id="slack:user:U42",
            metadata={},
        )
        sender = Identity(
            platform="slack",
            external_id="slack:user:U99",
            display_name="Alice",
            metadata={},
        )

        await started_connector.send_approval_prompt(
            admin_identity=admin,
            approval_id="abc1234567890def",
            sender=sender,
            preview="hello tank",
        )

        started_connector._app.client.chat_postMessage.assert_awaited_once()  # noqa: SLF001
        kwargs = (
            started_connector._app.client.chat_postMessage.call_args.kwargs  # noqa: SLF001
        )
        # Slack accepts user ids directly in ``channel`` for DMs.
        assert kwargs["channel"] == "U42"

        blocks = kwargs["blocks"]
        assert len(blocks) == 2
        section, actions = blocks
        assert section["type"] == "section"
        # Section text mentions the sender + preview.
        assert "Alice" in section["text"]["text"]
        assert "slack:user:U99" in section["text"]["text"]
        assert "hello tank" in section["text"]["text"]

        assert actions["type"] == "actions"
        button_elements = actions["elements"]
        assert len(button_elements) == 3
        action_ids = sorted(b["action_id"] for b in button_elements)
        assert action_ids == [
            "approve:allow_forever:abc1234567890def",
            "approve:allow_once:abc1234567890def",
            "approve:deny:abc1234567890def",
        ]
        # Deny button uses the danger style.
        deny = next(b for b in button_elements if "deny" in b["action_id"])
        assert deny.get("style") == "danger"

    async def test_unparseable_admin_external_id_is_noop(
        self, started_connector,
    ) -> None:
        started_connector._app.client.chat_postMessage = AsyncMock()  # noqa: SLF001
        bad = Identity(
            platform="slack",
            external_id="",  # no colon → rpartition returns ("", "", "")
            metadata={},
        )
        await started_connector.send_approval_prompt(
            admin_identity=bad,
            approval_id="abc",
            sender=Identity(platform="slack", external_id="x", metadata={}),
            preview="x",
        )
        started_connector._app.client.chat_postMessage.assert_not_awaited()  # noqa: SLF001


class TestApprovalAction:
    @staticmethod
    def _make_pending(sender_id: str = "U99") -> MagicMock:
        """A ``PendingApproval``-shaped mock for the broker's ``resolve``
        return value. The click handler reads ``resolved.event.identity``
        to render the outcome text."""
        pending = MagicMock()
        pending.event.identity = Identity(
            platform="slack",
            external_id=f"slack:user:{sender_id}",
            display_name="Alice",
            is_group=False,
            metadata={"user": sender_id},
        )
        return pending

    @staticmethod
    def _body(
        *,
        action_id: str = "approve:allow_forever:abc1234567890def",
        channel_id: str | None = "C123",
        message_ts: str | None = "1234567890.001",
        user_id: str = "U42",
        user_name: str = "admin",
    ) -> dict:
        """Build a plausible slack_bolt action payload.

        ``container.channel_id`` + ``container.message_ts`` drive the
        ``chat_update`` call; omit them to test the graceful-degrade path
        where the connector skips the edit but still resolves.
        """
        container: dict = {}
        if channel_id is not None:
            container["channel_id"] = channel_id
        if message_ts is not None:
            container["message_ts"] = message_ts
        return {
            "actions": [{
                "action_id": action_id,
                "value": action_id.rsplit(":", 1)[-1],
            }],
            "user": {"id": user_id, "name": user_name},
            "container": container,
        }

    async def test_ack_and_dispatch_to_broker(
        self, started_connector,
    ) -> None:
        """Happy path: ack the click, route to ``broker.resolve``, then
        overwrite the prompt with the outcome via ``chat_update`` so the
        three Block Kit buttons vanish."""
        broker = MagicMock()
        broker.resolve = AsyncMock(return_value=self._make_pending("U99"))
        started_connector.set_approval_broker(broker)
        started_connector._app.client.chat_update = AsyncMock()  # noqa: SLF001

        ack = AsyncMock()
        body = self._body()

        await started_connector._on_approval_action(ack, body)  # noqa: SLF001

        ack.assert_awaited_once()
        broker.resolve.assert_awaited_once()
        args = broker.resolve.call_args.args
        assert args[0] == "abc1234567890def"
        assert args[1] == "allow_forever"
        clicker = args[2]
        assert clicker.external_id == "slack:user:U42"

        # Prompt was edited — empty ``blocks`` strips the buttons.
        started_connector._app.client.chat_update.assert_awaited_once()  # noqa: SLF001
        kwargs = started_connector._app.client.chat_update.call_args.kwargs  # noqa: SLF001
        assert kwargs["channel"] == "C123"
        assert kwargs["ts"] == "1234567890.001"
        assert kwargs["blocks"] == []
        assert "Approved forever" in kwargs["text"]
        assert "Alice" in kwargs["text"]

    async def test_stale_resolve_does_not_edit_prompt(
        self, started_connector,
    ) -> None:
        """Broker returns ``None`` for stale clicks; the handler must
        leave the Block Kit message alone so a real admin can still
        act on it."""
        broker = MagicMock()
        broker.resolve = AsyncMock(return_value=None)
        started_connector.set_approval_broker(broker)
        started_connector._app.client.chat_update = AsyncMock()  # noqa: SLF001

        await started_connector._on_approval_action(  # noqa: SLF001
            AsyncMock(), self._body(),
        )
        started_connector._app.client.chat_update.assert_not_awaited()  # noqa: SLF001

    async def test_missing_channel_ts_skips_edit(
        self, started_connector,
    ) -> None:
        """Defensive: older slack_bolt payloads (or weird edge cases)
        may elide ``container.channel_id``/``message_ts``. The handler
        logs and skips the edit rather than raising — the broker's work
        already landed."""
        broker = MagicMock()
        broker.resolve = AsyncMock(return_value=self._make_pending("U99"))
        started_connector.set_approval_broker(broker)
        started_connector._app.client.chat_update = AsyncMock()  # noqa: SLF001

        body = self._body(channel_id=None, message_ts=None)
        # No ``channel`` fallback either.
        body.pop("channel", None)
        body.pop("message", None)

        await started_connector._on_approval_action(  # noqa: SLF001
            AsyncMock(), body,
        )
        started_connector._app.client.chat_update.assert_not_awaited()  # noqa: SLF001

    async def test_falls_back_to_legacy_channel_message_shape(
        self, started_connector,
    ) -> None:
        """Older payloads carry ``channel.id`` / ``message.ts`` instead
        of ``container.channel_id`` / ``container.message_ts``. The
        handler uses whichever shape is present."""
        broker = MagicMock()
        broker.resolve = AsyncMock(return_value=self._make_pending("U99"))
        started_connector.set_approval_broker(broker)
        started_connector._app.client.chat_update = AsyncMock()  # noqa: SLF001

        body = self._body(channel_id=None, message_ts=None)
        body["channel"] = {"id": "C_legacy"}
        body["message"] = {"ts": "9999.000"}

        await started_connector._on_approval_action(  # noqa: SLF001
            AsyncMock(), body,
        )
        started_connector._app.client.chat_update.assert_awaited_once()  # noqa: SLF001
        kwargs = started_connector._app.client.chat_update.call_args.kwargs  # noqa: SLF001
        assert kwargs["channel"] == "C_legacy"
        assert kwargs["ts"] == "9999.000"

    async def test_chat_update_api_error_is_swallowed(
        self, started_connector,
    ) -> None:
        """If ``chat_update`` fails (expired message, missing scope,
        etc.), the connector logs at debug and moves on. The broker
        already did the real work."""
        broker = MagicMock()
        broker.resolve = AsyncMock(return_value=self._make_pending("U99"))
        started_connector.set_approval_broker(broker)
        started_connector._app.client.chat_update = AsyncMock(  # noqa: SLF001
            side_effect=SlackApiError(
                message="message_not_found", response={"ok": False},
            ),
        )

        # Must not raise.
        await started_connector._on_approval_action(  # noqa: SLF001
            AsyncMock(), self._body(),
        )
        started_connector._app.client.chat_update.assert_awaited_once()  # noqa: SLF001

    async def test_no_broker_attached_silently_acks(
        self, started_connector,
    ) -> None:
        started_connector._broker = None  # noqa: SLF001
        ack = AsyncMock()
        body = {
            "actions": [{"action_id": "approve:deny:abc"}],
            "user": {"id": "U42"},
        }
        await started_connector._on_approval_action(ack, body)  # noqa: SLF001
        ack.assert_awaited_once()

    async def test_unrecognised_action_id_is_noop(
        self, started_connector,
    ) -> None:
        broker = MagicMock()
        broker.resolve = AsyncMock()
        started_connector.set_approval_broker(broker)

        ack = AsyncMock()
        body = {
            "actions": [{"action_id": "other-feature:button"}],
            "user": {"id": "U42"},
        }
        await started_connector._on_approval_action(ack, body)  # noqa: SLF001
        ack.assert_awaited_once()
        broker.resolve.assert_not_awaited()

    async def test_missing_user_id_is_noop(self, started_connector) -> None:
        broker = MagicMock()
        broker.resolve = AsyncMock()
        started_connector.set_approval_broker(broker)

        ack = AsyncMock()
        body = {
            "actions": [{"action_id": "approve:allow_once:abc"}],
            "user": {},  # Slack body without user.id
        }
        await started_connector._on_approval_action(ack, body)  # noqa: SLF001
        broker.resolve.assert_not_awaited()

    async def test_empty_actions_list_is_noop(
        self, started_connector,
    ) -> None:
        broker = MagicMock()
        broker.resolve = AsyncMock()
        started_connector.set_approval_broker(broker)

        ack = AsyncMock()
        body = {"actions": [], "user": {"id": "U42"}}
        await started_connector._on_approval_action(ack, body)  # noqa: SLF001
        broker.resolve.assert_not_awaited()
