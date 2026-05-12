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
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramRetryAfter,
)
from aiogram.types import (
    BufferedInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from tank_contracts.connector import (
    Attachment,
    Connector,
    ConnectorCapabilities,
    Identity,
    MessageEvent,
    SendResult,
)
from tank_contracts.connector_sdk import (
    APPROVAL_ACTION_PREFIX,
    APPROVAL_CHOICE_ALLOW_FOREVER,
    APPROVAL_CHOICE_ALLOW_ONCE,
    APPROVAL_CHOICE_DENY,
    BackgroundTaskRunner,
    build_prompt_text,
    decode_action,
    encode_action,
    truncate_for_platform,
)

if TYPE_CHECKING:
    from aiogram.types import CallbackQuery, Message

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

# Media-group (album) buffering window. Telegram delivers albums as N
# separate Message objects arriving within ~50-100ms of each other, with
# no explicit "album finished" signal. We collect siblings for this long
# after the first photo, then flush them as a single MessageEvent.
_MEDIA_GROUP_BUFFER_S = 0.5

# Defensive cap on the album buffer. Telegram limits albums to 10 files
# client-side, but a misbehaving client could in principle send more —
# anything above this cap falls through to the existing single-photo
# path rather than accumulating unboundedly.
_MAX_MEDIA_GROUP_SIZE = 10


# Approval-button wire format + choice constants live in
# ``tank_contracts.connector_sdk.constants`` and are imported above.
# ``APPROVAL_ACTION_PREFIX`` drives both the ``F.data.startswith(...)``
# filter and the payloads ``encode_action`` emits, so all four parties
# (broker + three plugins) stay agreed on the exact literal.


@dataclass
class _PendingPhoto:
    """One photo accumulated for a media group.

    ``message`` is kept so the flush path can re-derive the Identity
    from the first-arriving message (Telegram's album caption +
    thread-reply conventions both key on the album's first message).
    """

    data: bytes
    mime_type: str
    caption: str | None
    message: "Message"


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
        # Shared lifecycle coordinator: owns the polling task's lifecycle
        # (spawn, drain-with-timeout, cancel-on-timeout). The platform-
        # specific "signal the loop to exit" call (``dp.stop_polling()``)
        # stays in ``stop()``; the runner only manages the background
        # task after that signal lands.
        self._runner = BackgroundTaskRunner(
            instance_name=instance_name,
            platform=self.platform,
            shutdown_timeout_s=_SHUTDOWN_TIMEOUT_S,
        )
        # Media-group (album) buffering — see ``_on_photo`` + ``_flush_media_group``.
        # ``media_group_id`` → list of photos accumulated so far.
        self._media_group_buffers: dict[str, list[_PendingPhoto]] = {}
        # ``media_group_id`` → one-shot timer scheduled on the first photo
        # of the group. Siblings DO NOT reset the timer; otherwise a
        # steady dribble of photos could keep a group alive forever.
        self._media_group_timers: dict[str, asyncio.TimerHandle] = {}

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
        # Phase 10: register the callback-query handler for approval
        # button clicks. Filter ``F.data.startswith("approve:")`` so
        # other bots that add buttons via the same dispatcher (not
        # Phase 10 scope, but possible in the future) don't step on
        # each other. ``aiogram`` routes callbacks independently of
        # the message-type filters above — no ordering concern.
        self._dp.callback_query.register(
            self._on_callback_query,
            F.data.startswith(f"{APPROVAL_ACTION_PREFIX}:"),
        )
        self._runner.spawn(self._run_polling())
        self._connected = True
        logger.info(
            "Telegram connector '%s' started (voice_in=%s, voice_out=%s)",
            self.instance_name, self._voice_in, self._voice_out,
        )

    async def _run_polling(self) -> None:
        """Run long-polling until cancelled or dispatcher shuts down.

        ``handle_signals=False`` is critical: aiogram's default is to
        install its own ``SIGINT``/``SIGTERM`` handlers on the running
        event loop via ``loop.add_signal_handler``, which overwrites the
        handlers uvicorn installed during startup. When the operator hits
        Ctrl+C, aiogram catches the signal and stops only its own polling
        loop — uvicorn never hears it, the ASGI lifespan never fires, and
        the process appears hung. With ``handle_signals=False`` uvicorn
        owns the signal pipeline; its shutdown flow calls our lifespan,
        which calls :meth:`stop` on this connector, which drains the poll
        loop cleanly via the shared :class:`BackgroundTaskRunner`.

        Exception logging + cancellation handling live on the runner;
        this method only owns the platform-specific await.
        """
        assert self._dp is not None and self._bot is not None  # noqa: S101
        await self._dp.start_polling(self._bot, handle_signals=False)

    async def stop(self) -> None:
        if not self._connected:
            return
        # Signal the poll loop to exit. aiogram's ``stop_polling`` returns
        # once the pending getUpdates call is cancelled or the next update
        # arrives.
        if self._dp is not None:
            with contextlib.suppress(Exception):
                await self._dp.stop_polling()

        # Hand the task's drain-then-cancel choreography to the shared
        # runner — it handles timeout, cancellation, and exception
        # swallowing consistently across plugins.
        await self._runner.drain()

        if self._bot is not None:
            with contextlib.suppress(Exception):
                await self._bot.session.close()

        # Cancel any pending media-group flush timers and drop buffered
        # photos. The polling loop is gone; flushes can't reach the
        # (now-cleared) _on_message handler anyway.
        for timer in self._media_group_timers.values():
            with contextlib.suppress(Exception):
                timer.cancel()
        self._media_group_timers.clear()
        self._media_group_buffers.clear()

        self._bot = None
        self._dp = None
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

        Photos that are part of an **album** (multi-photo send) arrive
        as N separate messages sharing the same ``media_group_id``. We
        buffer siblings for ``_MEDIA_GROUP_BUFFER_S`` and then flush
        them as a single :class:`MessageEvent` with N attachments —
        otherwise the LLM sees N separate turns and replies N times.

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

        data = await self._download_photo_bytes(message)
        if data is None:
            return

        group_id = message.media_group_id
        if group_id is None:
            # Single-photo path — dispatch immediately.
            await self._dispatch_single_photo(message, data)
            return

        # Album path — defensive cap on buffer size. If a misbehaving
        # client ever pushes past the limit, fall the excess through as
        # a standalone photo rather than accumulating forever.
        buffer = self._media_group_buffers.setdefault(group_id, [])
        if len(buffer) >= _MAX_MEDIA_GROUP_SIZE:
            logger.warning(
                "Telegram connector '%s': media group '%s' exceeded "
                "%d photos; treating overflow as standalone",
                self.instance_name, group_id, _MAX_MEDIA_GROUP_SIZE,
            )
            await self._dispatch_single_photo(message, data)
            return

        buffer.append(_PendingPhoto(
            data=data,
            mime_type="image/jpeg",
            caption=message.caption,
            message=message,
        ))

        # Arm the flush timer on the first photo. Siblings must NOT
        # restart it — otherwise a steady dribble of photos could keep
        # the album open past any reasonable wait.
        if group_id not in self._media_group_timers:
            loop = asyncio.get_running_loop()
            self._media_group_timers[group_id] = loop.call_later(
                _MEDIA_GROUP_BUFFER_S,
                lambda gid=group_id: asyncio.create_task(
                    self._flush_media_group(gid),
                    name=f"telegram-album-flush-{self.instance_name}-{gid}",
                ),
            )

    async def _dispatch_single_photo(
        self, message: "Message", data: bytes,
    ) -> None:
        """Emit a :class:`MessageEvent` for one (non-album) photo."""
        if self._on_message is None:
            return

        identity = self._make_identity(message)

        reply_to_id: str | None = None
        if message.reply_to_message is not None:
            reply_to_id = str(message.reply_to_message.message_id)

        event = MessageEvent(
            identity=identity,
            text=message.caption or "",
            attachments=(
                Attachment(kind="image", data=data, mime_type="image/jpeg"),
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

    async def _flush_media_group(self, group_id: str) -> None:
        """Drain the buffered album into a single :class:`MessageEvent`.

        Called by the per-album timer. If ``stop()`` ran concurrently,
        the buffer and timer may already be cleared — we just return.
        The caption + reply context come from the **first** message in
        the album, matching Telegram's client-side conventions: clients
        only let users attach a caption to the first photo of an album.
        """
        buffer = self._media_group_buffers.pop(group_id, [])
        self._media_group_timers.pop(group_id, None)
        if not buffer:
            return
        if self._on_message is None:
            # Shutdown race: handler cleared before the timer fired.
            return

        first = buffer[0].message
        identity = self._make_identity(first)

        reply_to_id: str | None = None
        if first.reply_to_message is not None:
            reply_to_id = str(first.reply_to_message.message_id)

        attachments = tuple(
            Attachment(kind="image", data=p.data, mime_type=p.mime_type)
            for p in buffer
        )
        event = MessageEvent(
            identity=identity,
            text=buffer[0].caption or "",
            attachments=attachments,
            reply_to_message_id=reply_to_id,
        )
        try:
            await self._on_message(event)
        except Exception:
            logger.exception(
                "Telegram connector '%s': inbound handler raised on "
                "album (group_id=%s, %d photos)",
                self.instance_name, group_id, len(buffer),
            )

    async def _download_photo_bytes(
        self, message: "Message",
    ) -> bytes | None:
        """Download the largest :class:`PhotoSize` of ``message`` and
        return its bytes, or ``None`` if the photo was rejected at the
        edge (too large) or the download failed.

        Rejection reasons are communicated to the user via
        ``send_message``; download failures are logged and swallowed so
        the poll loop stays alive.
        """
        assert self._bot is not None  # noqa: S101 — guarded by caller
        if not message.photo:
            return None

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
            return None

        try:
            buf = await self._bot.download(largest)
        except TelegramAPIError:
            logger.exception(
                "Telegram connector '%s': photo download failed in chat %s",
                self.instance_name, message.chat.id,
            )
            return None
        except Exception:
            logger.exception(
                "Telegram connector '%s': unexpected error downloading photo",
                self.instance_name,
            )
            return None

        if buf is None:
            logger.debug(
                "Telegram connector '%s': download returned no buffer",
                self.instance_name,
            )
            return None

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
            return None
        finally:
            with contextlib.suppress(Exception):
                buf.close()

        return data or None

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
            send_caption = truncate_for_platform(
                caption, _TELEGRAM_MAX_CAPTION_LENGTH,
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
            send_caption = truncate_for_platform(
                caption, _TELEGRAM_MAX_CAPTION_LENGTH,
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

    # ── Approval workflow (Phase 10) ────────────────────────────────

    async def send_approval_prompt(
        self,
        *,
        admin_identity: Identity,
        approval_id: str,
        sender: Identity,
        preview: str,
    ) -> None:
        """Send an approval-prompt message with three inline buttons.

        The buttons carry ``callback_data`` encoded as
        ``approve:<choice>:<approval_id>`` — Telegram delivers the same
        string back to ``_on_callback_query`` when the admin taps a
        button. Telegram's 64-byte callback-data cap is comfortable:
        our format lands around 30 bytes.

        The prompt text includes the sender's display name and
        ``external_id`` so admins can decide without leaving the chat,
        plus a short preview of the pending message's content.
        """
        if self._bot is None:
            return

        try:
            chat_id = self._parse_chat_id(admin_identity.external_id)
        except ValueError:
            logger.warning(
                "Telegram connector '%s': cannot parse admin identity %r",
                self.instance_name, admin_identity.external_id,
            )
            return

        text = build_prompt_text(sender, preview)
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Allow once",
                        callback_data=encode_action(
                            APPROVAL_CHOICE_ALLOW_ONCE, approval_id,
                        ),
                    ),
                    InlineKeyboardButton(
                        text="🔓 Allow forever",
                        callback_data=encode_action(
                            APPROVAL_CHOICE_ALLOW_FOREVER, approval_id,
                        ),
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="🚫 Deny",
                        callback_data=encode_action(
                            APPROVAL_CHOICE_DENY, approval_id,
                        ),
                    ),
                ],
            ],
        )

        try:
            await self._bot.send_message(
                chat_id=chat_id, text=text, reply_markup=markup,
            )
        except TelegramAPIError:
            logger.exception(
                "Telegram connector '%s': failed to send approval prompt",
                self.instance_name,
            )

    async def _on_callback_query(self, callback: "CallbackQuery") -> None:
        """Route an approval button click to the :class:`ApprovalBroker`.

        Acks the query immediately (Telegram shows a loading spinner
        until ``callback.answer()`` fires) then parses the
        ``callback_data`` into ``(choice, approval_id)`` and calls
        ``broker.resolve``. The clicker's identity is synthesised from
        ``callback.from_user.id`` in Telegram's ``tg:user:*`` shape so
        ``ApprovalBroker.resolve``'s admin-membership check works.

        Silently ignores clicks when no broker is attached (operator
        config mistake) or the data doesn't parse.
        """
        data = callback.data or ""
        # Ack first — the spinner has a ~3 second patience window, and
        # broker.resolve() can take longer (DB write + reply send).
        with contextlib.suppress(TelegramAPIError):
            await callback.answer()

        broker = getattr(self, "_broker", None)
        if broker is None:
            logger.debug(
                "Telegram connector '%s': approval callback arrived but "
                "no broker is attached; ignoring",
                self.instance_name,
            )
            return

        decoded = decode_action(data)
        if decoded is None:
            logger.debug(
                "Telegram connector '%s': ignoring unrecognised "
                "callback_data %r",
                self.instance_name, data,
            )
            return
        choice, approval_id = decoded

        # Synthesise the clicker's identity in the same format as
        # _make_identity would for a DM — the broker checks identity
        # membership against the configured admin_external_ids set.
        clicker_user = callback.from_user
        if clicker_user is None:
            logger.warning(
                "Telegram connector '%s': approval callback without "
                "from_user; ignoring",
                self.instance_name,
            )
            return
        clicker_identity = Identity(
            platform=self.platform,
            external_id=f"tg:user:{clicker_user.id}",
            display_name=clicker_user.full_name or "",
            is_group=False,
            metadata={"user_id": clicker_user.id},
        )

        try:
            await broker.resolve(approval_id, choice, clicker_identity)
        except Exception:
            logger.exception(
                "Telegram connector '%s': broker.resolve raised",
                self.instance_name,
            )

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
