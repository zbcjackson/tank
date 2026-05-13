"""Unit tests for :class:`DiscordConnector` and ``create_connector``.

All tests use mocks — no real ``discord.Client`` is instantiated, no
gateway connection opens, no HTTP calls fire. Covers factory validation,
capabilities, lifecycle, composite message-id encoding, identity
construction (DM/channel/thread), inbound filtering, inbound images,
outbound send text + image, outbound edit, and typing-indicator
plumbing.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from tank_contracts.connector import Attachment, Identity, MessageEvent

from connector_discord import DiscordConnector, create_connector
from connector_discord.connector import _decode_msg_id, _encode_msg_id


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestCreateConnector:
    def test_happy_path(self) -> None:
        c = create_connector({
            "instance": "my-bot",
            "config": {"bot_token": "ABC.token.XYZ"},
        })
        assert isinstance(c, DiscordConnector)
        assert c.instance_name == "my-bot"
        assert c.platform == "discord"

    def test_missing_bot_token_raises(self) -> None:
        with pytest.raises(ValueError, match="bot_token"):
            create_connector({"instance": "x", "config": {}})

    def test_empty_bot_token_rejected(self) -> None:
        with pytest.raises(ValueError, match="bot_token"):
            create_connector({
                "instance": "x",
                "config": {"bot_token": "   "},
            })

    def test_non_dict_config_raises(self) -> None:
        with pytest.raises(ValueError, match="mapping"):
            create_connector({"instance": "x", "config": "not-a-dict"})

    def test_empty_instance_name_falls_back_to_platform(self) -> None:
        c = create_connector({"config": {"bot_token": "ABC"}})
        assert c.instance_name == "discord"


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


class TestCapabilities:
    def test_capabilities_match_discord_reality(self) -> None:
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        caps = c.capabilities
        # Discord's ~5 edits / 5 seconds per channel → 1000ms is the
        # natural floor. We use 1100ms for safety margin.
        assert caps.supports_edits is True
        assert caps.edit_min_interval_ms >= 1000
        # Discord's hard cap on chat.postMessage equivalent.
        assert caps.max_message_length == 2000
        # Phase-9 scope: text + image in both directions.
        assert caps.supports_images_in is True
        assert caps.supports_images_out is True
        # Phase 14: voice-in via ffmpeg sniffing of Discord's native
        # voice-message payloads (Opus-in-OGG) and generic audio file
        # uploads (WebM/MP3/M4A/WAV). Outbound voice still deferred —
        # Discord's voice channels are a separate subsystem.
        assert caps.supports_voice_in is True
        assert caps.supports_voice_out is False
        # Typing indicator is cheap via ``channel.typing()``.
        assert caps.supports_typing_indicator is True


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class _LifecycleMocks:
    """Captures references to the patched Client constructor + instance."""

    def __init__(
        self, client_cls: MagicMock, client: MagicMock,
    ) -> None:
        self.client_cls = client_cls
        self.client = client


@pytest.fixture()
def lifecycle_mocks():
    """Patch the ``_TankDiscordClient`` subclass so ``start()`` / ``stop()``
    exercise our lifecycle without opening a real gateway."""
    client = MagicMock(name="_TankDiscordClient")
    # ``start`` blocks until the gateway disconnects; make it awaitable
    # and slow so the task doesn't complete before stop() runs.
    async def _slow_start(token):
        await asyncio.sleep(60)
    client.start = AsyncMock(side_effect=_slow_start)
    client.close = AsyncMock()

    client_cls = MagicMock(return_value=client)

    with (
        patch("connector_discord.connector._TankDiscordClient", client_cls),
        patch("connector_discord.connector._SHUTDOWN_TIMEOUT_S", 0.1),
    ):
        yield _LifecycleMocks(client_cls=client_cls, client=client)


class TestLifecycle:
    async def test_start_creates_client_and_spawns_task(
        self, lifecycle_mocks,
    ) -> None:
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        await c.start()
        try:
            assert c.connected
            # Client was constructed with intents enabling message_content.
            _, kw = lifecycle_mocks.client_cls.call_args
            intents = kw.get("intents")
            assert isinstance(intents, discord.Intents)
            assert intents.message_content is True
            # Connector is passed so on_message can dispatch into us.
            assert kw.get("connector") is c
            # Gateway task is alive (managed by the shared runner).
            assert c._runner.running  # noqa: SLF001
        finally:
            await c.stop()

    async def test_stop_closes_client_and_drains_task(
        self, lifecycle_mocks,
    ) -> None:
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        await c.start()
        await c.stop()
        lifecycle_mocks.client.close.assert_awaited_once()
        assert not c.connected
        assert c._client is None  # noqa: SLF001
        assert not c._runner.running  # noqa: SLF001

    async def test_double_start_is_no_op(self, lifecycle_mocks) -> None:
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        await c.start()
        try:
            lifecycle_mocks.client_cls.reset_mock()
            await c.start()
            lifecycle_mocks.client_cls.assert_not_called()
        finally:
            await c.stop()

    async def test_stop_before_start_is_no_op(self, lifecycle_mocks) -> None:
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        await c.stop()
        lifecycle_mocks.client.close.assert_not_called()

    async def test_cancel_on_slow_shutdown(self, lifecycle_mocks) -> None:
        """A hung ``close()`` must not block the lifespan indefinitely —
        the task drain is bounded by ``_SHUTDOWN_TIMEOUT_S`` with a
        ``task.cancel()`` fallback."""
        async def _hang() -> None:
            await asyncio.sleep(10)
        lifecycle_mocks.client.close.side_effect = _hang

        c = DiscordConnector(instance_name="t", bot_token="xxx")
        await c.start()
        assert c._runner.running  # noqa: SLF001

        await c.stop()
        # With _SHUTDOWN_TIMEOUT_S patched low the runner cancelled
        # the task rather than awaiting it indefinitely.
        assert not c._runner.running  # noqa: SLF001
        assert not c.connected


# ---------------------------------------------------------------------------
# Message-id codec
# ---------------------------------------------------------------------------


class TestMessageIdCodec:
    def test_roundtrip(self) -> None:
        encoded = _encode_msg_id(12345, 67890)
        assert _decode_msg_id(encoded) == (12345, 67890)

    def test_decode_rejects_missing_pipe(self) -> None:
        with pytest.raises(ValueError, match="discord message id"):
            _decode_msg_id("1234567890")

    def test_decode_rejects_empty_message_id(self) -> None:
        with pytest.raises(ValueError):
            _decode_msg_id("12345|")

    def test_decode_rejects_non_numeric(self) -> None:
        with pytest.raises(ValueError):
            _decode_msg_id("C123|notanumber")


# ---------------------------------------------------------------------------
# Identity construction
# ---------------------------------------------------------------------------


def _make_mock_message(
    *,
    author_id: int = 100,
    author_name: str = "Alice",
    author_bot: bool = False,
    content: str = "hi",
    channel_id: int = 200,
    guild_id: int | None = 300,
    thread_parent_id: int | None = None,
    attachments: list[discord.Attachment] | None = None,
):
    """Build a minimal MagicMock looking like ``discord.Message``.

    ``thread_parent_id``:
        - ``None`` (default) → ``channel`` looks like a plain TextChannel
          (``parent_id`` absent) in a guild.
        - integer → ``channel`` behaves like a ``discord.Thread`` with
          ``parent_id`` set — exercises the thread-collapses-to-parent
          identity path.
    ``guild_id=None`` makes ``message.guild is None``, i.e. a DM.
    """
    author = MagicMock()
    author.id = author_id
    author.display_name = author_name
    author.name = author_name
    author.bot = author_bot

    channel = MagicMock()
    channel.id = channel_id
    if thread_parent_id is not None:
        channel.parent_id = thread_parent_id
    else:
        # Plain guild channel has no parent_id attribute in discord.py.
        # ``getattr(..., "parent_id", None)`` is how our code reads it,
        # so we deliberately leave this slot empty by using a fresh
        # MagicMock that answers ``None`` to that attribute. The cleanest
        # way is a SimpleNamespace-ish explicit None.
        channel.parent_id = None

    guild = None
    if guild_id is not None:
        guild = MagicMock()
        guild.id = guild_id

    message = MagicMock()
    message.id = 9_999
    message.author = author
    message.channel = channel
    message.guild = guild
    message.content = content
    message.attachments = attachments or []
    return message


class TestIdentityConstruction:
    def test_dm_emits_discord_user_prefix(self) -> None:
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        msg = _make_mock_message(
            author_id=42, author_name="Alice",
            channel_id=9000, guild_id=None,
        )
        identity = c._make_identity(msg)  # noqa: SLF001

        assert identity.external_id == "discord:user:42"
        assert identity.is_group is False
        assert identity.display_name == "Alice"
        assert identity.metadata["user_id"] == 42
        assert identity.metadata["channel_id"] == 9000
        assert identity.metadata["parent_channel_id"] == 9000
        assert identity.metadata["guild_id"] is None
        assert identity.metadata["thread_id"] is None

    def test_guild_channel_emits_discord_channel_prefix(self) -> None:
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        msg = _make_mock_message(
            channel_id=500, guild_id=1_000,
        )
        identity = c._make_identity(msg)  # noqa: SLF001

        assert identity.external_id == "discord:channel:500"
        assert identity.is_group is True
        assert identity.metadata["guild_id"] == 1_000
        assert identity.metadata["thread_id"] is None

    def test_thread_collapses_to_parent_channel(self) -> None:
        """A thread message's session is the parent channel's — matches
        Slack's channel-scoped model. The reply channel stays the thread
        so the bot's response lands in-thread."""
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        msg = _make_mock_message(
            channel_id=555,               # the thread itself
            thread_parent_id=500,         # its parent text channel
            guild_id=1_000,
        )
        identity = c._make_identity(msg)  # noqa: SLF001

        # External id keys on the PARENT — session spans parent + threads.
        assert identity.external_id == "discord:channel:500"
        # Metadata carries both so outbound replies go back to the thread.
        assert identity.metadata["channel_id"] == 555
        assert identity.metadata["parent_channel_id"] == 500
        assert identity.metadata["thread_id"] == 555

    def test_display_name_falls_back_to_user_id(self) -> None:
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        # Author whose display_name AND name are None-ish.
        author = MagicMock()
        author.id = 123
        author.display_name = None
        author.name = None
        author.bot = False
        channel = MagicMock()
        channel.id = 1
        channel.parent_id = None
        msg = MagicMock()
        msg.id = 1
        msg.author = author
        msg.channel = channel
        msg.guild = None
        msg.content = ""
        msg.attachments = []

        identity = c._make_identity(msg)  # noqa: SLF001
        assert identity.display_name == "123"


