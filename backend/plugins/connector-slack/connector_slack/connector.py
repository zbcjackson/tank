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
import re
import time
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

# How long a cached display-name entry stays fresh. 24h catches renames
# without burning ``users.info`` calls on every inbound message; lazy
# refresh + staggered expiry (each user's TTL starts at first sight)
# means no synchronised sweep storms the API.
_DISPLAY_NAME_TTL_S = 24 * 60 * 60

# Phase 10: shape of the ``action_id`` string on approval buttons.
# ``{prefix}:{choice}:{approval_id}`` — same three-part shape every
# connector uses. Choice literals are kept in sync (not imported) with
# :mod:`tank_backend.connectors.approval` so the plugin doesn't back-
# -depend on tank-backend. Slack's ``action_id`` has no length cap
# relevant to us at this shape.
_APPROVAL_ACTION_PREFIX = "approve"
_APPROVAL_ACTION_RE = re.compile(r"^approve:")
_CHOICE_ALLOW_ONCE = "allow_once"
_CHOICE_ALLOW_FOREVER = "allow_forever"
_CHOICE_DENY = "deny"


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
        mention_only: bool = False,
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
        self._mention_only = mention_only
        self._app: AsyncApp | None = None
        self._handler: AsyncSocketModeHandler | None = None
        self._task: asyncio.Task[None] | None = None
        # Resolved at ``start()`` via ``auth.test``. Needed for
        # mention-only filtering; stripped from inbound text before
        # forwarding so the LLM doesn't see Slack mention syntax.
        self._bot_user_id: str | None = None
        # Lazy cache of Slack ``user_id`` → ``(display_name, expiry_ts)``.
        # The TTL catches renames without burning a ``users.info`` call
        # per inbound message; staggered expiry (per-user starts at first
        # sight) avoids a synchronised refresh storm.
        self._display_name_cache: dict[str, tuple[str, float]] = {}

    # ── Lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        if self._connected:
            return
        self._app = AsyncApp(token=self._bot_token)

        # Resolve our own bot user id so mention-only filtering knows
        # which mention token to look for. Runs before we start receiving
        # events so inbound messages can't race past an un-resolved id.
        # If this fails, log and leave ``_bot_user_id=None`` — the
        # mention filter then drops all channel messages (safe failure:
        # silent-until-investigated beats accidental allow-all).
        if self._mention_only:
            try:
                auth_resp = await self._app.client.auth_test()
                self._bot_user_id = auth_resp.get("user_id")
                logger.info(
                    "Slack connector '%s': mention-only bound to %s",
                    self.instance_name, self._bot_user_id,
                )
            except Exception:
                logger.warning(
                    "Slack connector '%s': auth.test failed; mention-only "
                    "filter will drop all channel messages until this resolves. "
                    "Check the bot token.",
                    self.instance_name,
                    exc_info=True,
                )

        # Register handlers before opening the socket so no events are
        # dropped between connect + registration.
        self._app.event("message")(self._on_message_event)
        # Phase 10: ``action_id`` matches any approval button we rendered
        # via :meth:`send_approval_prompt`. slack_bolt's ``action``
        # decorator dispatches on the regex; our handler parses choice
        # + approval_id out of the id string.
        self._app.action(_APPROVAL_ACTION_RE)(self._on_approval_action)
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

        # Mention-only filter: in channels/groups/MPIMs, only forward
        # messages that mention us. DMs always forward (``channel_type == "im"``).
        # The filter strips the mention token from the text so the LLM
        # doesn't see Slack-specific ``<@U01ABCDEF>`` syntax.
        if self._mention_only and event.get("channel_type") != "im":
            text = event.get("text") or ""
            mention_token = (
                f"<@{self._bot_user_id}>" if self._bot_user_id else None
            )
            if mention_token is None or mention_token not in text:
                logger.debug(
                    "Slack connector '%s': mention-only dropping inbound "
                    "(channel=%s, bot=%s)",
                    self.instance_name,
                    event.get("channel"),
                    self._bot_user_id,
                )
                return
            # Clone the event with the mention stripped so downstream
            # identity construction and ``MessageEvent.text`` don't see
            # the ``<@U0BOTID>`` token.
            event = {
                **event,
                "text": text.replace(mention_token, "").strip(),
            }

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
        """Lazy ``users.info`` lookup with TTL-bounded cache.

        Slack events don't carry the user's display name, only their
        opaque ID. One ``users.info`` call on first sight gets us a
        human-friendly string; subsequent hits within
        ``_DISPLAY_NAME_TTL_S`` are free. Entries past the TTL are
        lazily refreshed on next access — renames propagate within a
        day without us polling every Slack workspace endlessly.

        Failures fall back to the raw user ID — not pretty, but the
        alternative is blocking inbound dispatch on a transient API
        error. Fallback entries are cached briefly too so a dead user
        doesn't re-trigger ``users.info`` on every message.
        """
        now = time.time()
        cached = self._display_name_cache.get(user_id)
        if cached is not None and cached[1] > now:
            return cached[0]

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
            self._display_name_cache[user_id] = (
                user_id, now + _DISPLAY_NAME_TTL_S,
            )
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
        self._display_name_cache[user_id] = (name, now + _DISPLAY_NAME_TTL_S)
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

    # ── Approval workflow (Phase 10) ────────────────────────────────

    async def send_approval_prompt(
        self,
        *,
        admin_identity: Identity,
        approval_id: str,
        sender: Identity,
        preview: str,
    ) -> None:
        """Send an approval-prompt message with three Block Kit buttons.

        Slack addresses DMs by user id via the ``chat.postMessage``
        ``channel`` parameter accepting either a channel id or a user
        id (Slack auto-resolves the DM channel). Our identity parser
        stores ``slack:user:{U}`` for DMs — we pass the user id
        directly and Slack handles the rest.

        Each button carries an ``action_id`` encoded as
        ``approve:<choice>:<approval_id>``. Slack delivers that same
        string back to :meth:`_on_approval_action` when the admin
        clicks — no length cap we need to worry about at this shape.
        """
        if self._app is None:
            return

        # Extract the channel/user id from the admin identity's
        # ``external_id``. Slack DMs are ``slack:user:{U}`` → the
        # ``U...`` id works directly as the ``channel`` arg because
        # Slack's API accepts user ids there. Channel admins (unusual
        # but valid) are ``slack:channel:{C}``.
        ext_id = admin_identity.external_id
        _, _, dest = ext_id.rpartition(":")
        if not dest:
            logger.warning(
                "Slack connector '%s': unparseable admin external_id %r",
                self.instance_name, ext_id,
            )
            return

        sender_label = (
            f"{sender.display_name} ({sender.external_id})"
            if sender.display_name
            else sender.external_id
        )
        # Block Kit structure — section with context, then three button
        # actions. Matches Slack's canonical "approval modal" shape;
        # users who expect the classic inline buttons will find it
        # familiar.
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*New sender wants to talk to me:*\n"
                        f"• {sender_label}\n"
                        f"• message preview: {preview}"
                    ),
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✅ Allow once"},
                        "action_id": (
                            f"{_APPROVAL_ACTION_PREFIX}:{_CHOICE_ALLOW_ONCE}"
                            f":{approval_id}"
                        ),
                        "value": approval_id,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "🔓 Allow forever"},
                        "action_id": (
                            f"{_APPROVAL_ACTION_PREFIX}:{_CHOICE_ALLOW_FOREVER}"
                            f":{approval_id}"
                        ),
                        "value": approval_id,
                    },
                    {
                        "type": "button",
                        "style": "danger",
                        "text": {"type": "plain_text", "text": "🚫 Deny"},
                        "action_id": (
                            f"{_APPROVAL_ACTION_PREFIX}:{_CHOICE_DENY}"
                            f":{approval_id}"
                        ),
                        "value": approval_id,
                    },
                ],
            },
        ]

        try:
            await self._app.client.chat_postMessage(
                channel=dest,
                text="New sender wants to talk to me.",  # fallback for non-Block-Kit clients
                blocks=blocks,
            )
        except SlackApiError:
            logger.exception(
                "Slack connector '%s': failed to send approval prompt",
                self.instance_name,
            )

    async def _on_approval_action(
        self, ack: Any, body: dict, **_: Any,
    ) -> None:
        """Route an approval button click to the :class:`ApprovalBroker`.

        slack_bolt enforces a 3-second ack window; we call ``ack()``
        immediately then run broker work async afterwards. The broker's
        identity check rejects non-admin clickers, so the public nature
        of Slack's buttons doesn't compromise the gate.

        Silently ignores clicks when no broker is attached or the
        action data doesn't parse.
        """
        # Ack first — Slack shows a "failed to complete" banner if
        # this doesn't happen inside 3 seconds.
        with contextlib.suppress(Exception):
            await ack()

        broker = getattr(self, "_broker", None)
        if broker is None:
            logger.debug(
                "Slack connector '%s': approval action arrived but "
                "no broker is attached; ignoring",
                self.instance_name,
            )
            return

        # slack_bolt hands us ``body`` with ``actions: [{action_id, ...}]``
        # and ``user: {id: "U..."}``. Pull both.
        actions = body.get("actions") or []
        if not actions:
            logger.debug(
                "Slack connector '%s': approval body had no actions",
                self.instance_name,
            )
            return
        action_id = actions[0].get("action_id", "")
        parts = action_id.split(":", 2)
        if len(parts) != 3 or parts[0] != _APPROVAL_ACTION_PREFIX:
            logger.debug(
                "Slack connector '%s': ignoring unrecognised action_id %r",
                self.instance_name, action_id,
            )
            return
        _, choice, approval_id = parts
        if not approval_id:
            return

        user_info = body.get("user") or {}
        clicker_user_id = user_info.get("id")
        if not clicker_user_id:
            logger.warning(
                "Slack connector '%s': approval action body missing user.id",
                self.instance_name,
            )
            return

        clicker_identity = Identity(
            platform=self.platform,
            external_id=f"slack:user:{clicker_user_id}",
            display_name=(user_info.get("name") or ""),
            is_group=False,
            metadata={"user": clicker_user_id},
        )

        try:
            await broker.resolve(approval_id, choice, clicker_identity)
        except Exception:
            logger.exception(
                "Slack connector '%s': broker.resolve raised",
                self.instance_name,
            )

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
