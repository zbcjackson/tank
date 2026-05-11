"""Slack connector implementation.

Uses slack_bolt's AsyncApp + AsyncSocketModeHandler. Socket Mode means
no public HTTP endpoint — the SDK opens a WebSocket to Slack via the
app-level token (``xapp-...``) and receives events as they're
delivered. The bot-level token (``xoxb-...``) authorises Web API calls
for sending, editing, and file uploads.

Supports text + single-image messages in both directions. Voice notes
are not supported in this release (see the plugin README for the full
matrix).

Message IDs are composite ``{channel}|{ts}`` strings so the Connector
contract's single ``message_id`` string can round-trip through
:meth:`edit`; Slack's Web API requires both pieces to identify a
message.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

import aiohttp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp
from slack_sdk.errors import SlackApiError
from tank_contracts.connector import (
    Attachment,
    Connector,
    ConnectorCapabilities,
    Identity,
    MessageEvent,
    SendResult,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger("SlackConnector")

# Slack's chat.update falls in the Tier 3 rate class — ~50 requests per
# minute per workspace. 1400ms ≈ 42/min sustained, well under the limit.
_DEFAULT_EDIT_INTERVAL_MS = 1400

# chat.postMessage accepts up to 40 000 characters of text.
_SLACK_MAX_MESSAGE_LENGTH = 40_000

# Captions on files.upload_v2 share the chat.postMessage limit.
_SLACK_MAX_CAPTION_LENGTH = 40_000

# Match the /api/upload + Telegram boundary. Slack allows much larger
# files in absolute terms, but bot interactions rarely need >25 MB.
_MAX_INBOUND_IMAGE_BYTES = 25 * 1024 * 1024

# Slack message subtypes we never want to react to — they represent
# state changes (edits, deletes, joins, leaves) rather than user speech.
_IGNORED_SUBTYPES = frozenset({
    "message_changed",
    "message_deleted",
    "channel_join",
    "channel_leave",
    "channel_topic",
    "channel_purpose",
    "channel_name",
    "thread_broadcast",
    "bot_message",
})

# Timeout for the Socket-Mode polling task to drain cleanly on shutdown.
_SHUTDOWN_TIMEOUT_S = 5.0


def _encode_msg_id(channel: str, ts: str) -> str:
    """Serialize Slack's ``(channel, ts)`` pair into a single message id.

    The Connector contract's ``message_id`` is a single string; Slack's
    Web API requires both pieces to identify a message. A pipe separator
    avoids collisions — Slack channel IDs and timestamps both consist of
    alphanumeric + dot characters.
    """
    return f"{channel}|{ts}"


def _decode_msg_id(msg_id: str) -> tuple[str, str]:
    """Inverse of :func:`_encode_msg_id`. Raises ``ValueError`` on malformed input."""
    channel, sep, ts = msg_id.partition("|")
    if not sep or not ts or not channel:
        raise ValueError(f"not a slack message id: {msg_id!r}")
    return channel, ts


def _classify_slack_error(exc: SlackApiError) -> SendResult:
    """Map a ``SlackApiError`` into our :class:`SendResult` shape.

    Rate-limited errors surface a ``Retry-After`` header — parse it into
    the conventional ``rate_limited:<seconds>`` token so the calling
    StreamConsumer can distinguish transient from terminal failures.
    Everything else falls through as a generic ``slack:<message>``.
    """
    response = getattr(exc, "response", None)
    if response is not None:
        # slack_sdk normalizes headers to lowercase in SlackResponse.
        headers = getattr(response, "headers", None) or {}
        retry_after = headers.get("retry-after") or headers.get("Retry-After")
        if retry_after:
            return SendResult(ok=False, error=f"rate_limited:{retry_after}")
        error_code = response.get("error") if hasattr(response, "get") else None
        if error_code == "ratelimited":
            return SendResult(ok=False, error="rate_limited:?")
    return SendResult(ok=False, error=f"slack:{exc}")


class SlackConnector(Connector):
    """Platform adapter for Slack (Socket Mode).

    One connector instance serves one Slack workspace. Deploy multiple
    instances with distinct ``(bot_token, app_token)`` pairs to cover
    multiple workspaces.
    """

    platform = "slack"

    def __init__(
        self,
        *,
        instance_name: str,
        bot_token: str,
        app_token: str,
    ) -> None:
        super().__init__(
            instance_name=instance_name,
            capabilities=ConnectorCapabilities(
                supports_edits=True,
                edit_min_interval_ms=_DEFAULT_EDIT_INTERVAL_MS,
                max_message_length=_SLACK_MAX_MESSAGE_LENGTH,
                supports_images_in=True,
                supports_images_out=True,
                supports_voice_in=False,
                supports_voice_out=False,
                supports_typing_indicator=False,
            ),
        )
        self._bot_token = bot_token
        self._app_token = app_token
        self._app: AsyncApp | None = None
        self._handler: AsyncSocketModeHandler | None = None
        self._task: asyncio.Task[None] | None = None
        # Lazy cache of Slack user_id → display_name. Unbounded (small by
        # nature — one entry per active user), no eviction.
        self._display_name_cache: dict[str, str] = {}

    # ── Lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        if self._connected:
            return
        self._app = AsyncApp(token=self._bot_token)
        # Register handlers before opening the socket so no events are
        # dropped between connect + registration.
        self._app.event("message")(self._on_message_event)
        self._handler = AsyncSocketModeHandler(self._app, self._app_token)
        self._task = asyncio.create_task(
            self._run_socket_mode(),
            name=f"slack-socket-{self.instance_name}",
        )
        self._connected = True
        logger.info("Slack connector '%s' started", self.instance_name)

    async def _run_socket_mode(self) -> None:
        """Run Socket Mode and surface unexpected crashes.

        Slack's SDK auto-reconnects on transient drops but bubbles up
        unrecoverable errors. We log loudly rather than leaving the
        connector silently dead.
        """
        assert self._handler is not None  # noqa: S101
        try:
            await self._handler.start_async()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Slack connector '%s' socket-mode task crashed",
                self.instance_name,
            )
            raise

    async def stop(self) -> None:
        if not self._connected:
            return
        if self._handler is not None:
            with contextlib.suppress(Exception):
                await self._handler.close_async()
        if self._task is not None:
            try:
                await asyncio.wait_for(
                    self._task, timeout=_SHUTDOWN_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                self._task.cancel()
                with contextlib.suppress(
                    asyncio.CancelledError, asyncio.TimeoutError, Exception,
                ):
                    await self._task
        self._app = None
        self._handler = None
        self._task = None
        self._connected = False
        logger.info("Slack connector '%s' stopped", self.instance_name)

    # ── Inbound ─────────────────────────────────────────────────────

    async def _on_message_event(self, event: dict, **_: Any) -> None:
        """Handle an inbound ``message`` event.

        Slack fires ``message`` for every channel state change (edits,
        deletes, joins, typing indicators, bot replies). Filter to
        original user messages only — anything with a ``subtype`` or
        ``bot_id`` set isn't a user speaking.
        """
        if self._on_message is None:
            return
        if event.get("bot_id"):
            return
        subtype = event.get("subtype")
        if subtype and subtype in _IGNORED_SUBTYPES:
            return
        # Subtypes we don't recognise are also suspicious; skip defensively.
        if subtype:
            logger.debug(
                "Slack connector '%s': dropping inbound with unknown "
                "subtype=%s",
                self.instance_name, subtype,
            )
            return

        identity = await self._make_identity(event)

        attachments: list[Attachment] = []
        for file_info in event.get("files") or []:
            att = await self._download_file(file_info)
            if att is not None:
                attachments.append(att)

        msg_event = MessageEvent(
            identity=identity,
            text=event.get("text") or "",
            attachments=tuple(attachments),
            reply_to_message_id=None,
            raw=event,
        )
        try:
            await self._on_message(msg_event)
        except Exception:
            logger.exception(
                "Slack connector '%s': inbound handler raised",
                self.instance_name,
            )

    async def _make_identity(self, event: dict) -> Identity:
        """Build an :class:`Identity` from a Slack ``message`` event.

        DMs (``channel_type="im"``) emit ``slack:user:{user_id}`` so
        allowlists can match individual people; group chats (channels,
        private channels, MPIMs) emit ``slack:channel:{channel_id}`` so
        allowlists match the room.

        :attr:`Identity.metadata` carries both ids plus thread context
        so outbound ``send`` can thread replies naturally.
        """
        user = event.get("user") or ""
        channel = event.get("channel") or ""
        channel_type = event.get("channel_type") or ""
        team = event.get("team") or ""
        thread_ts = event.get("thread_ts")
        ts = event.get("ts")

        is_dm = channel_type == "im"
        external_id = (
            f"slack:user:{user}" if is_dm else f"slack:channel:{channel}"
        )

        display_name = await self._resolve_display_name(user) if user else ""

        return Identity(
            platform=self.platform,
            external_id=external_id,
            display_name=display_name,
            is_group=not is_dm,
            metadata={
                "user": user,
                "channel": channel,
                "team": team,
                "channel_type": channel_type,
                # Replying should land in the same thread if the user
                # started one. If the inbound message is itself the root
                # of a thread (``thread_ts`` absent), we use the message's
                # own ``ts`` so Tank's first reply creates the thread.
                "thread_ts": thread_ts,
                "ts": ts,
            },
        )

    async def _resolve_display_name(self, user_id: str) -> str:
        """Lazy ``users.info`` lookup with in-memory cache.

        Slack events don't carry the user's display name, only their
        opaque ID. One ``users.info`` call on first sight gets us a
        human-friendly string; subsequent hits are free. Failures fall
        back to the raw user ID — not pretty, but the alternative is
        blocking inbound dispatch on a transient API error.
        """
        if user_id in self._display_name_cache:
            return self._display_name_cache[user_id]
        if self._app is None:
            return user_id

        try:
            resp = await self._app.client.users_info(user=user_id)
        except SlackApiError:
            logger.debug(
                "Slack connector '%s': users.info failed for %s; "
                "falling back to user id",
                self.instance_name, user_id,
                exc_info=True,
            )
            self._display_name_cache[user_id] = user_id
            return user_id

        user_obj = resp.get("user") or {}
        profile = user_obj.get("profile") or {}
        # Prefer display_name (Slack's user-chosen nickname), fall back
        # through real_name to the raw id.
        name = (
            profile.get("display_name")
            or profile.get("real_name")
            or user_obj.get("real_name")
            or user_id
        )
        self._display_name_cache[user_id] = name
        return name

    async def _download_file(self, file_info: dict) -> Attachment | None:
        """Fetch an inbound Slack file's bytes and wrap it as an Attachment.

        Only image files are currently handled — documents, audio, and
        other MIME types are dropped with a debug log. Slack files live
        at ``url_private`` and require a bot token in the ``Authorization``
        header; opening the URL unauthenticated returns HTML.

        Returns ``None`` for failures (missing url, non-image, oversized,
        network error) so the caller can skip silently without killing
        the rest of the message's attachments.
        """
        mime_type = file_info.get("mimetype") or ""
        if not mime_type.startswith("image/"):
            logger.debug(
                "Slack connector '%s': dropping non-image file mime=%s",
                self.instance_name, mime_type,
            )
            return None

        url = file_info.get("url_private") or file_info.get("url_private_download")
        if not url:
            return None

        size = file_info.get("size") or 0
        if size and size > _MAX_INBOUND_IMAGE_BYTES:
            logger.info(
                "Slack connector '%s': dropping oversized inbound image "
                "(%d bytes)",
                self.instance_name, size,
            )
            return None

        headers = {"Authorization": f"Bearer {self._bot_token}"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "Slack connector '%s': image download failed "
                            "(status=%d url=%s)",
                            self.instance_name, resp.status, url,
                        )
                        return None
                    # Enforce size cap even when the upstream size wasn't
                    # advertised — prevents a malicious/misconfigured
                    # Slack file from blowing out memory.
                    data = await resp.content.read(_MAX_INBOUND_IMAGE_BYTES + 1)
        except Exception:
            logger.exception(
                "Slack connector '%s': image download raised",
                self.instance_name,
            )
            return None

        if not data:
            return None
        if len(data) > _MAX_INBOUND_IMAGE_BYTES:
            logger.info(
                "Slack connector '%s': dropping inbound image that "
                "exceeded cap after read (%d bytes)",
                self.instance_name, len(data),
            )
            return None

        return Attachment(kind="image", data=data, mime_type=mime_type)

    # ── Outbound ────────────────────────────────────────────────────

    async def send(
        self,
        identity: Identity,
        text: str,
        *,
        reply_to: str | None = None,  # noqa: ARG002 — reserved for future use
        attachments: tuple[Attachment, ...] = (),
    ) -> SendResult:
        if self._app is None:
            return SendResult(ok=False, error="not connected")

        channel = identity.metadata.get("channel")
        if not channel:
            # DMs still populate channel in metadata via _make_identity,
            # so an empty channel here means the caller handed us an
            # Identity that wasn't built by this connector — bail.
            return SendResult(
                ok=False,
                error=f"bad_identity:missing_channel:{identity.external_id!r}",
            )

        image_att = next(
            (a for a in attachments if a.kind == "image"),
            None,
        )
        if image_att is not None:
            return await self._send_image(
                channel=channel,
                identity=identity,
                attachment=image_att,
                caption=text,
            )

        truncated = self._truncate(text, _SLACK_MAX_MESSAGE_LENGTH)
        post_kwargs: dict[str, Any] = {
            "channel": channel,
            "text": truncated,
        }
        # Reply in-thread if the inbound message carried thread context.
        # ``thread_ts`` can be None (not threaded) or the root ts (threaded).
        thread_ts = identity.metadata.get("thread_ts")
        if thread_ts:
            post_kwargs["thread_ts"] = thread_ts

        try:
            resp = await self._app.client.chat_postMessage(**post_kwargs)
        except SlackApiError as e:
            return _classify_slack_error(e)

        ts = resp.get("ts")
        resp_channel = resp.get("channel") or channel
        if not ts:
            return SendResult(ok=False, error="slack:missing_ts_in_response")
        return SendResult(
            ok=True,
            message_id=_encode_msg_id(resp_channel, ts),
        )

    async def _send_image(
        self,
        *,
        channel: str,
        identity: Identity,  # noqa: ARG002 — threaded send handled by caller
        attachment: Attachment,
        caption: str,
    ) -> SendResult:
        """Upload one image via ``files.upload_v2``.

        Slack's v2 upload is a two-step operation internally but the
        SDK hides that behind a single call. Bytes go via ``content``,
        URLs via a best-effort fallback (fetch + re-upload) — Slack
        doesn't accept arbitrary remote URLs the way Telegram does.
        """
        assert self._app is not None  # noqa: S101

        if isinstance(attachment.data, bytes):
            content = attachment.data
        elif isinstance(attachment.data, str):
            # URL case — fetch the bytes ourselves, then upload. Slack's
            # files.upload_v2 wants raw bytes, not a remote URL.
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(attachment.data) as resp:
                        if resp.status != 200:
                            return SendResult(
                                ok=False,
                                error=f"slack:url_fetch_failed:{resp.status}",
                            )
                        content = await resp.read()
            except Exception as e:
                return SendResult(ok=False, error=f"slack:url_fetch:{e}")
        else:
            return SendResult(
                ok=False,
                error=f"bad_attachment_data:{type(attachment.data).__name__}",
            )

        if not content:
            return SendResult(ok=False, error="empty_payload")

        send_caption: str | None = None
        if caption:
            send_caption = self._truncate(caption, _SLACK_MAX_CAPTION_LENGTH)

        filename = attachment.filename or "image.png"
        try:
            resp = await self._app.client.files_upload_v2(
                channel=channel,
                content=content,
                filename=filename,
                initial_comment=send_caption,
            )
        except SlackApiError as e:
            return _classify_slack_error(e)

        # files_upload_v2 returns a nested ``file`` / ``files`` shape; the
        # message timestamp lives under ``files[0].shares`` and is not
        # easily addressable for edits. Slack doesn't support
        # ``chat.update`` on uploaded-file messages anyway, so we don't
        # expose a message_id for image sends — the StreamConsumer only
        # edits text messages.
        return SendResult(ok=True, message_id=None)

    async def edit(
        self,
        identity: Identity,  # noqa: ARG002 — channel comes from message_id
        message_id: str,
        text: str,
    ) -> SendResult:
        if self._app is None:
            return SendResult(ok=False, error="not connected")

        try:
            channel, ts = _decode_msg_id(message_id)
        except ValueError:
            return SendResult(ok=False, error=f"bad_message_id:{message_id!r}")

        truncated = self._truncate(text, _SLACK_MAX_MESSAGE_LENGTH)

        try:
            await self._app.client.chat_update(
                channel=channel,
                ts=ts,
                text=truncated,
            )
        except SlackApiError as e:
            return _classify_slack_error(e)

        return SendResult(ok=True, message_id=message_id)

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _truncate(text: str, cap: int) -> str:
        """Truncate ``text`` to ``cap`` chars, replacing the tail with a
        single ellipsis so users see that trimming happened.

        Matches the Telegram connector's convention so both platforms
        truncate the same way.
        """
        if len(text) <= cap:
            return text
        return text[: cap - 1] + "…"
