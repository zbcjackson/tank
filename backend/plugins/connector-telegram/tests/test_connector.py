"""Unit tests for :class:`TelegramConnector` and ``create_connector``.

All tests use mocks — no real aiogram Bot is instantiated, no HTTP calls
fire. The tests cover:

- Factory validation of required config keys
- Capability flags
- Lifecycle (start / stop / double-start / stop before start)
- Inbound text-message translation → ``MessageEvent``
- Outbound send / edit (happy path, rate-limit, not-modified, API errors)
- Typing indicator
- ``external_id`` parsing edge cases
"""

from __future__ import annotations

import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramRetryAfter,
)
from tank_contracts.connector import Attachment, Identity, MessageEvent

from connector_telegram import TelegramConnector, create_connector


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestCreateConnector:
    def test_happy_path(self) -> None:
        c = create_connector({"instance": "my-bot", "config": {"bot_token": "abc123"}})
        assert isinstance(c, TelegramConnector)
        assert c.instance_name == "my-bot"
        assert c.platform == "telegram"
        assert c._token == "abc123"  # noqa: SLF001

    def test_defaults_instance_name_when_missing(self) -> None:
        c = create_connector({"config": {"bot_token": "abc"}})
        assert c.instance_name == "telegram"

    def test_missing_bot_token_raises(self) -> None:
        with pytest.raises(ValueError, match="bot_token"):
            create_connector({"instance": "x", "config": {}})

    def test_empty_bot_token_raises(self) -> None:
        with pytest.raises(ValueError, match="bot_token"):
            create_connector({"instance": "x", "config": {"bot_token": "   "}})

    def test_non_dict_config_raises(self) -> None:
        with pytest.raises(ValueError, match="mapping"):
            create_connector({"instance": "x", "config": "not-a-dict"})

    def test_missing_config_key_raises(self) -> None:
        # config defaults to {}, which then lacks bot_token.
        with pytest.raises(ValueError, match="bot_token"):
            create_connector({"instance": "x"})


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


class TestCapabilities:
    def test_capabilities_match_telegram_reality(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="x")
        caps = c.capabilities
        assert caps.supports_edits is True
        # Telegram edit rate limit is ~1/sec per chat; we use 1100ms to stay safe.
        assert caps.edit_min_interval_ms >= 1000
        # Telegram hard limit on sendMessage text.
        assert caps.max_message_length == 4096
        assert caps.supports_typing_indicator is True
        # Phase-4: photo support in both directions.
        assert caps.supports_images_in is True
        assert caps.supports_images_out is True
        # Phase-5: voice support defaults on (ASR/TTS gated at the
        # manager layer via AppContext; instance flag can opt out).
        assert caps.supports_voice_in is True
        assert caps.supports_voice_out is True

    def test_voice_in_can_be_disabled_per_instance(self) -> None:
        c = TelegramConnector(
            instance_name="t", bot_token="x", voice_in=False,
        )
        assert c.capabilities.supports_voice_in is False
        # Voice-out is independent — still on by default.
        assert c.capabilities.supports_voice_out is True

    def test_voice_out_can_be_disabled_per_instance(self) -> None:
        c = TelegramConnector(
            instance_name="t", bot_token="x", voice_out=False,
        )
        assert c.capabilities.supports_voice_out is False
        assert c.capabilities.supports_voice_in is True


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class _LifecycleMocks:
    """Container for the aiogram primitives we mock during lifecycle tests."""

    def __init__(self) -> None:
        self.bot = MagicMock(name="Bot")
        self.bot.session = MagicMock(name="BotSession")
        self.bot.session.close = AsyncMock(name="Bot.session.close")

        self.dp = MagicMock(name="Dispatcher")
        self.dp.message = MagicMock(name="Dispatcher.message")
        self.dp.message.register = MagicMock(name="Dispatcher.message.register")
        # start_polling returns a coroutine that blocks until stop_polling is called.
        self._stop_event = asyncio.Event()

        async def _fake_start_polling(*_args, **_kwargs) -> None:
            await self._stop_event.wait()

        async def _fake_stop_polling() -> None:
            self._stop_event.set()

        self.dp.start_polling = _fake_start_polling
        self.dp.stop_polling = _fake_stop_polling


@pytest.fixture()
def aiogram_mocks():
    """Patch aiogram Bot + Dispatcher so start/stop can run without network."""
    mocks = _LifecycleMocks()
    with (
        patch(
            "connector_telegram.connector.Bot",
            return_value=mocks.bot,
        ) as bot_cls,
        patch(
            "connector_telegram.connector.Dispatcher",
            return_value=mocks.dp,
        ) as dp_cls,
    ):
        yield SimpleNamespace(mocks=mocks, bot_cls=bot_cls, dp_cls=dp_cls)


