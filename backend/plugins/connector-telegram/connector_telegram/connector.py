"""Telegram connector implementation.

Uses aiogram 3's async Bot + Dispatcher. Long-polling runs as a
background task spawned by :meth:`start`; graceful shutdown signals the
poll loop and joins the task within a short timeout.

Text-only in this release. Non-text inbound messages (voice, photos,
documents, stickers) are ignored — see the plugin README for the full
list of Phase-3 limitations.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramRetryAfter,
)
from tank_contracts.connector import (
    Attachment,
    Connector,
    ConnectorCapabilities,
    Identity,
    MessageEvent,
    SendResult,
)

if TYPE_CHECKING:
    from aiogram.types import Message

logger = logging.getLogger("TelegramConnector")

# Telegram's rate limit for editMessageText is roughly 1 edit per second per
# chat. Add a small safety margin.
_DEFAULT_EDIT_INTERVAL_MS = 1100

# Telegram's hard max message length for sendMessage.
_TELEGRAM_MAX_MESSAGE_LENGTH = 4096

# Timeout for the polling task to drain cleanly on shutdown.
_SHUTDOWN_TIMEOUT_S = 5.0


class TelegramConnector(Connector):
    """Platform adapter for Telegram."""

    platform = "telegram"

    def __init__(self, *, instance_name: str, bot_token: str) -> None:
        super().__init__(
            instance_name=instance_name,
            capabilities=ConnectorCapabilities(
                supports_edits=True,
                edit_min_interval_ms=_DEFAULT_EDIT_INTERVAL_MS,
                max_message_length=_TELEGRAM_MAX_MESSAGE_LENGTH,
                supports_typing_indicator=True,
            ),
        )
        self._token = bot_token
        self._bot: Bot | None = None
        self._dp: Dispatcher | None = None
        self._task: asyncio.Task | None = None

    # ── Lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        if self._connected:
            return
        self._bot = Bot(
            token=self._token,
            default=DefaultBotProperties(parse_mode=None),
        )
        self._dp = Dispatcher()
        # `F.text` matches any inbound message whose ``text`` field is
        # truthy. Photos, voice notes, stickers etc. have ``text == None``
        # (they carry ``caption`` or media payloads instead) and fall off
        # this filter — silently ignored for v1.
        self._dp.message.register(self._on_text, F.text)
        self._task = asyncio.create_task(
            self._run_polling(),
            name=f"telegram-poll-{self.instance_name}",
        )
        self._connected = True
        logger.info("Telegram connector '%s' started", self.instance_name)

    async def _run_polling(self) -> None:
        """Run long-polling and surface unexpected crashes.

        aiogram swallows some errors internally; we wrap the call so a
        crashing polling loop is at least logged loudly rather than
        leaving the connector silently dead.
        """
        assert self._dp is not None and self._bot is not None  # noqa: S101
        try:
            await self._dp.start_polling(self._bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Telegram connector '%s' polling task crashed",
                self.instance_name,
            )
            raise

    async def stop(self) -> None:
        if not self._connected:
            return
        # Signal the poll loop to exit. aiogram's ``stop_polling`` returns
        # once the pending getUpdates call is cancelled or the next update
        # arrives.
        if self._dp is not None:
            with contextlib.suppress(Exception):
                await self._dp.stop_polling()

        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=_SHUTDOWN_TIMEOUT_S)
            except asyncio.TimeoutError:
                logger.warning(
                    "Telegram connector '%s' polling task did not exit in %.0fs; "
                    "cancelling",
                    self.instance_name, _SHUTDOWN_TIMEOUT_S,
                )
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await self._task
            except Exception:
                logger.exception(
                    "Telegram connector '%s' polling task raised on shutdown",
                    self.instance_name,
                )

        if self._bot is not None:
            with contextlib.suppress(Exception):
                await self._bot.session.close()

        self._bot = None
        self._dp = None
        self._task = None
        self._connected = False
        logger.info("Telegram connector '%s' stopped", self.instance_name)

    # ── Inbound ─────────────────────────────────────────────────────

    async def _on_text(self, message: "Message") -> None:
        """Handle an inbound text message."""
        if self._on_message is None:
            # Not yet registered with a ConnectorManager — drop defensively.
            logger.debug(
                "Telegram connector '%s': dropping inbound message; "
                "no handler registered",
                self.instance_name,
            )
            return

        display_name = ""
        if message.from_user is not None:
            display_name = message.from_user.full_name or ""

        identity = Identity(
            platform=self.platform,
            external_id=f"tg:chat:{message.chat.id}",
            display_name=display_name,
            is_group=message.chat.type in ("group", "supergroup"),
        )

        reply_to_id: str | None = None
        if message.reply_to_message is not None:
            reply_to_id = str(message.reply_to_message.message_id)

        event = MessageEvent(
            identity=identity,
            text=message.text or "",
            reply_to_message_id=reply_to_id,
        )
        try:
            await self._on_message(event)
        except Exception:
            logger.exception(
                "Telegram connector '%s': inbound handler raised",
                self.instance_name,
            )

    # ── Outbound ────────────────────────────────────────────────────

    async def send(
        self,
        identity: Identity,
        text: str,
        *,
        reply_to: str | None = None,
        attachments: tuple[Attachment, ...] = (),
    ) -> SendResult:
        if self._bot is None:
            return SendResult(ok=False, error="not connected")
        try:
            chat_id = self._parse_chat_id(identity.external_id)
        except ValueError as e:
            return SendResult(ok=False, error=f"bad_identity:{e}")

        reply_to_message_id: int | None = None
        if reply_to is not None:
            try:
                reply_to_message_id = int(reply_to)
            except ValueError:
                logger.debug(
                    "Telegram connector '%s': ignoring non-integer reply_to=%r",
                    self.instance_name, reply_to,
                )

        try:
            msg = await self._bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_to_message_id=reply_to_message_id,
            )
        except TelegramRetryAfter as e:
            return SendResult(ok=False, error=f"rate_limited:{e.retry_after}")
        except TelegramAPIError as e:
            return SendResult(ok=False, error=f"telegram:{e}")

        return SendResult(ok=True, message_id=str(msg.message_id))

    async def edit(
        self,
        identity: Identity,
        message_id: str,
        text: str,
    ) -> SendResult:
        if self._bot is None:
            return SendResult(ok=False, error="not connected")
        try:
            chat_id = self._parse_chat_id(identity.external_id)
        except ValueError as e:
            return SendResult(ok=False, error=f"bad_identity:{e}")

        try:
            message_id_int = int(message_id)
        except ValueError:
            return SendResult(ok=False, error=f"bad_message_id:{message_id!r}")

        try:
            await self._bot.edit_message_text(
                text=text,
                chat_id=chat_id,
                message_id=message_id_int,
            )
        except TelegramBadRequest as e:
            # "message is not modified" fires when we flush the same buffer
            # twice. From Tank's perspective that's a benign no-op — report
            # success and let the consumer keep using the existing id.
            if "message is not modified" in str(e).lower():
                return SendResult(ok=True, message_id=message_id)
            return SendResult(ok=False, error=f"telegram:{e}")
        except TelegramRetryAfter as e:
            return SendResult(ok=False, error=f"rate_limited:{e.retry_after}")
        except TelegramAPIError as e:
            return SendResult(ok=False, error=f"telegram:{e}")

        return SendResult(ok=True, message_id=message_id)

    async def send_typing(self, identity: Identity) -> None:
        if self._bot is None:
            return
        try:
            chat_id = self._parse_chat_id(identity.external_id)
        except ValueError:
            return
        # Typing is advisory — swallow any Telegram failure.
        with contextlib.suppress(TelegramAPIError):
            await self._bot.send_chat_action(chat_id=chat_id, action="typing")

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _parse_chat_id(external_id: str) -> int:
        """Parse ``"tg:chat:<id>"`` → ``<id>`` as int.

        Raises ``ValueError`` for any format that doesn't match — the
        connector framework should never produce one, but defensive
        parsing protects against a bad identity slipping through.
        """
        _, sep, raw = external_id.rpartition(":")
        if not sep or not raw:
            raise ValueError(f"not a telegram identity: {external_id!r}")
        try:
            return int(raw)
        except ValueError as e:
            raise ValueError(
                f"telegram identity has non-numeric chat id: {external_id!r}"
            ) from e
