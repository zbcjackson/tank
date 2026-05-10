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
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramRetryAfter,
)
from tank_contracts.connector import Identity, MessageEvent

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
        # Phase-3 scope: no media in/out yet.
        assert caps.supports_images_in is False
        assert caps.supports_images_out is False
        assert caps.supports_voice_in is False
        assert caps.supports_voice_out is False


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
            # Handler for plain text was registered.
            aiogram_mocks.mocks.dp.message.register.assert_called_once()
            # Polling task was spawned.
            assert c._task is not None  # noqa: SLF001
            assert not c._task.done()  # noqa: SLF001
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
    reply_to_message_id: int | None = None,
):
    """Build a minimal MagicMock looking like ``aiogram.types.Message``."""
    chat = MagicMock()
    chat.id = chat_id
    chat.type = chat_type

    from_user = None
    if user_full_name is not None:
        from_user = MagicMock()
        from_user.full_name = user_full_name

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
        assert event.identity.external_id == "tg:chat:12345"
        assert event.identity.display_name == "Alice"
        assert event.identity.is_group is False

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