class TestLifecycle:
    async def test_start_creates_bot_dispatcher_and_registers_handler(
        self, aiogram_mocks,
    ) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok-xyz")
        await c.start()
        try:
            assert c.connected
            aiogram_mocks.bot_cls.assert_called_once()
            aiogram_mocks.dp_cls.assert_called_once()
            # Phase-5 defaults: photo, voice, and text handlers.
            assert aiogram_mocks.mocks.dp.message.register.call_count == 3
            # Polling task was spawned.
            assert c._task is not None  # noqa: SLF001
            assert not c._task.done()  # noqa: SLF001
        finally:
            await c.stop()

    async def test_voice_in_false_skips_voice_handler(
        self, aiogram_mocks,
    ) -> None:
        c = TelegramConnector(
            instance_name="t", bot_token="tok", voice_in=False,
        )
        await c.start()
        try:
            # Only photo + text — no voice handler when opted out.
            assert aiogram_mocks.mocks.dp.message.register.call_count == 2
        finally:
            await c.stop()

    async def test_stop_closes_bot_session_and_drains_task(
        self, aiogram_mocks,
    ) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        await c.start()
        await c.stop()

        assert not c.connected
        assert c._task is None  # noqa: SLF001
        assert c._bot is None  # noqa: SLF001
        aiogram_mocks.mocks.bot.session.close.assert_awaited()

    async def test_double_start_is_no_op(self, aiogram_mocks) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        await c.start()
        try:
            aiogram_mocks.bot_cls.reset_mock()
            aiogram_mocks.dp_cls.reset_mock()
            await c.start()
            # No second Bot / Dispatcher instantiation.
            aiogram_mocks.bot_cls.assert_not_called()
            aiogram_mocks.dp_cls.assert_not_called()
        finally:
            await c.stop()

    async def test_stop_before_start_is_no_op(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        await c.stop()  # must not raise
        assert not c.connected

    async def test_stop_cancels_hanging_polling_task(self) -> None:
        """If stop_polling somehow doesn't unblock the loop, we fall back to cancel."""
        bot = MagicMock()
        bot.session = MagicMock()
        bot.session.close = AsyncMock()

        dp = MagicMock()
        dp.message = MagicMock()

        never_stops = asyncio.Event()

        async def _fake_start_polling(*_a, **_kw) -> None:
            await never_stops.wait()

        async def _fake_stop_polling() -> None:
            # Intentionally does NOT signal the event — simulates a wedged SDK.
            pass

        dp.start_polling = _fake_start_polling
        dp.stop_polling = _fake_stop_polling

        with (
            patch("connector_telegram.connector.Bot", return_value=bot),
            patch("connector_telegram.connector.Dispatcher", return_value=dp),
            patch("connector_telegram.connector._SHUTDOWN_TIMEOUT_S", 0.1),
        ):
            c = TelegramConnector(instance_name="t", bot_token="tok")
            await c.start()
            await c.stop()

        assert not c.connected


# ---------------------------------------------------------------------------
# Inbound translation
# ---------------------------------------------------------------------------


def _make_mock_message(
    *,
    chat_id: int,
    chat_type: str = "private",
    text: str = "",
    user_full_name: str | None = "Alice",
    user_id: int | None = None,
    reply_to_message_id: int | None = None,
):
    """Build a minimal MagicMock looking like ``aiogram.types.Message``.

    In private chats Telegram guarantees ``chat_id == from_user.id`` —
    the helper mirrors that convention by defaulting ``user_id`` to
    ``chat_id`` when not supplied, so DM tests don't have to pass both.
    """
    chat = MagicMock()
    chat.id = chat_id
    chat.type = chat_type

    from_user = None
    if user_full_name is not None:
        from_user = MagicMock()
        from_user.full_name = user_full_name
        from_user.id = user_id if user_id is not None else chat_id

    reply_to = None
    if reply_to_message_id is not None:
        reply_to = MagicMock()
        reply_to.message_id = reply_to_message_id

    message = MagicMock()
    message.chat = chat
    message.text = text
    message.from_user = from_user
    message.reply_to_message = reply_to
    return message


class TestInboundTranslation:
    async def test_dm_text_becomes_message_event(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)

        c.set_message_handler(handler)

        msg = _make_mock_message(
            chat_id=12345,
            chat_type="private",
            text="hello tank",
            user_full_name="Alice",
        )
        await c._on_text(msg)  # noqa: SLF001

        assert len(received) == 1
        event = received[0]
        assert event.text == "hello tank"
        assert event.identity.platform == "telegram"
        # DMs emit tg:user:* so allowlists can match individual users.
        assert event.identity.external_id == "tg:user:12345"
        assert event.identity.display_name == "Alice"
        assert event.identity.is_group is False
        # Metadata carries both raw ids for audit / cross-referencing.
        assert event.identity.metadata["chat_id"] == 12345
        assert event.identity.metadata["user_id"] == 12345
        assert event.identity.metadata["chat_type"] == "private"

    async def test_group_chat_sets_is_group_true(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)

        c.set_message_handler(handler)

        msg = _make_mock_message(chat_id=-1001234567, chat_type="supergroup")
        await c._on_text(msg)  # noqa: SLF001

        assert received[0].identity.is_group is True
        assert received[0].identity.external_id == "tg:chat:-1001234567"

    async def test_reply_to_message_id_is_stringified(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)

        c.set_message_handler(handler)

        msg = _make_mock_message(chat_id=1, reply_to_message_id=42)
        await c._on_text(msg)  # noqa: SLF001

        assert received[0].reply_to_message_id == "42"

    async def test_no_handler_registered_drops_silently(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        # No set_message_handler() call.
        msg = _make_mock_message(chat_id=1, text="ignored")
        await c._on_text(msg)  # noqa: SLF001 — must not raise

    async def test_handler_exception_is_swallowed(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")

        async def bad_handler(event: MessageEvent) -> None:
            raise RuntimeError("synthetic")

        c.set_message_handler(bad_handler)

        msg = _make_mock_message(chat_id=1, text="hi")
        # Bad handler must NOT take down the polling loop.
        await c._on_text(msg)  # noqa: SLF001

    async def test_missing_user_gives_empty_display_name(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)

        c.set_message_handler(handler)

        msg = _make_mock_message(chat_id=1, user_full_name=None)
        await c._on_text(msg)  # noqa: SLF001

        assert received[0].identity.display_name == ""


# ---------------------------------------------------------------------------
# Outbound send / edit
# ---------------------------------------------------------------------------


@pytest.fixture()
def started_connector():
    """Yield a TelegramConnector with ``_bot`` set to a mock (no real lifecycle)."""
    c = TelegramConnector(instance_name="t", bot_token="tok")
    c._bot = MagicMock()  # noqa: SLF001
    c._connected = True  # noqa: SLF001
    return c


def _identity(chat_id: int = 12345) -> Identity:
    return Identity(platform="telegram", external_id=f"tg:chat:{chat_id}")


class TestSend:
    async def test_happy_path(self, started_connector) -> None:
        sent_message = MagicMock()
        sent_message.message_id = 99
        started_connector._bot.send_message = AsyncMock(return_value=sent_message)  # noqa: SLF001

        result = await started_connector.send(_identity(12345), "hello")

        assert result.ok is True
        assert result.message_id == "99"
        started_connector._bot.send_message.assert_awaited_once()  # noqa: SLF001
        kwargs = started_connector._bot.send_message.call_args.kwargs  # noqa: SLF001
        assert kwargs["chat_id"] == 12345
        assert kwargs["text"] == "hello"
        assert kwargs["reply_to_message_id"] is None

    async def test_reply_to_stringified_int_passes_through(
        self, started_connector,
    ) -> None:
        sent_message = MagicMock()
        sent_message.message_id = 100
        started_connector._bot.send_message = AsyncMock(return_value=sent_message)  # noqa: SLF001

        await started_connector.send(_identity(), "hi", reply_to="42")

        kwargs = started_connector._bot.send_message.call_args.kwargs  # noqa: SLF001
        assert kwargs["reply_to_message_id"] == 42

    async def test_reply_to_non_integer_is_ignored(self, started_connector) -> None:
        sent_message = MagicMock()
        sent_message.message_id = 100
        started_connector._bot.send_message = AsyncMock(return_value=sent_message)  # noqa: SLF001

        result = await started_connector.send(_identity(), "hi", reply_to="not-an-int")

        assert result.ok is True
        kwargs = started_connector._bot.send_message.call_args.kwargs  # noqa: SLF001
        assert kwargs["reply_to_message_id"] is None

    async def test_not_connected_returns_error(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        # No start() — _bot is None.
        result = await c.send(_identity(), "hi")
        assert result.ok is False
        assert result.error == "not connected"

    async def test_bad_identity_returns_error(self, started_connector) -> None:
        result = await started_connector.send(
            Identity(platform="telegram", external_id="garbage"),
            "hi",
        )
        assert result.ok is False
        assert result.error is not None
        assert result.error.startswith("bad_identity")

    async def test_rate_limit_returns_error_with_retry_after(
        self, started_connector,
    ) -> None:
        err = TelegramRetryAfter(
            method=MagicMock(),
            message="Too Many Requests: retry after 7",
            retry_after=7,
        )
        started_connector._bot.send_message = AsyncMock(side_effect=err)  # noqa: SLF001

        result = await started_connector.send(_identity(), "hi")
        assert result.ok is False
        assert result.error == "rate_limited:7"

    async def test_generic_telegram_error_returns_error(
        self, started_connector,
    ) -> None:
        started_connector._bot.send_message = AsyncMock(  # noqa: SLF001
            side_effect=TelegramAPIError(
                method=MagicMock(), message="Bad Gateway",
            )
        )

        result = await started_connector.send(_identity(), "hi")
        assert result.ok is False
        assert result.error is not None
        assert result.error.startswith("telegram:")


class TestEdit:
    async def test_happy_path(self, started_connector) -> None:
        started_connector._bot.edit_message_text = AsyncMock(return_value=MagicMock())  # noqa: SLF001

        result = await started_connector.edit(_identity(12345), "42", "new text")

        assert result.ok is True
        assert result.message_id == "42"
        kwargs = started_connector._bot.edit_message_text.call_args.kwargs  # noqa: SLF001
        assert kwargs == {"text": "new text", "chat_id": 12345, "message_id": 42}

    async def test_message_not_modified_treated_as_success(
        self, started_connector,
    ) -> None:
        started_connector._bot.edit_message_text = AsyncMock(  # noqa: SLF001
            side_effect=TelegramBadRequest(
                method=MagicMock(),
                message="Bad Request: message is not modified: specified new message content and reply markup are exactly the same",
            )
        )

        result = await started_connector.edit(_identity(), "42", "same as before")
        assert result.ok is True
        assert result.message_id == "42"

    async def test_other_bad_request_returns_error(self, started_connector) -> None:
        started_connector._bot.edit_message_text = AsyncMock(  # noqa: SLF001
            side_effect=TelegramBadRequest(
                method=MagicMock(),
                message="Bad Request: chat not found",
            )
        )

        result = await started_connector.edit(_identity(), "42", "text")
        assert result.ok is False
        assert result.error is not None
        assert result.error.startswith("telegram:")

    async def test_rate_limit_returns_error(self, started_connector) -> None:
        err = TelegramRetryAfter(
            method=MagicMock(),
            message="Too Many Requests: retry after 3",
            retry_after=3,
        )
        started_connector._bot.edit_message_text = AsyncMock(side_effect=err)  # noqa: SLF001

        result = await started_connector.edit(_identity(), "42", "x")
        assert result.ok is False
        assert result.error == "rate_limited:3"

    async def test_non_integer_message_id_rejected(self, started_connector) -> None:
        result = await started_connector.edit(_identity(), "not-a-number", "x")
        assert result.ok is False
        assert result.error is not None
        assert "bad_message_id" in result.error

    async def test_not_connected_returns_error(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        result = await c.edit(_identity(), "1", "x")
        assert result.ok is False
        assert result.error == "not connected"


class TestSendTyping:
    async def test_sends_typing_action(self, started_connector) -> None:
        started_connector._bot.send_chat_action = AsyncMock()  # noqa: SLF001

        await started_connector.send_typing(_identity(12345))

        kwargs = started_connector._bot.send_chat_action.call_args.kwargs  # noqa: SLF001
        assert kwargs == {"chat_id": 12345, "action": "typing"}

    async def test_telegram_error_is_swallowed(self, started_connector) -> None:
        started_connector._bot.send_chat_action = AsyncMock(  # noqa: SLF001
            side_effect=TelegramAPIError(method=MagicMock(), message="boom"),
        )
        # Must not raise.
        await started_connector.send_typing(_identity())

    async def test_not_connected_is_silent(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        # No bot; must not raise.
        await c.send_typing(_identity())

    async def test_bad_identity_is_silent(self, started_connector) -> None:
        started_connector._bot.send_chat_action = AsyncMock()  # noqa: SLF001
        await started_connector.send_typing(
            Identity(platform="telegram", external_id="garbage"),
        )
        started_connector._bot.send_chat_action.assert_not_awaited()  # noqa: SLF001


# ---------------------------------------------------------------------------
# Chat ID parsing
# ---------------------------------------------------------------------------


class TestParseChatId:
    def test_dm_chat_id(self) -> None:
        assert TelegramConnector._parse_chat_id("tg:chat:12345") == 12345  # noqa: SLF001

    def test_group_chat_negative_id(self) -> None:
        assert TelegramConnector._parse_chat_id("tg:chat:-1001234567") == -1001234567  # noqa: SLF001

    def test_rejects_format_without_colons(self) -> None:
        with pytest.raises(ValueError):
            TelegramConnector._parse_chat_id("12345")  # noqa: SLF001

    def test_rejects_non_integer_id(self) -> None:
        with pytest.raises(ValueError, match="non-numeric"):
            TelegramConnector._parse_chat_id("tg:chat:abc")  # noqa: SLF001

    def test_accepts_arbitrary_prefix(self) -> None:
        # The parser takes the part after the last ':' as the id. Any prefix works.
        assert TelegramConnector._parse_chat_id("slack:channel:42") == 42  # noqa: SLF001


# ---------------------------------------------------------------------------
# Photo inbound (Phase 4)
# ---------------------------------------------------------------------------


def _make_mock_photo_message(
    *,
    chat_id: int,
    chat_type: str = "private",
    caption: str = "",
    user_full_name: str | None = "Alice",
    user_id: int | None = None,
    reply_to_message_id: int | None = None,
    photo_sizes: list[tuple[int, int, int]] | None = None,
    largest_file_size: int | None = None,
):
    """Minimal MagicMock mirroring a Telegram photo ``Message``.

    ``photo_sizes`` is a list of ``(width, height, file_size)`` tuples
    representing successive :class:`PhotoSize` entries — the last one is
    the largest, matching Telegram's convention.

    In private chats Telegram guarantees ``chat_id == from_user.id`` —
    the helper defaults ``user_id`` to ``chat_id`` so DM tests don't
    have to pass both.
    """
    chat = MagicMock()
    chat.id = chat_id
    chat.type = chat_type

    from_user = None
    if user_full_name is not None:
        from_user = MagicMock()
        from_user.full_name = user_full_name
        from_user.id = user_id if user_id is not None else chat_id

    reply_to = None
    if reply_to_message_id is not None:
        reply_to = MagicMock()
        reply_to.message_id = reply_to_message_id

    if photo_sizes is None:
        photo_sizes = [(90, 60, 1024), (320, 240, 8192), (1280, 960, 65536)]

    photo_list = []
    for w, h, size in photo_sizes:
        ps = MagicMock()
        ps.width = w
        ps.height = h
        ps.file_size = size
        photo_list.append(ps)

    if largest_file_size is not None:
        photo_list[-1].file_size = largest_file_size

    message = MagicMock()
    message.chat = chat
    message.photo = photo_list
    message.caption = caption
    # Photo messages carry caption — never text.
    message.text = None
    message.from_user = from_user
    message.reply_to_message = reply_to
    return message


class TestPhotoInbound:
    async def test_photo_emits_message_event_with_image_attachment(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        c._bot = MagicMock()  # noqa: SLF001
        c._bot.download = AsyncMock(return_value=BytesIO(b"\xff\xd8\xffPHOTO"))  # noqa: SLF001

        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)

        c.set_message_handler(handler)

        msg = _make_mock_photo_message(
            chat_id=12345, caption="what is this?", user_full_name="Alice",
        )
        await c._on_photo(msg)  # noqa: SLF001

        assert len(received) == 1
        event = received[0]
        assert event.text == "what is this?"
        # DMs emit tg:user:* (Phase 6); groups still emit tg:chat:*.
        assert event.identity.external_id == "tg:user:12345"
        assert event.identity.display_name == "Alice"
        assert len(event.attachments) == 1
        att = event.attachments[0]
        assert att.kind == "image"
        assert att.data == b"\xff\xd8\xffPHOTO"
        assert att.mime_type == "image/jpeg"

    async def test_picks_largest_photo_size(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        c._bot = MagicMock()  # noqa: SLF001
        c._bot.download = AsyncMock(return_value=BytesIO(b"big"))  # noqa: SLF001

        async def handler(event: MessageEvent) -> None:
            pass

        c.set_message_handler(handler)

        msg = _make_mock_photo_message(chat_id=1)
        await c._on_photo(msg)  # noqa: SLF001

        # Verify bot.download was called with the LAST (largest) photo.
        downloaded = c._bot.download.call_args.args[0]  # noqa: SLF001
        assert downloaded is msg.photo[-1]

    async def test_empty_caption_becomes_empty_text(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        c._bot = MagicMock()  # noqa: SLF001
        c._bot.download = AsyncMock(return_value=BytesIO(b"x"))  # noqa: SLF001

        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)

        c.set_message_handler(handler)
        msg = _make_mock_photo_message(chat_id=1, caption="")
        await c._on_photo(msg)  # noqa: SLF001

        assert received[0].text == ""

    async def test_oversize_photo_replies_with_too_large(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        c._bot = MagicMock()  # noqa: SLF001
        c._bot.send_message = AsyncMock()  # noqa: SLF001

        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)

        c.set_message_handler(handler)

        # 26 MB — just over the 25 MB cap.
        msg = _make_mock_photo_message(
            chat_id=99, largest_file_size=26 * 1024 * 1024,
        )
        await c._on_photo(msg)  # noqa: SLF001

        # No handler invocation; user got a friendly reply.
        assert received == []
        c._bot.send_message.assert_awaited_once()  # noqa: SLF001
        kwargs = c._bot.send_message.call_args.kwargs  # noqa: SLF001
        assert kwargs["chat_id"] == 99
        assert "too large" in kwargs["text"].lower()

    async def test_download_failure_logs_and_drops(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        c._bot = MagicMock()  # noqa: SLF001
        c._bot.download = AsyncMock(  # noqa: SLF001
            side_effect=TelegramAPIError(method=MagicMock(), message="boom"),
        )

        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)

        c.set_message_handler(handler)

        msg = _make_mock_photo_message(chat_id=1)
        # Must not propagate. The handler sees nothing.
        await c._on_photo(msg)  # noqa: SLF001
        assert received == []

    async def test_no_handler_registered_drops_silently(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        c._bot = MagicMock()  # noqa: SLF001
        # No set_message_handler() — handler stays None.

        msg = _make_mock_photo_message(chat_id=1)
        # Must not raise; must not call download.
        await c._on_photo(msg)  # noqa: SLF001

    async def test_group_chat_sets_is_group(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        c._bot = MagicMock()  # noqa: SLF001
        c._bot.download = AsyncMock(return_value=BytesIO(b"x"))  # noqa: SLF001

        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)

        c.set_message_handler(handler)
        msg = _make_mock_photo_message(chat_id=-1001234567, chat_type="supergroup")
        await c._on_photo(msg)  # noqa: SLF001

        assert received[0].identity.is_group is True
        assert received[0].identity.external_id == "tg:chat:-1001234567"


# ---------------------------------------------------------------------------
# Photo outbound (Phase 4)
# ---------------------------------------------------------------------------


class TestPhotoOutbound:
    async def test_send_with_bytes_image_calls_send_photo(
        self, started_connector,
    ) -> None:
        from aiogram.types import BufferedInputFile

        sent_message = MagicMock()
        sent_message.message_id = 777
        started_connector._bot.send_photo = AsyncMock(return_value=sent_message)  # noqa: SLF001

        result = await started_connector.send(
            _identity(12345),
            text="a cat",
            attachments=(
                Attachment(kind="image", data=b"\xff\xd8\xff" + b"\x00" * 100,
                           mime_type="image/jpeg"),
            ),
        )

        assert result.ok is True
        assert result.message_id == "777"
        started_connector._bot.send_photo.assert_awaited_once()  # noqa: SLF001
        kwargs = started_connector._bot.send_photo.call_args.kwargs  # noqa: SLF001
        assert kwargs["chat_id"] == 12345
        assert kwargs["caption"] == "a cat"
        assert isinstance(kwargs["photo"], BufferedInputFile)

    async def test_send_with_url_image_passes_string(
        self, started_connector,
    ) -> None:
        sent_message = MagicMock()
        sent_message.message_id = 1
        started_connector._bot.send_photo = AsyncMock(return_value=sent_message)  # noqa: SLF001

        await started_connector.send(
            _identity(),
            text="",
            attachments=(
                Attachment(kind="image", data="https://example.com/x.png",
                           mime_type="image/png"),
            ),
        )

        kwargs = started_connector._bot.send_photo.call_args.kwargs  # noqa: SLF001
        assert kwargs["photo"] == "https://example.com/x.png"

    async def test_empty_text_becomes_none_caption(
        self, started_connector,
    ) -> None:
        sent_message = MagicMock()
        sent_message.message_id = 1
        started_connector._bot.send_photo = AsyncMock(return_value=sent_message)  # noqa: SLF001

        await started_connector.send(
            _identity(),
            text="",
            attachments=(
                Attachment(kind="image", data=b"x", mime_type="image/jpeg"),
            ),
        )

        kwargs = started_connector._bot.send_photo.call_args.kwargs  # noqa: SLF001
        assert kwargs["caption"] is None

    async def test_long_caption_truncated_to_1024(
        self, started_connector,
    ) -> None:
        sent_message = MagicMock()
        sent_message.message_id = 1
        started_connector._bot.send_photo = AsyncMock(return_value=sent_message)  # noqa: SLF001

        long_text = "x" * 2000
        await started_connector.send(
            _identity(),
            text=long_text,
            attachments=(
                Attachment(kind="image", data=b"x", mime_type="image/jpeg"),
            ),
        )

        kwargs = started_connector._bot.send_photo.call_args.kwargs  # noqa: SLF001
        assert len(kwargs["caption"]) == 1024
        assert kwargs["caption"].endswith("…")

    async def test_rate_limit_on_send_photo(
        self, started_connector,
    ) -> None:
        started_connector._bot.send_photo = AsyncMock(  # noqa: SLF001
            side_effect=TelegramRetryAfter(
                method=MagicMock(),
                message="Too Many Requests: retry after 4",
                retry_after=4,
            ),
        )

        result = await started_connector.send(
            _identity(), text="",
            attachments=(
                Attachment(kind="image", data=b"x", mime_type="image/jpeg"),
            ),
        )
        assert result.ok is False
        assert result.error == "rate_limited:4"

    async def test_generic_error_on_send_photo(
        self, started_connector,
    ) -> None:
        started_connector._bot.send_photo = AsyncMock(  # noqa: SLF001
            side_effect=TelegramAPIError(method=MagicMock(), message="boom"),
        )

        result = await started_connector.send(
            _identity(), text="",
            attachments=(
                Attachment(kind="image", data=b"x", mime_type="image/jpeg"),
            ),
        )
        assert result.ok is False
        assert result.error is not None
        assert result.error.startswith("telegram:")

    async def test_text_only_send_still_works(
        self, started_connector,
    ) -> None:
        """Regression: a send() with no attachments still hits send_message."""
        sent_message = MagicMock()
        sent_message.message_id = 1
        started_connector._bot.send_message = AsyncMock(return_value=sent_message)  # noqa: SLF001
        started_connector._bot.send_photo = AsyncMock()  # noqa: SLF001

        await started_connector.send(_identity(), text="hello")

        started_connector._bot.send_message.assert_awaited_once()  # noqa: SLF001
        started_connector._bot.send_photo.assert_not_awaited()  # noqa: SLF001


# ---------------------------------------------------------------------------
# Voice inbound
# ---------------------------------------------------------------------------


def _make_mock_voice_message(
    *,
    chat_id: int,
    chat_type: str = "private",
    user_full_name: str | None = "Alice",
    user_id: int | None = None,
    reply_to_message_id: int | None = None,
    duration: int = 3,
    file_size: int | None = 4096,
    mime_type: str = "audio/ogg",
):
    """Minimal MagicMock mirroring a Telegram voice ``Message``.

    In private chats Telegram guarantees ``chat_id == from_user.id`` —
    the helper defaults ``user_id`` to ``chat_id`` so DM tests don't
    have to pass both.
    """
    chat = MagicMock()
    chat.id = chat_id
    chat.type = chat_type

    from_user = None
    if user_full_name is not None:
        from_user = MagicMock()
        from_user.full_name = user_full_name
        from_user.id = user_id if user_id is not None else chat_id

    reply_to = None
    if reply_to_message_id is not None:
        reply_to = MagicMock()
        reply_to.message_id = reply_to_message_id

    voice = MagicMock()
    voice.duration = duration
    voice.file_size = file_size
    voice.mime_type = mime_type

    message = MagicMock()
    message.chat = chat
    message.voice = voice
    # Voice messages don't carry text or caption by default.
    message.text = None
    message.caption = None
    message.photo = None
    message.from_user = from_user
    message.reply_to_message = reply_to
    return message


class TestInboundVoice:
    async def test_voice_emits_message_event_with_audio_attachment(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        c._bot = MagicMock()  # noqa: SLF001
        c._bot.download = AsyncMock(return_value=BytesIO(b"OggS_bytes"))  # noqa: SLF001

        received: list[MessageEvent] = []

        async def handler(event: MessageEvent) -> None:
            received.append(event)

        c.set_message_handler(handler)

        msg = _make_mock_voice_message(chat_id=42, duration=5)
        await c._on_voice(msg)  # noqa: SLF001

        assert len(received) == 1
        event = received[0]
        # Phase 6: DMs emit tg:user:*; groups continue to emit tg:chat:*.
        assert event.identity.external_id == "tg:user:42"
        assert event.identity.is_group is False
        assert event.text == ""
        assert len(event.attachments) == 1
        att = event.attachments[0]
        assert att.kind == "audio"
        assert att.data == b"OggS_bytes"
        assert att.mime_type == "audio/ogg"

    async def test_voice_in_supergroup_sets_is_group(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        c._bot = MagicMock()  # noqa: SLF001
        c._bot.download = AsyncMock(return_value=BytesIO(b"bytes"))  # noqa: SLF001
        received: list[MessageEvent] = []
        c.set_message_handler(lambda e: received.append(e) or asyncio.sleep(0))

        msg = _make_mock_voice_message(
            chat_id=-1001234567, chat_type="supergroup",
        )
        await c._on_voice(msg)  # noqa: SLF001

        assert received[0].identity.is_group is True

    async def test_voice_reply_to_is_stringified(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        c._bot = MagicMock()  # noqa: SLF001
        c._bot.download = AsyncMock(return_value=BytesIO(b"bytes"))  # noqa: SLF001
        received: list[MessageEvent] = []

        async def handler(e):
            received.append(e)

        c.set_message_handler(handler)

        msg = _make_mock_voice_message(chat_id=1, reply_to_message_id=99)
        await c._on_voice(msg)  # noqa: SLF001

        assert received[0].reply_to_message_id == "99"

    async def test_overlong_voice_rejected_before_download(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        c._bot = MagicMock()  # noqa: SLF001
        c._bot.download = AsyncMock()  # noqa: SLF001
        c._bot.send_message = AsyncMock()  # noqa: SLF001

        received: list[MessageEvent] = []
        c.set_message_handler(lambda e: received.append(e))

        # 3 minutes — over the 2-minute cap.
        msg = _make_mock_voice_message(chat_id=7, duration=180)
        await c._on_voice(msg)  # noqa: SLF001

        c._bot.download.assert_not_awaited()  # noqa: SLF001
        c._bot.send_message.assert_awaited_once()  # noqa: SLF001
        reply_text = c._bot.send_message.call_args.kwargs["text"]  # noqa: SLF001
        assert "too long" in reply_text.lower()
        assert received == []

    async def test_oversize_voice_rejected_before_download(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        c._bot = MagicMock()  # noqa: SLF001
        c._bot.download = AsyncMock()  # noqa: SLF001
        c._bot.send_message = AsyncMock()  # noqa: SLF001

        received: list[MessageEvent] = []
        c.set_message_handler(lambda e: received.append(e))

        msg = _make_mock_voice_message(
            chat_id=7, duration=5, file_size=30 * 1024 * 1024,
        )
        await c._on_voice(msg)  # noqa: SLF001

        c._bot.download.assert_not_awaited()  # noqa: SLF001
        c._bot.send_message.assert_awaited_once()  # noqa: SLF001
        assert "too large" in c._bot.send_message.call_args.kwargs["text"].lower()  # noqa: SLF001
        assert received == []

    async def test_download_failure_drops_silently(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        c._bot = MagicMock()  # noqa: SLF001
        c._bot.download = AsyncMock(  # noqa: SLF001
            side_effect=TelegramAPIError(method=MagicMock(), message="gone"),
        )

        received: list[MessageEvent] = []
        c.set_message_handler(lambda e: received.append(e))

        msg = _make_mock_voice_message(chat_id=1)
        await c._on_voice(msg)  # noqa: SLF001

        assert received == []

    async def test_no_handler_registered_drops_silently(self) -> None:
        """Defence-in-depth: voice delivered before ConnectorManager wires
        a handler must not explode."""
        c = TelegramConnector(instance_name="t", bot_token="tok")
        c._bot = MagicMock()  # noqa: SLF001
        c._bot.download = AsyncMock(return_value=BytesIO(b"data"))  # noqa: SLF001

        msg = _make_mock_voice_message(chat_id=1)
        # Should not raise.
        await c._on_voice(msg)  # noqa: SLF001

        # Download is skipped because `_on_message` is None; the early
        # return happens before download.
        c._bot.download.assert_not_awaited()  # noqa: SLF001


# ---------------------------------------------------------------------------
# Voice outbound — send_voice
# ---------------------------------------------------------------------------


class TestSendVoice:
    async def test_happy_path_sends_ogg(self, started_connector) -> None:
        sent = MagicMock()
        sent.message_id = 77
        started_connector._bot.send_voice = AsyncMock(return_value=sent)  # noqa: SLF001

        result = await started_connector.send_voice(
            _identity(42), b"OggSAAAbytes",
        )

        assert result.ok is True
        assert result.message_id == "77"
        kwargs = started_connector._bot.send_voice.call_args.kwargs  # noqa: SLF001
        assert kwargs["chat_id"] == 42
        # voice is wrapped in BufferedInputFile
        from aiogram.types import BufferedInputFile as _BIF
        assert isinstance(kwargs["voice"], _BIF)

    async def test_voice_out_disabled_short_circuits(self) -> None:
        c = TelegramConnector(
            instance_name="t", bot_token="tok", voice_out=False,
        )
        c._bot = MagicMock()  # noqa: SLF001
        c._connected = True  # noqa: SLF001
        c._bot.send_voice = AsyncMock()  # noqa: SLF001

        result = await c.send_voice(_identity(), b"bytes")

        assert result.ok is False
        assert result.error == "disabled:voice_out=false"
        c._bot.send_voice.assert_not_awaited()  # noqa: SLF001

    async def test_not_connected_returns_error(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        # _bot is None (never started)
        result = await c.send_voice(_identity(), b"bytes")
        assert result.ok is False
        assert result.error == "not connected"

    async def test_empty_payload_rejected(self, started_connector) -> None:
        started_connector._bot.send_voice = AsyncMock()  # noqa: SLF001
        result = await started_connector.send_voice(_identity(), b"")
        assert result.ok is False
        assert result.error == "empty_payload"
        started_connector._bot.send_voice.assert_not_awaited()  # noqa: SLF001

    async def test_bad_identity_returns_error(self, started_connector) -> None:
        started_connector._bot.send_voice = AsyncMock()  # noqa: SLF001
        bad = Identity(platform="telegram", external_id="not-a-chat-id")
        result = await started_connector.send_voice(bad, b"bytes")
        assert result.ok is False
        assert result.error is not None
        assert result.error.startswith("bad_identity:")

    async def test_caption_truncated_to_1024(self, started_connector) -> None:
        sent = MagicMock()
        sent.message_id = 1
        started_connector._bot.send_voice = AsyncMock(return_value=sent)  # noqa: SLF001

        long_caption = "x" * 2000
        await started_connector.send_voice(
            _identity(), b"bytes", caption=long_caption,
        )

        kwargs = started_connector._bot.send_voice.call_args.kwargs  # noqa: SLF001
        assert kwargs["caption"] is not None
        assert len(kwargs["caption"]) == 1024
        assert kwargs["caption"].endswith("…")

    async def test_rate_limit_returns_retry_after(
        self, started_connector,
    ) -> None:
        started_connector._bot.send_voice = AsyncMock(  # noqa: SLF001
            side_effect=TelegramRetryAfter(
                method=MagicMock(),
                message="Too Many Requests: retry after 5",
                retry_after=5,
            ),
        )

        result = await started_connector.send_voice(_identity(), b"bytes")

        assert result.ok is False
        assert result.error == "rate_limited:5"

    async def test_generic_telegram_error_returns_error(
        self, started_connector,
    ) -> None:
        started_connector._bot.send_voice = AsyncMock(  # noqa: SLF001
            side_effect=TelegramAPIError(method=MagicMock(), message="boom"),
        )
        result = await started_connector.send_voice(_identity(), b"bytes")
        assert result.ok is False
        assert result.error is not None
        assert result.error.startswith("telegram:")


# ---------------------------------------------------------------------------
# Phase 6 — identity format split (DM → tg:user:*; group → tg:chat:*)
# ---------------------------------------------------------------------------


class TestIdentityFormat:
    """Pin the Phase-6 contract: DMs key on the user, groups key on the
    chat. The metadata dict carries both ids so downstream audit and
    debugging can cross-reference without re-parsing strings."""

    async def test_dm_emits_tg_user_prefix(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        received: list[MessageEvent] = []
        c.set_message_handler(lambda e: received.append(e) or asyncio.sleep(0))

        msg = _make_mock_message(chat_id=42, text="hi")
        await c._on_text(msg)  # noqa: SLF001

        assert received[0].identity.external_id == "tg:user:42"
        assert received[0].identity.is_group is False
        assert received[0].identity.metadata["chat_id"] == 42
        assert received[0].identity.metadata["user_id"] == 42
        assert received[0].identity.metadata["chat_type"] == "private"

    async def test_group_still_emits_tg_chat_prefix(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        received: list[MessageEvent] = []
        c.set_message_handler(lambda e: received.append(e) or asyncio.sleep(0))

        msg = _make_mock_message(
            chat_id=-1001234567,
            chat_type="supergroup",
            text="hi team",
            user_id=99,  # the user in the group — ≠ chat_id
        )
        await c._on_text(msg)  # noqa: SLF001

        assert received[0].identity.external_id == "tg:chat:-1001234567"
        assert received[0].identity.is_group is True
        assert received[0].identity.metadata["chat_id"] == -1001234567
        assert received[0].identity.metadata["user_id"] == 99
        assert received[0].identity.metadata["chat_type"] == "supergroup"

    async def test_channel_is_treated_as_group(self) -> None:
        c = TelegramConnector(instance_name="t", bot_token="tok")
        received: list[MessageEvent] = []
        c.set_message_handler(lambda e: received.append(e) or asyncio.sleep(0))

        msg = _make_mock_message(
            chat_id=-1009999999,
            chat_type="channel",
            text="broadcast",
            user_full_name=None,  # channels often post without a from_user
        )
        await c._on_text(msg)  # noqa: SLF001

        assert received[0].identity.external_id == "tg:chat:-1009999999"
        assert received[0].identity.is_group is True

    async def test_parse_chat_id_accepts_both_prefixes(self) -> None:
        """``_parse_chat_id`` is used on outbound for all identities —
        it must strip either DM or group prefix to the numeric id
        Telegram's ``send_message`` needs."""
        assert TelegramConnector._parse_chat_id("tg:user:42") == 42  # noqa: SLF001
        assert TelegramConnector._parse_chat_id("tg:chat:12345") == 12345  # noqa: SLF001
        assert TelegramConnector._parse_chat_id(  # noqa: SLF001
            "tg:chat:-1001234567",
        ) == -1001234567
