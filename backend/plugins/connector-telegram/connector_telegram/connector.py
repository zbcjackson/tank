"""Telegram connector implementation.

Uses aiogram 3's async Bot + Dispatcher. Long-polling runs as a
background task spawned by :meth:`start`; graceful shutdown signals the
poll loop and joins the task within a short timeout.

Text and single-photo messages are supported in both directions.
Voice notes, documents, stickers, and media groups still fall off the
handlers and are silently ignored for now — see the plugin README for
the full list of supported/unsupported message types.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramRetryAfter,
)
from aiogram.types import BufferedInputFile
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

# Telegram's max caption length (for media like photos).
_TELEGRAM_MAX_CAPTION_LENGTH = 1024

# Upper bound on photos we'll download / accept inbound. Matches the
# /api/upload boundary elsewhere in Tank.
_MAX_PHOTO_BYTES = 25 * 1024 * 1024

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
                supports_images_in=True,
                supports_images_out=True,
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
        # Register handlers in priority order. ``F.photo`` matches photo
        # messages (with or without caption); ``F.text`` matches plain
        # text-only messages. aiogram 3 dispatches to the first handler
        # whose filter matches, so order here is safe — text and photo
        # filters are mutually exclusive at the API level.
        self._dp.message.register(self._on_photo, F.photo)
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

    async def _on_photo(self, message: "Message") -> None:
        """Handle an inbound photo message.

        Telegram delivers photos as a list of :class:`PhotoSize` at
        several resolutions. We take the largest (last element) as the
        canonical version — the smaller ones are thumbnails.

        Photo messages can carry a caption; we surface it as
        :attr:`MessageEvent.text` so the downstream LLM sees the user's
        prompt ("what is this?") alongside the image.
        """
        if self._on_message is None:
            logger.debug(
                "Telegram connector '%s': dropping inbound photo; "
                "no handler registered",
                self.instance_name,
            )
            return
        if self._bot is None:
            return
        if not message.photo:
            return

        largest = message.photo[-1]

        # Reject oversized photos at the edge before downloading.
        if largest.file_size and largest.file_size > _MAX_PHOTO_BYTES:
            with contextlib.suppress(TelegramAPIError):
                await self._bot.send_message(
                    chat_id=message.chat.id,
                    text=(
                        "That image is too large — please send one "
                        "under 25 MB."
                    ),
                )
            return

        try:
            buf = await self._bot.download(largest)
        except TelegramAPIError:
            logger.exception(
                "Telegram connector '%s': photo download failed in chat %s",
                self.instance_name, message.chat.id,
            )
            return
        except Exception:
            logger.exception(
                "Telegram connector '%s': unexpected error downloading photo",
                self.instance_name,
            )
            return

        if buf is None:
            logger.debug(
                "Telegram connector '%s': download returned no buffer",
                self.instance_name,
            )
            return

        try:
            # aiogram returns a ``BytesIO`` in practice, but the declared
            # type is ``BinaryIO`` — which doesn't expose ``getvalue()``.
            # Rewind + read works for both without fighting the stubs.
            with contextlib.suppress(Exception):
                buf.seek(0)
            data = buf.read()
        except Exception:
            logger.exception(
                "Telegram connector '%s': buffer read failed",
                self.instance_name,
            )
            return
        finally:
            with contextlib.suppress(Exception):
                buf.close()

        if not data:
            return

        # Post-server processing at Telegram normalises uploaded photos
        # to JPEG regardless of the user's original format.
        mime_type = "image/jpeg"

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
            text=message.caption or "",
            attachments=(
                Attachment(kind="image", data=data, mime_type=mime_type),
            ),
            reply_to_message_id=reply_to_id,
        )
        try:
            await self._on_message(event)
        except Exception:
            logger.exception(
                "Telegram connector '%s': inbound handler raised on photo",
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

        # Route image attachments through send_photo. The Connector
        # contract allows mixed attachment + text; Telegram's photo API
        # only carries a single photo per send with an optional caption
        # (≤1024 chars), so we send the first image here and leave any
        # leftover text to the text path. In practice today callers
        # invoke send() either with ``text`` OR with ``attachments`` (the
        # StreamConsumer sends text; the _ImageDispatcher sends photos).
        image_att = next(
            (a for a in attachments if a.kind == "image"),
            None,
        )
        if image_att is not None:
            return await self._send_photo(
                chat_id=chat_id,
                attachment=image_att,
                caption=text,
                reply_to_message_id=reply_to_message_id,
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

    async def _send_photo(
        self,
        *,
        chat_id: int,
        attachment: Attachment,
        caption: str,
        reply_to_message_id: int | None,
    ) -> SendResult:
        """Deliver one image via ``bot.send_photo``.

        ``attachment.data`` may be ``bytes`` (uploaded as a
        :class:`BufferedInputFile`) or ``str`` (passed to Telegram as a
        URL — Telegram's servers then fetch and host it). The caption is
        silently truncated to the 1024-char Telegram limit so we never
        raise a confusing ``MESSAGE_CAPTION_TOO_LONG`` mid-reply.
        """
        assert self._bot is not None  # noqa: S101 — guarded by caller

        if isinstance(attachment.data, bytes):
            photo: Any = BufferedInputFile(
                attachment.data,
                filename=attachment.filename or "image.jpg",
            )
        elif isinstance(attachment.data, str):
            photo = attachment.data
        else:
            return SendResult(
                ok=False,
                error=f"bad_attachment_data:{type(attachment.data).__name__}",
            )

        send_caption: str | None = None
        if caption:
            send_caption = (
                caption
                if len(caption) <= _TELEGRAM_MAX_CAPTION_LENGTH
                else caption[: _TELEGRAM_MAX_CAPTION_LENGTH - 1] + "…"
            )

        try:
            msg = await self._bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=send_caption,
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