# ---------------------------------------------------------------------------
# Inbound filtering
# ---------------------------------------------------------------------------


class TestInboundFiltering:
    async def test_bot_own_echo_dropped(self) -> None:
        """If ``message.author.id`` matches ``client.user.id`` the
        message is the bot talking to itself — filter at the source."""
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        fake_client = MagicMock()
        fake_client.user = MagicMock()
        fake_client.user.id = 999
        c._client = fake_client  # noqa: SLF001

        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)

        c.set_message_handler(handler)
        msg = _make_mock_message(author_id=999)
        await c._on_discord_message(msg)  # noqa: SLF001
        assert received == []

    async def test_other_bot_messages_dropped(self) -> None:
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        c._client = MagicMock()  # noqa: SLF001
        c._client.user.id = 1  # noqa: SLF001
        received: list[MessageEvent] = []
        c.set_message_handler(
            lambda e: received.append(e) or asyncio.sleep(0),
        )

        msg = _make_mock_message(author_id=2, author_bot=True)
        await c._on_discord_message(msg)  # noqa: SLF001
        assert received == []

    async def test_no_handler_registered_drops_silently(self) -> None:
        """Defence in depth: ``_on_message`` is None between instance
        creation and ConnectorManager registration."""
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        c._client = MagicMock()  # noqa: SLF001
        c._client.user.id = 1  # noqa: SLF001
        msg = _make_mock_message(author_id=2)
        # Should not raise.
        await c._on_discord_message(msg)  # noqa: SLF001

    async def test_happy_path_text_reaches_handler(self) -> None:
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        c._client = MagicMock()  # noqa: SLF001
        c._client.user.id = 1  # noqa: SLF001

        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)

        c.set_message_handler(handler)
        msg = _make_mock_message(
            author_id=2, author_name="Alice",
            content="hello tank",
            channel_id=500, guild_id=1_000,
        )
        await c._on_discord_message(msg)  # noqa: SLF001

        assert len(received) == 1
        event = received[0]
        assert event.text == "hello tank"
        assert event.identity.external_id == "discord:channel:500"
        assert event.identity.display_name == "Alice"

    async def test_handler_exception_does_not_crash_gateway(self) -> None:
        """If the downstream ``_on_message`` raises, log it but don't
        let it propagate — the exception would otherwise kill the
        gateway task."""
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        c._client = MagicMock()  # noqa: SLF001
        c._client.user.id = 1  # noqa: SLF001

        async def handler(event: MessageEvent) -> None:  # noqa: ARG001
            raise RuntimeError("synthetic")

        c.set_message_handler(handler)
        msg = _make_mock_message(author_id=2)
        # Must NOT raise.
        await c._on_discord_message(msg)  # noqa: SLF001


