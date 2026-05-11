"""Telegram connector implementation.

Uses aiogram 3's async Bot + Dispatcher. Long-polling runs as a
background task spawned by :meth:`start`; graceful shutdown signals the
poll loop and joins the task within a short timeout.

Supports text, single-photo, and voice-note messages in both
directions. Voice I/O is gated per-instance on ``voice_in`` /
``voice_out`` config flags — operators who want a text-only bot even
when ASR/TTS are configured globally can opt out. Documents,
stickers, and media groups still fall off the handlers and are
silently ignored — see the plugin README for the full list of
supported/unsupported message types.
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

# Voice notes: Telegram's own cap is 20 MB on download; we match /api/upload's
# 25 MB ceiling for consistency with photos. The duration cap prevents Tank
# from waiting minutes on ASR for a fat clip.
_MAX_VOICE_BYTES = 25 * 1024 * 1024
_MAX_VOICE_DURATION_S = 120

# Timeout for the polling task to drain cleanly on shutdown.
_SHUTDOWN_TIMEOUT_S = 5.0


class TelegramConnector(Connector):
    """Platform adapter for Telegram."""

    platform = "telegram"

    def __init__(
        self,
        *,
        instance_name: str,
        bot_token: str,
        voice_in: bool = True,
        voice_out: bool = True,
    ) -> None:
        super().__init__(
            instance_name=instance_name,
            capabilities=ConnectorCapabilities(
                supports_edits=True,
                edit_min_interval_ms=_DEFAULT_EDIT_INTERVAL_MS,
                max_message_length=_TELEGRAM_MAX_MESSAGE_LENGTH,
                supports_images_in=True,
                supports_images_out=True,
                supports_voice_in=voice_in,
                supports_voice_out=voice_out,
                supports_typing_indicator=True,
            ),
        )
        self._token = bot_token
        self._voice_in = voice_in
        self._voice_out = voice_out
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
        # Register handlers in priority order. aiogram 3 dispatches to
        # the first handler whose filter matches, so order is stable —
        # the filters (photo / voice / text) are mutually exclusive at
        # the API level anyway. ``F.voice`` is only registered when the
        # operator actually wants voice in, so a bot configured
        # ``voice_in: false`` will silently drop voice notes (they fall
        # off all handlers).
        self._dp.message.register(self._on_photo, F.photo)
        if self._voice_in:
            self._dp.message.register(self._on_voice, F.voice)
        self._dp.message.register(self._on_text, F.text)
        self._task = asyncio.create_task(
            self._run_polling(),
            name=f"telegram-poll-{self.instance_name}",
        )
        self._connected = True
        logger.info(
            "Telegram connector '%s' started (voice_in=%s, voice_out=%s)",
            self.instance_name, self._voice_in, self._voice_out,
        )

    async def _run_polling(self) -> None:
        """Run long-polling and surface unexpected crashes.

        ``handle_signals=False`` is critical: aiogram's default is to
        install its own ``SIGINT``/``SIGTERM`` handlers on the running
        event loop via ``loop.add_signal_handler``, which overwrites the
        handlers uvicorn installed during startup. When the operator hits
        Ctrl+C, aiogram catches the signal and stops only its own polling
        loop — uvicorn never hears it, the ASGI lifespan never fires, and
        the process appears hung. With ``handle_signals=False`` uvicorn
        owns the signal pipeline; its shutdown flow calls our lifespan,
        which calls :meth:`stop` on this connector, which drains the poll
        loop cleanly.

        aiogram swallows some errors internally; we wrap the call so a
        crashing polling loop is at least logged loudly rather than
        leaving the connector silently dead.
        """
        assert self._dp is not None and self._bot is not None  # noqa: S101
        try:
            await self._dp.start_polling(self._bot, handle_signals=False)
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

        identity = self._make_identity(message)

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

        identity = self._make_identity(message)

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

    async def _on_voice(self, message: "Message") -> None:
        """Handle an inbound voice note.

        Telegram delivers voice notes as Ogg-encapsulated Opus at 48 kHz
        mono — the format is fixed by the client and we don't need to
        sniff the MIME. Rejects overlong or oversized clips at the edge
        before paying for the download, so a user who taps-and-holds for
        five minutes gets a fast "too long" reply instead of a silent
        timeout.

        Transcription itself happens in
        :meth:`ConnectorManager._audio_to_text_block` — this handler just
        packages the bytes as ``Attachment(kind="audio")`` and lets the
        manager route them through the shared ``ASREngine``.
        """
        if self._on_message is None:
            logger.debug(
                "Telegram connector '%s': dropping inbound voice; "
                "no handler registered",
                self.instance_name,
            )
            return
        if self._bot is None:
            return
        if message.voice is None:
            return

        voice = message.voice

        # Duration is the cheapest reject — no bytes crossed the wire yet.
        if voice.duration and voice.duration > _MAX_VOICE_DURATION_S:
            with contextlib.suppress(TelegramAPIError):
                await self._bot.send_message(
                    chat_id=message.chat.id,
                    text=(
                        f"That voice note is too long — please keep it "
                        f"under {_MAX_VOICE_DURATION_S // 60} minutes."
                    ),
                )
            return

        if voice.file_size and voice.file_size > _MAX_VOICE_BYTES:
            with contextlib.suppress(TelegramAPIError):
                await self._bot.send_message(
                    chat_id=message.chat.id,
                    text="That voice note is too large — please send a shorter one.",
                )
            return

        try:
            buf = await self._bot.download(voice)
        except TelegramAPIError:
            logger.exception(
                "Telegram connector '%s': voice download failed in chat %s",
                self.instance_name, message.chat.id,
            )
            return
        except Exception:
            logger.exception(
                "Telegram connector '%s': unexpected error downloading voice",
                self.instance_name,
            )
            return

        if buf is None:
            logger.debug(
                "Telegram connector '%s': voice download returned no buffer",
                self.instance_name,
            )
            return

        try:
            with contextlib.suppress(Exception):
                buf.seek(0)
            data = buf.read()
        except Exception:
            logger.exception(
                "Telegram connector '%s': voice buffer read failed",
                self.instance_name,
            )
            return
        finally:
            with contextlib.suppress(Exception):
                buf.close()

        if not data:
            return

        identity = self._make_identity(message)

        reply_to_id: str | None = None
        if message.reply_to_message is not None:
            reply_to_id = str(message.reply_to_message.message_id)

        # Telegram voice notes are always Ogg/Opus — no sniffing needed.
        event = MessageEvent(
            identity=identity,
            text="",
            attachments=(
                Attachment(kind="audio", data=data, mime_type="audio/ogg"),
            ),
            reply_to_message_id=reply_to_id,
        )
        try:
            await self._on_message(event)
        except Exception:
            logger.exception(
                "Telegram connector '%s': inbound handler raised on voice",
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

    async def send_voice(
        self,
        identity: Identity,
        data: bytes,
        *,
        mime_type: str = "audio/ogg",
        caption: str = "",
    ) -> SendResult:
        """Send an Ogg/Opus voice note.

        Telegram expects Ogg-encapsulated Opus — our
        :mod:`~tank_backend.connectors.voice_bridge` encoder produces
        exactly that shape, so the dispatcher can hand us raw bytes.
        ``voice_out=False`` on this instance short-circuits with a
        ``"disabled"`` error so the upstream dispatcher logs and skips
        without burning an HTTP round-trip.

        ``caption`` is silently truncated to Telegram's 1024-char limit
        (matching the photo path) — ffmpeg errors on long captions are
        more confusing than a trimmed-with-ellipsis message.
        """
        if self._bot is None:
            return SendResult(ok=False, error="not connected")
        if not self._voice_out:
            return SendResult(ok=False, error="disabled:voice_out=false")
        try:
            chat_id = self._parse_chat_id(identity.external_id)
        except ValueError as e:
            return SendResult(ok=False, error=f"bad_identity:{e}")
        if not data:
            return SendResult(ok=False, error="empty_payload")

        send_caption: str | None = None
        if caption:
            send_caption = (
                caption
                if len(caption) <= _TELEGRAM_MAX_CAPTION_LENGTH
                else caption[: _TELEGRAM_MAX_CAPTION_LENGTH - 1] + "…"
            )

        voice_file = BufferedInputFile(data, filename="voice.ogg")
        try:
            msg = await self._bot.send_voice(
                chat_id=chat_id,
                voice=voice_file,
                caption=send_caption,
            )
        except TelegramRetryAfter as e:
            return SendResult(ok=False, error=f"rate_limited:{e.retry_after}")
        except TelegramAPIError as e:
            return SendResult(ok=False, error=f"telegram:{e}")

        return SendResult(ok=True, message_id=str(msg.message_id))

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

    def _make_identity(self, message: "Message") -> Identity:
        """Build an :class:`Identity` from an inbound Telegram ``Message``.

        DMs emit ``tg:user:{user_id}`` so allowlists can match individual
        people regardless of which 1:1 chat the ``chat_id`` happens to
        represent. Groups and channels emit ``tg:chat:{chat_id}`` — the
        chat itself is the allowlist unit, not any particular member.

        :attr:`Identity.metadata` stashes both raw ids so downstream
        audit / debugging can cross-reference without re-parsing the
        external_id string.
        """
        display_name = ""
        if message.from_user is not None:
            display_name = message.from_user.full_name or ""

        chat = message.chat
        chat_id: int = chat.id
        user_id: int | None = (
            message.from_user.id if message.from_user is not None else None
        )
        is_group = chat.type in ("group", "supergroup", "channel")

        if is_group:
            external_id = f"tg:chat:{chat_id}"
        else:
            # DMs: prefer the user id (equals chat_id but is the more
            # semantically-meaningful key) and fall back to chat_id only
            # when from_user is missing — which shouldn't happen in real
            # Telegram traffic, but defensive coding costs nothing here.
            external_id = f"tg:user:{user_id if user_id is not None else chat_id}"

        return Identity(
            platform=self.platform,
            external_id=external_id,
            display_name=display_name,
            is_group=is_group,
            metadata={
                "chat_id": chat_id,
                "user_id": user_id,
                "chat_type": chat.type,
            },
        )

    @staticmethod
    def _parse_chat_id(external_id: str) -> int:
        """Parse ``"tg:chat:<id>"`` or ``"tg:user:<id>"`` → ``<id>`` as int.

        Both inbound prefixes are accepted for outbound operations —
        Telegram's ``send_message`` takes the same chat_id regardless of
        whether it was a DM or a group. Raises ``ValueError`` for any
        format that doesn't match — the connector framework should never
        produce one, but defensive parsing protects against a bad
        identity slipping through.
        """
        _, sep, raw = external_id.rpartition(":")
        if not sep or not raw:
            raise ValueError(f"not a telegram identity: {external_id!r}")
        try:
            return int(raw)
        except ValueError as e:
            raise ValueError(
                f"telegram identity has non-numeric id: {external_id!r}"
            ) from e