# ---------------------------------------------------------------------------
# Inbound images
# ---------------------------------------------------------------------------


def _mock_disc_attachment(
    *, content_type: str = "image/png", size: int = 1024,
    data: bytes = b"\x89PNG_fake", filename: str = "cat.png",
):
    att = MagicMock(spec=discord.Attachment)
    att.content_type = content_type
    att.size = size
    att.filename = filename
    att.read = AsyncMock(return_value=data)
    return att


class TestInboundImages:
    async def test_image_attachment_becomes_attachment_block(self) -> None:
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        c._client = MagicMock()  # noqa: SLF001
        c._client.user.id = 1  # noqa: SLF001

        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)

        c.set_message_handler(handler)

        att = _mock_disc_attachment(content_type="image/png", data=b"\x89PNG...")
        msg = _make_mock_message(author_id=2, content="look", attachments=[att])
        await c._on_discord_message(msg)  # noqa: SLF001

        assert len(received) == 1
        event = received[0]
        assert len(event.attachments) == 1
        out = event.attachments[0]
        assert out.kind == "image"
        assert out.data == b"\x89PNG..."
        assert out.mime_type == "image/png"

    async def test_non_image_attachment_dropped(self) -> None:
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        c._client = MagicMock()  # noqa: SLF001
        c._client.user.id = 1  # noqa: SLF001

        received: list[MessageEvent] = []
        c.set_message_handler(
            lambda e: received.append(e) or asyncio.sleep(0),
        )

        att = _mock_disc_attachment(
            content_type="application/pdf", filename="doc.pdf",
        )
        msg = _make_mock_message(author_id=2, attachments=[att])
        await c._on_discord_message(msg)  # noqa: SLF001

        # Message still forwarded (it might carry text), but the
        # non-image attachment is stripped.
        assert len(received) == 1
        assert received[0].attachments == ()

    async def test_oversized_image_skipped_by_declared_size(self) -> None:
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        c._client = MagicMock()  # noqa: SLF001
        c._client.user.id = 1  # noqa: SLF001

        received: list[MessageEvent] = []
        c.set_message_handler(
            lambda e: received.append(e) or asyncio.sleep(0),
        )

        att = _mock_disc_attachment(size=30 * 1024 * 1024)
        msg = _make_mock_message(author_id=2, attachments=[att])
        await c._on_discord_message(msg)  # noqa: SLF001

        assert received[0].attachments == ()
        # read() never even called — cap checked before.
        att.read.assert_not_awaited()

    async def test_attachment_read_failure_skips_that_one(self) -> None:
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        c._client = MagicMock()  # noqa: SLF001
        c._client.user.id = 1  # noqa: SLF001

        received: list[MessageEvent] = []
        c.set_message_handler(
            lambda e: received.append(e) or asyncio.sleep(0),
        )

        bad = _mock_disc_attachment(filename="bad.png")
        bad.read = AsyncMock(side_effect=RuntimeError("net"))
        good = _mock_disc_attachment(
            data=b"GOOD", filename="good.png",
        )
        msg = _make_mock_message(author_id=2, attachments=[bad, good])
        await c._on_discord_message(msg)  # noqa: SLF001

        # Good image survives, bad one skipped.
        assert len(received[0].attachments) == 1
        assert received[0].attachments[0].data == b"GOOD"


class TestInboundAudio:
    """Phase 14: voice-in. Discord's native voice-message feature
    (2023+) uploads Opus-in-OGG attachments; generic audio file uploads
    arrive as ``audio/*`` MIMEs. Both route through the same
    ``_download_attachment`` path as images, then the manager's
    :meth:`_audio_to_text_block` dispatches to the ffmpeg-sniffing
    :func:`decode_any_audio` for non-OGG MIMEs."""

    @pytest.mark.parametrize(
        "mime",
        [
            "audio/ogg",     # Discord native voice messages
            "audio/webm",    # WebM/Opus file uploads
            "audio/mp4",     # iOS/macOS recordings
            "audio/mpeg",    # Plain MP3 uploads
            "audio/wav",     # WAV uploads (rare but possible)
        ],
    )
    async def test_audio_attachment_becomes_audio_block(
        self, mime: str,
    ) -> None:
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        c._client = MagicMock()  # noqa: SLF001
        c._client.user.id = 1  # noqa: SLF001

        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)

        c.set_message_handler(handler)

        att = _mock_disc_attachment(
            content_type=mime, data=b"\x00" * 2048, filename="voice.ogg",
        )
        msg = _make_mock_message(author_id=2, content="", attachments=[att])
        await c._on_discord_message(msg)  # noqa: SLF001

        assert len(received) == 1
        event = received[0]
        assert len(event.attachments) == 1
        out = event.attachments[0]
        assert out.kind == "audio"
        assert out.mime_type == mime
        assert out.data == b"\x00" * 2048

    async def test_unsupported_attachment_dropped_silently(self) -> None:
        """Post-Phase-14, anything neither ``image/*`` nor ``audio/*``
        is still dropped — video, zips, plain-text docs, etc. The
        message itself still forwards (it may carry text); only the
        attachment is stripped."""
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        c._client = MagicMock()  # noqa: SLF001
        c._client.user.id = 1  # noqa: SLF001

        received: list[MessageEvent] = []
        c.set_message_handler(
            lambda e: received.append(e) or asyncio.sleep(0),
        )

        att = _mock_disc_attachment(
            content_type="video/mp4", filename="clip.mp4",
        )
        msg = _make_mock_message(
            author_id=2, content="check this", attachments=[att],
        )
        await c._on_discord_message(msg)  # noqa: SLF001

        assert len(received) == 1
        assert received[0].text == "check this"
        assert received[0].attachments == ()

    async def test_oversized_audio_skipped_by_declared_size(self) -> None:
        """25 MiB audio cap matches the image cap; declared size > cap
        short-circuits before ``attachment.read()`` is even awaited."""
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        c._client = MagicMock()  # noqa: SLF001
        c._client.user.id = 1  # noqa: SLF001

        received: list[MessageEvent] = []
        c.set_message_handler(
            lambda e: received.append(e) or asyncio.sleep(0),
        )

        att = _mock_disc_attachment(
            content_type="audio/webm", size=30 * 1024 * 1024,
            filename="big.webm",
        )
        msg = _make_mock_message(author_id=2, attachments=[att])
        await c._on_discord_message(msg)  # noqa: SLF001

        assert received[0].attachments == ()
        # read() never called — size cap is the early gate.
        att.read.assert_not_awaited()

    async def test_mixed_image_and_audio_both_forwarded(self) -> None:
        """A Discord message carrying both an image and a voice note
        (rare but possible — user replies with a photo + a recording)
        should forward both attachments."""
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        c._client = MagicMock()  # noqa: SLF001
        c._client.user.id = 1  # noqa: SLF001

        received: list[MessageEvent] = []
        c.set_message_handler(
            lambda e: received.append(e) or asyncio.sleep(0),
        )

        img = _mock_disc_attachment(
            content_type="image/png", data=b"\x89PNG", filename="a.png",
        )
        voice = _mock_disc_attachment(
            content_type="audio/ogg", data=b"OggS_hdr", filename="v.ogg",
        )
        msg = _make_mock_message(author_id=2, attachments=[img, voice])
        await c._on_discord_message(msg)  # noqa: SLF001

        kinds = [a.kind for a in received[0].attachments]
        assert kinds == ["image", "audio"]


# ---------------------------------------------------------------------------
# Outbound — send text
# ---------------------------------------------------------------------------


def _identity(
    *,
    channel_id: int = 500,
    external_id: str | None = None,
    user_id: int = 100,
) -> Identity:
    return Identity(
        platform="discord",
        external_id=external_id or f"discord:channel:{channel_id}",
        metadata={
            "user_id": user_id,
            "channel_id": channel_id,
            "parent_channel_id": channel_id,
        },
    )


@pytest.fixture()
def started_connector():
    """A DiscordConnector with ``_client`` patched to a mock, bypassing
    the gateway lifecycle — lets outbound tests inject arbitrary
    channels without real discord.py machinery."""
    c = DiscordConnector(instance_name="t", bot_token="xxx")
    client = MagicMock()
    client.get_channel = MagicMock(return_value=None)
    client.fetch_channel = AsyncMock()
    client.get_user = MagicMock(return_value=None)
    client.fetch_user = AsyncMock()
    c._client = client  # noqa: SLF001
    c._connected = True  # noqa: SLF001
    return c


class TestSendText:
    async def test_happy_path(self, started_connector) -> None:
        channel = MagicMock()
        channel.id = 500
        channel.send = AsyncMock(return_value=_mock_sent_message(
            channel_id=500, message_id=777,
        ))
        started_connector._client.get_channel = MagicMock(return_value=channel)  # noqa: SLF001

        result = await started_connector.send(_identity(), "hello")

        assert result.ok is True
        assert result.message_id == "500|777"
        kwargs = channel.send.call_args.kwargs
        assert kwargs["content"] == "hello"

    async def test_truncates_at_2000_chars(self, started_connector) -> None:
        channel = MagicMock()
        channel.id = 500
        channel.send = AsyncMock(return_value=_mock_sent_message(
            channel_id=500, message_id=1,
        ))
        started_connector._client.get_channel = MagicMock(return_value=channel)  # noqa: SLF001

        long = "x" * 5000
        await started_connector.send(_identity(), long)

        sent_text = channel.send.call_args.kwargs["content"]
        assert len(sent_text) == 2000
        assert sent_text.endswith("…")

    async def test_rate_limited_classified(self, started_connector) -> None:
        channel = MagicMock()
        channel.send = AsyncMock(side_effect=_http_exception(429, retry_after="5"))
        started_connector._client.get_channel = MagicMock(return_value=channel)  # noqa: SLF001

        result = await started_connector.send(_identity(), "hello")
        assert result.ok is False
        assert result.error == "rate_limited:5"

    async def test_forbidden_classified(self, started_connector) -> None:
        channel = MagicMock()
        channel.send = AsyncMock(side_effect=_http_exception(403))
        started_connector._client.get_channel = MagicMock(return_value=channel)  # noqa: SLF001

        result = await started_connector.send(_identity(), "hello")
        assert result.ok is False
        assert result.error is not None
        assert "forbidden" in result.error

    async def test_not_connected_returns_error(self) -> None:
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        result = await c.send(_identity(), "hello")
        assert result.ok is False
        assert result.error == "not connected"

    async def test_missing_channel_in_metadata_returns_bad_identity(
        self, started_connector,
    ) -> None:
        bad = Identity(
            platform="discord",
            external_id="discord:channel:500",
            metadata={},  # no channel_id
        )
        result = await started_connector.send(bad, "hello")
        assert result.ok is False
        assert result.error is not None
        assert "bad_identity" in result.error

    async def test_channel_cache_miss_falls_back_to_fetch(
        self, started_connector,
    ) -> None:
        channel = MagicMock()
        channel.id = 500
        channel.send = AsyncMock(return_value=_mock_sent_message(
            channel_id=500, message_id=1,
        ))
        started_connector._client.get_channel = MagicMock(return_value=None)  # noqa: SLF001
        started_connector._client.fetch_channel = AsyncMock(return_value=channel)  # noqa: SLF001

        result = await started_connector.send(_identity(), "hello")
        assert result.ok is True
        started_connector._client.fetch_channel.assert_awaited_once_with(500)  # noqa: SLF001


# ---------------------------------------------------------------------------
# Outbound — send image
# ---------------------------------------------------------------------------


class TestSendImage:
    async def test_bytes_image_uses_discord_file(self, started_connector) -> None:
        channel = MagicMock()
        channel.send = AsyncMock(return_value=_mock_sent_message(
            channel_id=500, message_id=1,
        ))
        started_connector._client.get_channel = MagicMock(return_value=channel)  # noqa: SLF001

        att = Attachment(
            kind="image", data=b"\x89PNG...", mime_type="image/png",
            filename="cat.png",
        )
        result = await started_connector.send(
            _identity(), "see this", attachments=(att,),
        )

        assert result.ok is True
        # No edit-addressable message_id for image sends.
        assert result.message_id is None
        kwargs = channel.send.call_args.kwargs
        assert kwargs["content"] == "see this"
        file = kwargs["file"]
        assert isinstance(file, discord.File)

    async def test_empty_payload_rejected(self, started_connector) -> None:
        channel = MagicMock()
        channel.send = AsyncMock()
        started_connector._client.get_channel = MagicMock(return_value=channel)  # noqa: SLF001
        att = Attachment(kind="image", data=b"", mime_type="image/png")
        result = await started_connector.send(
            _identity(), "", attachments=(att,),
        )
        assert result.ok is False
        assert result.error == "empty_payload"
        channel.send.assert_not_awaited()

    async def test_caption_truncated(self, started_connector) -> None:
        channel = MagicMock()
        channel.send = AsyncMock(return_value=_mock_sent_message(
            channel_id=500, message_id=1,
        ))
        started_connector._client.get_channel = MagicMock(return_value=channel)  # noqa: SLF001

        long = "c" * 5000
        att = Attachment(kind="image", data=b"\x89PNG", mime_type="image/png")
        await started_connector.send(_identity(), long, attachments=(att,))

        sent = channel.send.call_args.kwargs["content"]
        assert len(sent) == 2000
        assert sent.endswith("…")


# ---------------------------------------------------------------------------
# Outbound — edit
# ---------------------------------------------------------------------------


class TestEdit:
    async def test_happy_path(self, started_connector) -> None:
        target_msg = MagicMock()
        target_msg.edit = AsyncMock()

        channel = MagicMock()
        channel.fetch_message = AsyncMock(return_value=target_msg)
        started_connector._client.get_channel = MagicMock(return_value=channel)  # noqa: SLF001

        result = await started_connector.edit(
            _identity(), "500|777", "edited text",
        )

        assert result.ok is True
        assert result.message_id == "500|777"
        channel.fetch_message.assert_awaited_once_with(777)
        target_msg.edit.assert_awaited_once()
        assert target_msg.edit.call_args.kwargs["content"] == "edited text"

    async def test_bad_message_id_rejected(self, started_connector) -> None:
        started_connector._client.get_channel = MagicMock()  # noqa: SLF001
        result = await started_connector.edit(
            _identity(), "not-a-composite", "text",
        )
        assert result.ok is False
        assert result.error is not None
        assert "bad_message_id" in result.error
        started_connector._client.get_channel.assert_not_called()  # noqa: SLF001

    async def test_rate_limited_classified(self, started_connector) -> None:
        target_msg = MagicMock()
        target_msg.edit = AsyncMock(side_effect=_http_exception(429, retry_after="7"))
        channel = MagicMock()
        channel.fetch_message = AsyncMock(return_value=target_msg)
        started_connector._client.get_channel = MagicMock(return_value=channel)  # noqa: SLF001

        result = await started_connector.edit(
            _identity(), "500|777", "text",
        )
        assert result.ok is False
        assert result.error == "rate_limited:7"

    async def test_not_connected_returns_error(self) -> None:
        c = DiscordConnector(instance_name="t", bot_token="xxx")
        result = await c.edit(_identity(), "500|777", "text")
        assert result.ok is False
        assert result.error == "not connected"

    async def test_channel_not_found_returns_error(
        self, started_connector,
    ) -> None:
        started_connector._client.get_channel = MagicMock(return_value=None)  # noqa: SLF001
        started_connector._client.fetch_channel = AsyncMock(return_value=None)  # noqa: SLF001

        result = await started_connector.edit(
            _identity(), "500|777", "text",
        )
        assert result.ok is False
        assert result.error is not None
        assert "channel_not_found" in result.error


# ---------------------------------------------------------------------------
# Typing indicator
# ---------------------------------------------------------------------------


class TestSendTyping:
    async def test_send_typing_uses_channel_typing_context(
        self, started_connector,
    ) -> None:
        """``channel.typing()`` is an async context manager; we enter
        and exit it once to pulse the indicator."""
        channel = MagicMock()
        # channel.typing() returns an async context manager.
        typing_ctx = AsyncMock()
        typing_ctx.__aenter__ = AsyncMock(return_value=None)
        typing_ctx.__aexit__ = AsyncMock(return_value=None)
        channel.typing = MagicMock(return_value=typing_ctx)
        started_connector._client.get_channel = MagicMock(return_value=channel)  # noqa: SLF001

        await started_connector.send_typing(_identity())

        channel.typing.assert_called_once()
        typing_ctx.__aenter__.assert_awaited_once()
        typing_ctx.__aexit__.assert_awaited_once()

    async def test_send_typing_swallows_http_errors(
        self, started_connector,
    ) -> None:
        channel = MagicMock()
        channel.typing = MagicMock(side_effect=_http_exception(500))
        started_connector._client.get_channel = MagicMock(return_value=channel)  # noqa: SLF001

        # Must not raise — typing is advisory, never fatal.
        await started_connector.send_typing(_identity())


# ---------------------------------------------------------------------------
# Test helpers (module-private)
# ---------------------------------------------------------------------------


def _mock_sent_message(*, channel_id: int, message_id: int) -> MagicMock:
    """MagicMock that looks like a ``discord.Message`` returned by
    ``channel.send``."""
    m = MagicMock()
    m.id = message_id
    m.channel = MagicMock()
    m.channel.id = channel_id
    return m


def _http_exception(status: int, *, retry_after: str | None = None) -> discord.HTTPException:
    """Construct a realistic-enough ``discord.HTTPException`` for testing
    the classifier. discord.py requires a ``response`` object with
    ``.status`` + ``.headers`` and an arbitrary message payload."""
    response = MagicMock()
    response.status = status
    headers: dict[str, str] = {}
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    response.headers = headers
    response.reason = "test"
    # HTTPException accepts the response + an error dict-or-string.
    exc = discord.HTTPException(response, {"code": 0, "message": "synthetic"})
    # Sanity: discord.py copies status onto the exception itself.
    exc.status = status
    return exc


# ---------------------------------------------------------------------------
# Phase 10 — Approval buttons (send_approval_prompt + _on_approval_interaction)
# ---------------------------------------------------------------------------


class TestApprovalPrompt:
    """``send_approval_prompt`` DMs the admin with three button
    components whose ``custom_id`` fields encode choice + approval_id.
    Discord routes clicks through :meth:`_TankDiscordClient.on_interaction`,
    which calls ``_on_approval_interaction`` below."""

    async def test_sends_dm_with_three_buttons_and_expected_custom_ids(
        self, started_connector,
    ) -> None:
        # Admin user DM resolution: get_user returns a cached user whose
        # ``create_dm`` yields a mock channel we can inspect.
        admin_user = MagicMock()
        channel = MagicMock()
        channel.send = AsyncMock()
        admin_user.create_dm = AsyncMock(return_value=channel)
        started_connector._client.get_user = MagicMock(  # noqa: SLF001
            return_value=admin_user,
        )

        admin = Identity(
            platform="discord",
            external_id="discord:user:42",
            metadata={"user_id": 42},
        )
        sender = Identity(
            platform="discord",
            external_id="discord:user:99",
            display_name="Alice",
            metadata={"user_id": 99},
        )

        await started_connector.send_approval_prompt(
            admin_identity=admin,
            approval_id="abc1234567890def",
            sender=sender,
            preview="hello tank",
        )

        channel.send.assert_awaited_once()
        kwargs = channel.send.call_args.kwargs
        # Prompt text mentions sender + identity + preview.
        content = kwargs["content"]
        assert "Alice" in content
        assert "discord:user:99" in content
        assert "hello tank" in content

        # Three buttons on the attached View, each carrying the expected
        # ``approve:<choice>:<approval_id>`` custom_id.
        view = kwargs["view"]
        buttons = [child for child in view.children
                   if isinstance(child, discord.ui.Button)]
        assert len(buttons) == 3
        custom_ids = sorted(b.custom_id for b in buttons)
        assert custom_ids == [
            "approve:allow_forever:abc1234567890def",
            "approve:allow_once:abc1234567890def",
            "approve:deny:abc1234567890def",
        ]

    async def test_falls_back_to_fetch_user_when_cache_misses(
        self, started_connector,
    ) -> None:
        """``get_user`` hits the gateway cache; for users the bot hasn't
        seen this session, ``fetch_user`` does the HTTP lookup. Both
        paths should land on the same DM-send flow."""
        started_connector._client.get_user = MagicMock(return_value=None)  # noqa: SLF001
        admin_user = MagicMock()
        channel = MagicMock()
        channel.send = AsyncMock()
        admin_user.create_dm = AsyncMock(return_value=channel)
        started_connector._client.fetch_user = AsyncMock(  # noqa: SLF001
            return_value=admin_user,
        )

        admin = Identity(
            platform="discord",
            external_id="discord:user:42",
            metadata={"user_id": 42},
        )
        await started_connector.send_approval_prompt(
            admin_identity=admin,
            approval_id="abc",
            sender=_identity(user_id=99),
            preview="x",
        )

        started_connector._client.fetch_user.assert_awaited_once_with(42)  # noqa: SLF001
        channel.send.assert_awaited_once()

    async def test_derives_user_id_from_external_id_when_metadata_missing(
        self, started_connector,
    ) -> None:
        """Defensive: if the admin Identity lacks ``metadata["user_id"]``
        we parse the trailing int from ``discord:user:<id>`` so we can
        still find the admin."""
        admin_user = MagicMock()
        channel = MagicMock()
        channel.send = AsyncMock()
        admin_user.create_dm = AsyncMock(return_value=channel)
        started_connector._client.get_user = MagicMock(  # noqa: SLF001
            return_value=admin_user,
        )

        admin = Identity(
            platform="discord",
            external_id="discord:user:42",
            metadata={},  # no user_id
        )
        await started_connector.send_approval_prompt(
            admin_identity=admin,
            approval_id="abc",
            sender=_identity(user_id=99),
            preview="x",
        )

        started_connector._client.get_user.assert_called_with(42)  # noqa: SLF001

    async def test_unresolvable_admin_is_silent_noop(
        self, started_connector,
    ) -> None:
        """If we can't parse the admin user id out of the Identity, we
        bail without trying to send. The broker's 24h TTL will eventually
        clean up the orphaned pending entry."""
        started_connector._client.get_user = MagicMock()  # noqa: SLF001
        bad = Identity(platform="discord", external_id="garbage")
        await started_connector.send_approval_prompt(
            admin_identity=bad,
            approval_id="abc",
            sender=_identity(user_id=99),
            preview="x",
        )
        started_connector._client.get_user.assert_not_called()  # noqa: SLF001

    async def test_admin_not_found_is_logged_not_raised(
        self, started_connector,
    ) -> None:
        """If both the cache and fetch_user return None (e.g. admin left
        the server), we log and move on — no crash."""
        started_connector._client.get_user = MagicMock(return_value=None)  # noqa: SLF001
        started_connector._client.fetch_user = AsyncMock(  # noqa: SLF001
            return_value=None,
        )
        admin = Identity(
            platform="discord",
            external_id="discord:user:42",
            metadata={"user_id": 42},
        )
        # Must not raise.
        await started_connector.send_approval_prompt(
            admin_identity=admin,
            approval_id="abc",
            sender=_identity(user_id=99),
            preview="x",
        )


class TestApprovalInteraction:
    """Button clicks arrive as :class:`discord.Interaction` objects.
    ``_on_approval_interaction`` must defer (Discord's 3-second ack
    window) and then route the click to the broker."""

    @staticmethod
    def _mock_interaction(
        *, custom_id: str, user_id: int = 42, user_name: str = "Admin",
    ):
        interaction = MagicMock()
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": custom_id}
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        user = MagicMock()
        user.id = user_id
        user.display_name = user_name
        user.name = user_name
        interaction.user = user
        # The prompt-edit path reads ``interaction.message`` and calls
        # ``message.edit(content=..., view=None)``; making the latter an
        # AsyncMock by default covers both resolved-happy-path tests and
        # tests that explicitly null out ``interaction.message``.
        interaction.message = MagicMock()
        interaction.message.edit = AsyncMock()
        return interaction

    @staticmethod
    def _make_pending(sender_id: int = 99) -> MagicMock:
        """A ``PendingApproval``-shaped mock the broker's ``resolve``
        returns on success — the click handler reads
        ``resolved.event.identity`` to build the outcome text."""
        pending = MagicMock()
        pending.event.identity = Identity(
            platform="discord",
            external_id=f"discord:user:{sender_id}",
            display_name="Alice",
            is_group=False,
            metadata={"user_id": sender_id},
        )
        return pending

    async def test_ack_and_dispatch_to_broker(
        self, started_connector,
    ) -> None:
        broker = MagicMock()
        broker.resolve = AsyncMock(return_value=self._make_pending(99))
        started_connector.set_approval_broker(broker)

        interaction = self._mock_interaction(
            custom_id="approve:allow_forever:abc1234567890def",
        )
        await started_connector._on_approval_interaction(  # noqa: SLF001
            interaction, "approve:allow_forever:abc1234567890def",
        )

        # Defer fires first so Discord doesn't show "interaction failed".
        interaction.response.defer.assert_awaited_once()
        # Broker is handed (approval_id, choice, clicker_identity).
        broker.resolve.assert_awaited_once()
        args = broker.resolve.call_args.args
        assert args[0] == "abc1234567890def"
        assert args[1] == "allow_forever"
        clicker = args[2]
        assert clicker.platform == "discord"
        assert clicker.external_id == "discord:user:42"
        assert clicker.metadata["user_id"] == 42
        # Prompt was edited — ``view=None`` drops the three buttons;
        # ``content`` is the outcome line referencing sender + admin.
        interaction.message.edit.assert_awaited_once()
        kwargs = interaction.message.edit.call_args.kwargs
        assert kwargs["view"] is None
        assert "Approved forever" in kwargs["content"]
        assert "Alice" in kwargs["content"]
        assert "Admin" in kwargs["content"]

    async def test_stale_resolve_does_not_edit_prompt(
        self, started_connector,
    ) -> None:
        """Broker returns ``None`` for stale or non-admin clicks — the
        handler must leave the prompt alone so a real admin can still
        act on it."""
        broker = MagicMock()
        broker.resolve = AsyncMock(return_value=None)
        started_connector.set_approval_broker(broker)

        interaction = self._mock_interaction(
            custom_id="approve:deny:abc1234567890def",
        )
        await started_connector._on_approval_interaction(  # noqa: SLF001
            interaction, "approve:deny:abc1234567890def",
        )
        broker.resolve.assert_awaited_once()
        interaction.message.edit.assert_not_awaited()

    async def test_missing_interaction_message_skips_edit(
        self, started_connector,
    ) -> None:
        """If ``interaction.message`` is ``None`` (e.g. ephemeral
        response), the broker still resolves, but the edit is skipped
        silently — nothing to edit."""
        broker = MagicMock()
        broker.resolve = AsyncMock(return_value=self._make_pending(99))
        started_connector.set_approval_broker(broker)

        interaction = self._mock_interaction(
            custom_id="approve:allow_once:abc1234567890def",
        )
        interaction.message = None

        # Must not raise.
        await started_connector._on_approval_interaction(  # noqa: SLF001
            interaction, "approve:allow_once:abc1234567890def",
        )
        broker.resolve.assert_awaited_once()

    async def test_edit_http_exception_is_swallowed(
        self, started_connector,
    ) -> None:
        """Prompt-edit failures (message too old, missing perms, etc.)
        shouldn't propagate — the broker's real work already landed."""
        broker = MagicMock()
        broker.resolve = AsyncMock(return_value=self._make_pending(99))
        started_connector.set_approval_broker(broker)

        interaction = self._mock_interaction(
            custom_id="approve:allow_once:abc1234567890def",
        )
        interaction.message.edit = AsyncMock(
            side_effect=_http_exception(404),
        )

        # Must not raise.
        await started_connector._on_approval_interaction(  # noqa: SLF001
            interaction, "approve:allow_once:abc1234567890def",
        )
        interaction.message.edit.assert_awaited_once()

    async def test_no_broker_attached_silently_defers(
        self, started_connector,
    ) -> None:
        """Arriving click with no broker attached — possible during a
        restart window — still acks so Discord's UI doesn't spin."""
        # Ensure no broker.
        if hasattr(started_connector, "_broker"):
            delattr(started_connector, "_broker")

        interaction = self._mock_interaction(
            custom_id="approve:allow_once:abc",
        )
        await started_connector._on_approval_interaction(  # noqa: SLF001
            interaction, "approve:allow_once:abc",
        )
        interaction.response.defer.assert_awaited_once()

    async def test_malformed_custom_id_is_noop(
        self, started_connector,
    ) -> None:
        """Guard against mis-parsed prefixes — e.g. a truncated custom_id.
        The method still defers (UX contract) but doesn't call the
        broker."""
        broker = MagicMock()
        broker.resolve = AsyncMock()
        started_connector.set_approval_broker(broker)

        interaction = self._mock_interaction(
            custom_id="approve:only-two-parts",
        )
        await started_connector._on_approval_interaction(  # noqa: SLF001
            interaction, "approve:only-two-parts",
        )
        broker.resolve.assert_not_awaited()

    async def test_empty_approval_id_is_noop(
        self, started_connector,
    ) -> None:
        """Empty approval_id after the prefix — defensive against
        ``approve:allow_once:``."""
        broker = MagicMock()
        broker.resolve = AsyncMock()
        started_connector.set_approval_broker(broker)

        interaction = self._mock_interaction(
            custom_id="approve:allow_once:",
        )
        await started_connector._on_approval_interaction(  # noqa: SLF001
            interaction, "approve:allow_once:",
        )
        broker.resolve.assert_not_awaited()

    async def test_missing_user_on_interaction_is_noop(
        self, started_connector,
    ) -> None:
        """Discord's SDK guarantees ``interaction.user`` for component
        interactions but we code defensively."""
        broker = MagicMock()
        broker.resolve = AsyncMock()
        started_connector.set_approval_broker(broker)

        interaction = self._mock_interaction(
            custom_id="approve:allow_once:abc",
        )
        interaction.user = None

        await started_connector._on_approval_interaction(  # noqa: SLF001
            interaction, "approve:allow_once:abc",
        )
        broker.resolve.assert_not_awaited()

    async def test_defer_failure_still_dispatches_to_broker(
        self, started_connector,
    ) -> None:
        """If the 3-second ack window slips (network blip, Discord lag),
        the deferred call raises an :class:`discord.HTTPException`. We
        swallow the ack error and still dispatch to the broker — the
        user's click shouldn't be lost because the spinner got unlucky."""
        broker = MagicMock()
        broker.resolve = AsyncMock()
        started_connector.set_approval_broker(broker)

        interaction = self._mock_interaction(
            custom_id="approve:allow_forever:abc1234567890def",
        )
        interaction.response.defer = AsyncMock(
            side_effect=_http_exception(404),
        )

        await started_connector._on_approval_interaction(  # noqa: SLF001
            interaction, "approve:allow_forever:abc1234567890def",
        )
        broker.resolve.assert_awaited_once()

    async def test_broker_resolve_raising_is_logged_not_raised(
        self, started_connector,
    ) -> None:
        """Broker bugs shouldn't propagate up through the gateway
        dispatcher — discord.py would log and drop, but we want
        explicit containment with a clear log at our layer."""
        broker = MagicMock()
        broker.resolve = AsyncMock(side_effect=RuntimeError("synthetic"))
        started_connector.set_approval_broker(broker)

        interaction = self._mock_interaction(
            custom_id="approve:allow_once:abc",
        )
        # Must not raise.
        await started_connector._on_approval_interaction(  # noqa: SLF001
            interaction, "approve:allow_once:abc",
        )


class TestClientInteractionDispatch:
    """``_TankDiscordClient.on_interaction`` is the gateway-level hook
    that filters by ``custom_id`` prefix before routing to
    ``_on_approval_interaction``. Non-approval interactions must pass
    through (or be dropped) without touching the connector's approval
    path — otherwise future UI additions would conflict."""

    async def test_non_component_interactions_skip_approval_path(
        self, started_connector,
    ) -> None:
        """Slash commands, application commands, etc. have type != component."""
        from connector_discord.connector import _TankDiscordClient

        # Construct a client directly so we can call on_interaction in
        # isolation — the fixture's _client is a MagicMock, not a real
        # _TankDiscordClient.
        client = _TankDiscordClient.__new__(_TankDiscordClient)
        client._connector = started_connector  # noqa: SLF001
        started_connector._on_approval_interaction = AsyncMock()  # noqa: SLF001

        interaction = MagicMock()
        interaction.type = discord.InteractionType.application_command
        interaction.data = {"custom_id": "approve:allow_once:abc"}

        await client.on_interaction(interaction)
        started_connector._on_approval_interaction.assert_not_awaited()  # noqa: SLF001

    async def test_non_approval_custom_id_skips_approval_path(
        self, started_connector,
    ) -> None:
        """Component interactions whose ``custom_id`` is not an
        ``approve:`` click fall through — e.g. if a future phase adds
        settings toggles via buttons."""
        from connector_discord.connector import _TankDiscordClient

        client = _TankDiscordClient.__new__(_TankDiscordClient)
        client._connector = started_connector  # noqa: SLF001
        started_connector._on_approval_interaction = AsyncMock()  # noqa: SLF001

        interaction = MagicMock()
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "settings:theme:dark"}

        await client.on_interaction(interaction)
        started_connector._on_approval_interaction.assert_not_awaited()  # noqa: SLF001

    async def test_approval_prefix_routes_to_connector_handler(
        self, started_connector,
    ) -> None:
        from connector_discord.connector import _TankDiscordClient

        client = _TankDiscordClient.__new__(_TankDiscordClient)
        client._connector = started_connector  # noqa: SLF001
        started_connector._on_approval_interaction = AsyncMock()  # noqa: SLF001

        interaction = MagicMock()
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "approve:deny:xyz"}

        await client.on_interaction(interaction)
        started_connector._on_approval_interaction.assert_awaited_once()  # noqa: SLF001
        args = started_connector._on_approval_interaction.call_args.args  # noqa: SLF001
        assert args[0] is interaction
        assert args[1] == "approve:deny:xyz"
