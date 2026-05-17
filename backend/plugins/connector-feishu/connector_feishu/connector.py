"""Feishu / Lark connector implementation.

Uses ``lark-oapi``'s WebSocket long-connection client (``lark.ws.Client``)
— same shape as the Slack Socket Mode connector. No public webhook URL
required: the SDK opens a long-lived WS to Feishu and dispatches inbound
events to handlers we register.

A wrinkle worth flagging: ``lark.ws.Client.start()`` is *synchronous* —
it calls ``loop.run_until_complete`` on a private module-global event
loop and blocks the calling thread forever. We can't run that on the
main asyncio loop without deadlocking the rest of Tank, so the lark
client lives on a dedicated background thread spawned via
``asyncio.to_thread``. The :class:`BackgroundTaskRunner` wraps the
to_thread coroutine; on shutdown we ask the lark client to close,
which exits its private loop and lets the thread join.

Inbound events arrive on the lark thread; we hop them back to the main
loop via :func:`asyncio.run_coroutine_threadsafe` so handlers run in
the same event loop as ``send`` / ``edit`` / approval-broker calls.

Phase 20 v1 surface:

- Text inbound + outbound (DMs and groups)
- Voice notes inbound (Feishu's ``audio`` msg_type)
- Image attachments in both directions
- Per-instance allowlist + REQUIRE_APPROVAL via interactive cards

Message IDs are the lark message_id (``om_...``) directly — the lark
patch API takes those, no compositing needed.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import TYPE_CHECKING, Any

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    P2ImMessageReceiveV1,
    PatchMessageRequest,
    PatchMessageRequestBody,
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
    APPROVAL_CHOICE_ALLOW_FOREVER,
    APPROVAL_CHOICE_ALLOW_ONCE,
    APPROVAL_CHOICE_DENY,
    BackgroundTaskRunner,
    build_outcome_text,
    build_prompt_text,
    decode_action,
    encode_action,
    truncate_for_platform,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger("FeishuConnector")


# Feishu's hard cap on text messages is 30 000 characters. Captions
# on media messages are smaller (~1500); we let the platform clamp.
_FEISHU_MAX_MESSAGE_LENGTH = 30_000

# Feishu's send rate limit is roughly 50/min/app. ~1100ms keeps
# streaming edits comfortably under without feeling sluggish.
_DEFAULT_EDIT_INTERVAL_MS = 1100

# Match the /api/upload + other-connector boundary. Feishu permits
# larger uploads in absolute terms; bot interactions rarely benefit.
_MAX_INBOUND_IMAGE_BYTES = 25 * 1024 * 1024
_MAX_INBOUND_AUDIO_BYTES = 25 * 1024 * 1024

# Timeout for the WebSocket task to drain cleanly on shutdown.
_SHUTDOWN_TIMEOUT_S = 5.0


def _classify_lark_error(exc: Exception) -> SendResult:
    """Map a lark SDK error into our :class:`SendResult` shape.

    lark exposes errors as plain ``ClientException`` / generic
    exceptions plus structured response codes on the response object;
    we surface the message for diagnostics and prefix with ``feishu:``
    so logs are greppable.
    """
    return SendResult(ok=False, error=f"feishu:{exc}")


class FeishuConnector(Connector):
    """Platform adapter for Feishu / Lark (long-connection WebSocket).

    One connector instance serves one Feishu app. Deploy multiple
    instances with distinct ``(app_id, app_secret)`` pairs to cover
    multiple tenants.
    """

    platform = "feishu"

    def __init__(
        self,
        instance_name: str,
        *,
        app_id: str,
        app_secret: str,
    ) -> None:
        super().__init__(
            instance_name=instance_name,
            capabilities=ConnectorCapabilities(
                supports_edits=True,
                edit_min_interval_ms=_DEFAULT_EDIT_INTERVAL_MS,
                max_message_length=_FEISHU_MAX_MESSAGE_LENGTH,
                supports_images_in=True,
                supports_images_out=True,
                # Voice-in via lark's audio msg_type → Tank's ASR.
                # Voice outbound deferred (separate file_key upload
                # path; see README "What doesn't work yet").
                supports_voice_in=True,
                supports_voice_out=True,
                # Feishu has no public typing-indicator API.
                supports_typing_indicator=False,
            ),
        )
        self._app_id = app_id
        self._app_secret = app_secret
        # API client (sync REST wrapper; we call the ``async``/``a*``
        # methods on its sub-resources for non-blocking sends).
        self._api: lark.Client | None = None
        # WebSocket client (long-connection event receiver). Built in
        # ``start`` so the event handler picks up the bound methods.
        self._ws: lark.ws.Client | None = None
        # The OS thread that runs lark's blocking ``start()`` and the
        # asyncio loop owned by that thread. We monkey-patch lark's
        # module-global ``loop`` to this thread-local one so the SDK
        # doesn't try to ``run_until_complete`` Tank's main loop. See
        # ``_run_ws`` for the full reasoning.
        self._ws_thread: Any = None
        self._ws_loop: asyncio.AbstractEventLoop | None = None
        # Capture the main event loop so the WS-thread callback can
        # post coroutines back onto it via run_coroutine_threadsafe.
        self._main_loop: asyncio.AbstractEventLoop | None = None
        # Lifecycle coordinator — same shape Slack/Discord use.
        self._runner = BackgroundTaskRunner(
            instance_name=instance_name,
            platform=self.platform,
            shutdown_timeout_s=_SHUTDOWN_TIMEOUT_S,
        )

    # ── Lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        if self._connected:
            return
        # Capture the main loop so WS-thread callbacks can hop back.
        self._main_loop = asyncio.get_running_loop()

        # Build the API client first — needed by approval handlers
        # too, not just outbound send.
        self._api = (
            lark.Client.builder()
            .app_id(self._app_id)
            .app_secret(self._app_secret)
            .log_level(lark.LogLevel.WARNING)
            .build()
        )

        # Event handler: register the inbound message + card-action
        # callbacks. ``encrypt_key`` and ``verification_token`` are
        # only needed for HTTP webhook delivery; long-connection mode
        # ignores them (we pass empty strings).
        # ``register_p2_card_action_trigger`` is typed in lark's stubs
        # as a sync handler returning ``P2CardActionTriggerResponse``,
        # but in practice the SDK accepts handlers that return ``None``
        # (the response is built later from the message edit). The
        # ``# type: ignore`` keeps the actual runtime contract intact
        # while satisfying pyright; remove if lark's stubs ever
        # broaden the callback type.
        event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._on_message_event)
            .register_p2_im_message_message_read_v1(self._on_message_read)
            .register_p2_card_action_trigger(self._on_card_action)  # type: ignore[arg-type]
            .build()
        )

        self._ws = lark.ws.Client(
            self._app_id,
            self._app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.WARNING,
        )

        # ``ws.start()`` blocks the calling thread on its own private
        # event loop. Run it in a worker thread; the runner waits for
        # task completion on shutdown but the actual stop signal is
        # the lark client's internal disconnect (see ``stop``).
        self._runner.spawn(self._run_ws())
        self._connected = True
        logger.info("Feishu connector '%s' started", self.instance_name)

    async def _run_ws(self) -> None:
        """Run the lark WebSocket client on a dedicated thread with
        its own asyncio loop.

        ``lark.ws.Client.start`` calls ``loop.run_until_complete`` on
        a *module-global* ``loop`` symbol that lark grabs at import
        time via ``asyncio.get_event_loop()``. When Tank imports lark
        before its main loop has finished initialising, the captured
        ``loop`` ends up being Tank's main loop — so when the SDK
        later tries to call ``run_until_complete`` on it, Python
        raises ``RuntimeError: this event loop is already running``.

        The fix: spawn a real OS thread, create a fresh asyncio loop
        inside it, monkey-patch ``lark_oapi.ws.client.loop`` to that
        thread-local loop *before* calling ``self._ws.start()``. The
        SDK then runs entirely on the thread's loop and our main loop
        stays free for ``send`` / ``edit`` / approval-broker work.

        ``asyncio.to_thread`` is the cleaner-looking alternative but
        it doesn't change which event loop ``loop.run_until_complete``
        targets — it only moves the *call* to a worker. The shared
        global stays the main loop.
        """
        import threading

        import lark_oapi.ws.client as lark_ws_module

        assert self._ws is not None  # noqa: S101
        ws = self._ws

        loop_ready = threading.Event()
        thread_loop_holder: list[asyncio.AbstractEventLoop] = []

        def _runner() -> None:
            """Body of the lark thread.

            Creates a private loop, swaps it in for lark's module-
            global, makes it available to ``stop()`` via the holder,
            then enters the SDK's blocking ``start()`` call. When the
            connection closes the loop drains and the thread exits.
            """
            thread_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(thread_loop)
            # Monkey-patch lark's module-global loop. Save the original
            # so other lark.ws.Client instances elsewhere in the
            # process aren't collateral damage; we don't currently
            # ship any, but the swap-restore pattern is hygienic.
            original_loop = lark_ws_module.loop
            lark_ws_module.loop = thread_loop
            thread_loop_holder.append(thread_loop)
            loop_ready.set()
            try:
                ws.start()
            except Exception:
                logger.exception(
                    "Feishu connector '%s': lark WS client crashed",
                    self.instance_name,
                )
            finally:
                lark_ws_module.loop = original_loop
                thread_loop.close()

        thread = threading.Thread(
            target=_runner,
            name=f"feishu-ws-{self.instance_name}",
            daemon=True,
        )
        thread.start()

        # Stash the thread + its loop so ``stop()`` can ask the lark
        # client to disconnect on the right loop. ``loop_ready`` fires
        # before ``start()`` blocks, so the holder is populated by
        # the time we return.
        loop_ready.wait()
        self._ws_thread = thread
        self._ws_loop = thread_loop_holder[0]

        # Block this coroutine until the thread exits — same
        # lifecycle BackgroundTaskRunner expects from the awaitable
        # it owns. The wait happens on the main loop's executor pool,
        # so it doesn't stall anything.
        await asyncio.to_thread(thread.join)

    async def stop(self) -> None:
        if not self._connected:
            return

        # Signal the lark client to disconnect on the thread-owned
        # loop ``_run_ws`` set up. ``_disconnect`` mutates client
        # state that lives on that loop, so it MUST run there — not
        # on Tank's main loop. ``run_coroutine_threadsafe`` posts
        # the coroutine onto the target loop and returns a future we
        # don't need to await: the lark thread picks it up, exits
        # its ``start()`` blocker, and the thread joins via the
        # ``thread.join`` we already await inside ``_run_ws``.
        if self._ws is not None and self._ws_loop is not None:
            with contextlib.suppress(Exception):
                if self._ws_loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        self._ws._disconnect(),  # noqa: SLF001
                        self._ws_loop,
                    )

        # Drain the worker thread via the shared runner.
        await self._runner.drain()

        self._api = None
        self._ws = None
        self._ws_thread = None
        self._ws_loop = None
        self._main_loop = None
        self._connected = False
        logger.info("Feishu connector '%s' stopped", self.instance_name)

    # ── Inbound ─────────────────────────────────────────────────────

    def _on_message_read(self, data: Any) -> None:
        """No-op handler for ``im.message.message_read_v1`` events.

        Feishu pushes a read-receipt event whenever a user reads a
        message we sent. lark-oapi's dispatcher rejects unhandled
        event types with an ERROR log per receipt, which floods the
        log under any non-trivial conversation. We don't track read
        receipts, so register an explicit no-op to silence the noise.
        Future work could surface read state to the UI via the
        existing ``ui_message`` bus event; for now, drop on the floor.
        """
        return None

    def _on_message_event(self, data: P2ImMessageReceiveV1) -> None:
        """Lark dispatches inbound messages to this callback on the
        WS thread. We hop back to the main loop and forward to the
        async handler so all message processing runs on one loop.
        """
        if self._main_loop is None or self._on_message is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._dispatch_message(data),
                self._main_loop,
            )
        except Exception:
            logger.exception(
                "Feishu connector '%s': failed to hop inbound to main loop",
                self.instance_name,
            )

    async def _dispatch_message(self, data: P2ImMessageReceiveV1) -> None:
        """Translate a lark event into a :class:`MessageEvent` and
        forward to the framework's bound handler.

        Filters out messages from bots (including our own) so we
        don't loop on our own replies. Other apps' bots are dropped
        for the same conservative reason Slack/Discord drop them —
        opt-in bot-to-bot chains can come later via a flag.
        """
        if data.event is None or data.event.message is None:
            return
        msg = data.event.message
        sender = data.event.sender

        # Skip messages without a sender (system events, edits, etc.).
        if sender is None or sender.sender_id is None:
            return
        # Skip bot-authored messages — same conservative default as
        # the other connectors. ``sender_type`` is "user" for humans
        # and "app" / "bot" for bots; treat anything non-user as a
        # bot to avoid loops with our own replies.
        if sender.sender_type and sender.sender_type != "user":
            return

        # Build identity. DMs and groups land on different prefixes
        # so the SessionMapper can distinguish them — same shape the
        # other connectors use (slack:user vs slack:channel).
        if msg.chat_type == "p2p":
            external_id = f"feishu:user:{sender.sender_id.open_id}"
            is_group = False
        else:
            external_id = f"feishu:chat:{msg.chat_id}"
            is_group = True

        identity = Identity(
            platform=self.platform,
            external_id=external_id,
            display_name="",  # Feishu doesn't ship display name on the event
            is_group=is_group,
            metadata={
                "open_id": sender.sender_id.open_id or "",
                "chat_id": msg.chat_id or "",
                "chat_type": msg.chat_type or "",
                "message_id": msg.message_id or "",
                "tenant_key": sender.tenant_key or "",
            },
        )

        # Decode content. Feishu sends ``content`` as a JSON string;
        # the inner shape depends on ``message_type``.
        try:
            content = json.loads(msg.content) if msg.content else {}
        except json.JSONDecodeError:
            logger.warning(
                "Feishu connector '%s': non-JSON content for msg %s",
                self.instance_name, msg.message_id,
            )
            return

        text = ""
        attachments: list[Attachment] = []
        if msg.message_type == "text":
            text = content.get("text", "")
        elif msg.message_type == "image":
            image_key = content.get("image_key", "")
            image_bytes = await self._download_resource(
                msg.message_id or "", image_key, "image",
            )
            if image_bytes is not None:
                attachments.append(Attachment(
                    kind="image", data=image_bytes, mime_type="image/jpeg",
                ))
        elif msg.message_type == "audio":
            file_key = content.get("file_key", "")
            audio_bytes = await self._download_resource(
                msg.message_id or "", file_key, "file",
            )
            if audio_bytes is not None:
                # Feishu voice notes are typically opus-in-ogg.
                attachments.append(Attachment(
                    kind="audio", data=audio_bytes, mime_type="audio/ogg",
                ))
        else:
            logger.debug(
                "Feishu connector '%s': dropping unsupported msg_type=%s",
                self.instance_name, msg.message_type,
            )
            return

        # Forward the message directly — no bundling. Feishu delivers
        # text and image as separate events; each becomes its own turn.
        # Users who want text+image in one turn should use Feishu's
        # rich-text editor to compose a single message containing both.
        await self._forward_message(identity, text, tuple(attachments))

    async def _forward_message(
        self,
        identity: Identity,
        text: str,
        attachments: tuple[Attachment, ...],
    ) -> None:
        """Forward a message to the framework handler.

        Logs the inbound identity at INFO for open_id discovery.
        """
        assert self._on_message is not None  # noqa: S101
        logger.info(
            "Feishu connector '%s' inbound from %s (msg_type=%s)",
            self.instance_name,
            identity.external_id,
            "image" if attachments else "text",
        )
        try:
            await self._on_message(MessageEvent(
                identity=identity,
                text=text,
                attachments=attachments,
                reply_to_message_id=None,
            ))
        except Exception:
            logger.exception(
                "Feishu connector '%s': inbound handler raised",
                self.instance_name,
            )

    async def _download_resource(
        self, message_id: str, file_key: str, file_type: str,
    ) -> bytes | None:
        """Fetch a Feishu-hosted resource (image / audio / file).

        Caps at the per-kind size limit. Returns ``None`` for any
        failure so the caller can skip without killing the rest of
        the message.
        """
        if not message_id or not file_key or self._api is None:
            return None
        try:
            from lark_oapi.api.im.v1 import GetMessageResourceRequest

            req = (
                GetMessageResourceRequest.builder()
                .message_id(message_id)
                .file_key(file_key)
                .type(file_type)
                .build()
            )
            assert self._api is not None  # noqa: S101
            resp = await self._api.im.v1.message_resource.aget(req)  # pyright: ignore[reportOptionalMemberAccess]
            if not resp.success():
                logger.warning(
                    "Feishu connector '%s': resource fetch failed "
                    "(code=%s msg=%s)",
                    self.instance_name, resp.code, resp.msg,
                )
                return None
            file_bytes = resp.file.read() if resp.file is not None else b""
            cap = (
                _MAX_INBOUND_AUDIO_BYTES if file_type == "file"
                else _MAX_INBOUND_IMAGE_BYTES
            )
            if len(file_bytes) > cap:
                logger.info(
                    "Feishu connector '%s': dropping oversized %s "
                    "(%d bytes > %d cap)",
                    self.instance_name, file_type, len(file_bytes), cap,
                )
                return None
            return file_bytes
        except Exception:
            logger.exception(
                "Feishu connector '%s': resource fetch raised",
                self.instance_name,
            )
            return None

    # ── Outbound ────────────────────────────────────────────────────

    async def send(
        self,
        identity: Identity,
        text: str,
        *,
        reply_to: str | None = None,  # noqa: ARG002 — reserved for future use
        attachments: tuple[Attachment, ...] = (),
    ) -> SendResult:
        """Send a text message (with optional attachments) to a Feishu chat."""
        if self._api is None:
            return SendResult(ok=False, error="feishu:not_connected")

        receive_id, receive_id_type = self._resolve_receive(identity)
        if not receive_id:
            return SendResult(
                ok=False, error="feishu:identity_missing_target",
            )

        if attachments:
            return await self._send_with_attachments(
                identity, text, receive_id, receive_id_type, attachments,
            )

        truncated = truncate_for_platform(text, _FEISHU_MAX_MESSAGE_LENGTH)
        body = (
            CreateMessageRequestBody.builder()
            .receive_id(receive_id)
            .msg_type("text")
            .content(json.dumps({"text": truncated}, ensure_ascii=False))
            .build()
        )
        req = (
            CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(body)
            .build()
        )
        try:
            assert self._api is not None  # noqa: S101
            resp = await self._api.im.v1.message.acreate(req)  # pyright: ignore[reportOptionalMemberAccess]
            if not resp.success():
                return SendResult(
                    ok=False,
                    error=f"feishu:{resp.code}:{resp.msg}",
                )
            message_id = ""
            if resp.data is not None:
                message_id = resp.data.message_id or ""
            return SendResult(ok=True, message_id=message_id)
        except Exception as exc:
            logger.exception(
                "Feishu connector '%s': send raised", self.instance_name,
            )
            return _classify_lark_error(exc)

    async def _send_with_attachments(
        self,
        identity: Identity,  # noqa: ARG002 — reserved for richer routing
        text: str,
        receive_id: str,
        receive_id_type: str,
        attachments: tuple[Attachment, ...],
    ) -> SendResult:
        """Send the first image attachment. Multi-image batches are
        dropped past the first because Feishu's send-message API only
        accepts one image per message (you'd need a card with multiple
        elements; that's deferred).
        """
        # Only image attachments are supported on outbound today.
        image_atts = [a for a in attachments if a.kind == "image"]
        if not image_atts:
            # Fall back to text-only if no images survive (audio-out
            # is deferred to a later phase).
            return await self.send(
                identity=Identity(
                    platform=self.platform,
                    external_id=receive_id if receive_id_type == "open_id"
                    else f"feishu:chat:{receive_id}",
                    metadata={},
                ),
                text=text,
            )

        att = image_atts[0]
        # ``data`` may be raw bytes or a URL string. Feishu's send API
        # needs an ``image_key`` we get by uploading bytes. When the
        # source is a URL (e.g. from ``echo_image``), download first.
        if isinstance(att.data, bytes):
            image_bytes = att.data
        elif isinstance(att.data, str) and att.data.startswith(("http://", "https://")):
            image_bytes = await self._download_url_image(att.data)
            if image_bytes is None:
                return SendResult(
                    ok=False, error="feishu:url_image_download_failed",
                )
        else:
            logger.warning(
                "Feishu connector '%s': unsupported image data type %s",
                self.instance_name, type(att.data).__name__,
            )
            return SendResult(
                ok=False, error="feishu:unsupported_image_source",
            )

        try:
            image_key = await self._upload_image(image_bytes)
        except Exception as exc:
            logger.exception(
                "Feishu connector '%s': image upload raised",
                self.instance_name,
            )
            return _classify_lark_error(exc)
        if not image_key:
            return SendResult(ok=False, error="feishu:upload_failed")

        # Caption rides on a separate text message because Feishu's
        # image msg_type doesn't carry inline captions. Most platforms
        # render captions next to the image; Feishu doesn't, so we
        # send text-then-image (the order matches what Phase 15's
        # caption-on-first-attachment expects).
        if text:
            text_resp = await self.send(
                identity=Identity(
                    platform=self.platform,
                    external_id=receive_id if receive_id_type == "open_id"
                    else f"feishu:chat:{receive_id}",
                    metadata={},
                ),
                text=text,
            )
            if not text_resp.ok:
                return text_resp

        body = (
            CreateMessageRequestBody.builder()
            .receive_id(receive_id)
            .msg_type("image")
            .content(json.dumps({"image_key": image_key}))
            .build()
        )
        req = (
            CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(body)
            .build()
        )
        try:
            assert self._api is not None  # noqa: S101
            resp = await self._api.im.v1.message.acreate(req)  # pyright: ignore[reportOptionalMemberAccess]
            if not resp.success():
                return SendResult(
                    ok=False, error=f"feishu:{resp.code}:{resp.msg}",
                )
            message_id = (
                resp.data.message_id if resp.data is not None else ""
            ) or ""
            return SendResult(ok=True, message_id=message_id)
        except Exception as exc:
            return _classify_lark_error(exc)

    async def _download_url_image(self, url: str) -> bytes | None:
        """Download an image from a public URL for outbound upload.

        Used when ``echo_image`` or the chart tool returns a public
        ``http(s)://`` URL as the image source rather than raw bytes.
        Downloads the image, caps at ``_MAX_INBOUND_IMAGE_BYTES``, and
        returns the bytes for ``_upload_image``. Returns ``None`` on
        any failure so the caller can surface a clean error.
        """
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "Feishu connector '%s': URL image download "
                            "failed (status=%d url=%s)",
                            self.instance_name, resp.status, url,
                        )
                        return None
                    data = await resp.content.read(_MAX_INBOUND_IMAGE_BYTES + 1)
        except Exception:
            logger.exception(
                "Feishu connector '%s': URL image download raised (url=%s)",
                self.instance_name, url,
            )
            return None

        if not data:
            return None
        if len(data) > _MAX_INBOUND_IMAGE_BYTES:
            logger.info(
                "Feishu connector '%s': URL image too large (%d bytes)",
                self.instance_name, len(data),
            )
            return None
        return data

    async def _upload_image(self, data: bytes) -> str:
        """Upload PNG/JPEG bytes to Feishu, return ``image_key``.

        Feishu's outbound image messages address content by
        ``image_key``: the bot uploads bytes to ``client.im.v1.image.acreate``,
        receives a key, then sends a ``msg_type="image"`` message
        whose body is ``{"image_key": ...}``. ``image_type="message"``
        is the only value that works for chat messages (``"avatar"``
        is for the app's own icon).

        The SDK's ``image`` builder field expects an ``IO[Any]`` —
        we wrap the raw bytes in :class:`io.BytesIO` so the upload
        machinery can stream from a file-like object without us
        materialising a temp file on disk.

        Returns the image_key string on success, empty string on
        failure. The caller (``_send_with_attachments``) checks for
        empty and surfaces ``feishu:upload_failed`` to the user
        instead of a 500.
        """
        if self._api is None or not data:
            return ""

        from io import BytesIO

        from lark_oapi.api.im.v1 import (
            CreateImageRequest,
            CreateImageRequestBody,
        )

        body = (
            CreateImageRequestBody.builder()
            .image_type("message")
            .image(BytesIO(data))
            .build()
        )
        req = (
            CreateImageRequest.builder()
            .request_body(body)
            .build()
        )
        try:
            resp = await self._api.im.v1.image.acreate(req)  # pyright: ignore[reportOptionalMemberAccess]
        except Exception:
            logger.exception(
                "Feishu connector '%s': image upload raised",
                self.instance_name,
            )
            return ""
        if not resp.success():
            logger.warning(
                "Feishu connector '%s': image upload failed "
                "(code=%s msg=%s)",
                self.instance_name, resp.code, resp.msg,
            )
            return ""
        if resp.data is None or not resp.data.image_key:
            logger.warning(
                "Feishu connector '%s': image upload succeeded but "
                "no image_key in response",
                self.instance_name,
            )
            return ""
        return resp.data.image_key

    async def edit(
        self,
        identity: Identity,  # noqa: ARG002 — message_id is sufficient for Feishu
        message_id: str,
        text: str,
    ) -> SendResult:
        """Edit a message's text via lark's update API.

        Used by the streaming path (StreamConsumer's edit cadence).
        Feishu has two distinct edit endpoints — ``apatch`` only works
        on **interactive cards** (``msg_type=interactive``), and
        ``aupdate`` works on **text** messages. The original
        implementation used ``apatch`` which 400'd every text edit
        with ``230001: This message is NOT a card``; switching to
        ``aupdate`` is the right path for the streaming-text use case.
        Card edits (the approval-prompt outcome rewrite) still use
        ``apatch`` because that endpoint is card-only.

        ``identity`` is unused: Feishu's update API addresses messages
        by the ``om_*`` message_id directly; the chat the message
        lives in is implicit. The base contract still includes it so
        platforms that need both (Slack's ``{channel}|{ts}`` style)
        have somewhere to read.
        """
        if self._api is None:
            return SendResult(ok=False, error="feishu:not_connected")
        if not message_id:
            return SendResult(ok=False, error="feishu:no_message_id")

        from lark_oapi.api.im.v1 import (
            UpdateMessageRequest,
            UpdateMessageRequestBody,
        )

        truncated = truncate_for_platform(text, _FEISHU_MAX_MESSAGE_LENGTH)
        body = (
            UpdateMessageRequestBody.builder()
            .msg_type("text")
            .content(json.dumps({"text": truncated}, ensure_ascii=False))
            .build()
        )
        req = (
            UpdateMessageRequest.builder()
            .message_id(message_id)
            .request_body(body)
            .build()
        )
        try:
            assert self._api is not None  # noqa: S101
            resp = await self._api.im.v1.message.aupdate(req)  # pyright: ignore[reportOptionalMemberAccess]
            if not resp.success():
                return SendResult(
                    ok=False, error=f"feishu:{resp.code}:{resp.msg}",
                )
            return SendResult(ok=True, message_id=message_id)
        except Exception as exc:
            return _classify_lark_error(exc)

    async def send_voice(
        self,
        identity: Identity,
        data: bytes,
        *,
        mime_type: str = "audio/ogg",
        caption: str = "",
    ) -> SendResult:
        """Send a voice note via Feishu's file upload + audio message.

        Feishu's audio messages require a two-step flow:
        1. Upload the audio bytes via ``client.im.v1.file.acreate``
           with ``file_type="opus"`` to get a ``file_key``.
        2. Send a message with ``msg_type="audio"`` carrying the
           ``file_key``.

        The ``_VoiceDispatcher`` produces Ogg/Opus bytes via
        ``encode_pcm_to_opus``; Feishu's audio player handles that
        format natively.
        """
        if self._api is None:
            return SendResult(ok=False, error="feishu:not_connected")
        if not data:
            return SendResult(ok=False, error="feishu:empty_payload")

        receive_id, receive_id_type = self._resolve_receive(identity)
        if not receive_id:
            return SendResult(ok=False, error="feishu:identity_missing_target")

        # Step 1: Upload audio file
        from io import BytesIO

        from lark_oapi.api.im.v1 import (
            CreateFileRequest,
            CreateFileRequestBody,
        )

        file_body = (
            CreateFileRequestBody.builder()
            .file_type("opus")
            .file_name("voice.opus")
            .file(BytesIO(data))
            .build()
        )
        file_req = (
            CreateFileRequest.builder()
            .request_body(file_body)
            .build()
        )
        try:
            assert self._api is not None  # noqa: S101
            file_resp = await self._api.im.v1.file.acreate(file_req)  # pyright: ignore[reportOptionalMemberAccess]
        except Exception as exc:
            logger.exception(
                "Feishu connector '%s': audio file upload raised",
                self.instance_name,
            )
            return _classify_lark_error(exc)

        if not file_resp.success():
            return SendResult(
                ok=False,
                error=f"feishu:{file_resp.code}:{file_resp.msg}",
            )
        file_key = file_resp.data.file_key if file_resp.data else ""
        if not file_key:
            return SendResult(ok=False, error="feishu:audio_upload_no_key")

        # Step 2: Send audio message
        body = (
            CreateMessageRequestBody.builder()
            .receive_id(receive_id)
            .msg_type("audio")
            .content(json.dumps({"file_key": file_key}))
            .build()
        )
        req = (
            CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(body)
            .build()
        )
        try:
            assert self._api is not None  # noqa: S101
            resp = await self._api.im.v1.message.acreate(req)  # pyright: ignore[reportOptionalMemberAccess]
            if not resp.success():
                return SendResult(
                    ok=False, error=f"feishu:{resp.code}:{resp.msg}",
                )
            message_id = (
                resp.data.message_id if resp.data is not None else ""
            ) or ""
            return SendResult(ok=True, message_id=message_id)
        except Exception as exc:
            return _classify_lark_error(exc)

    # ── Approval prompts (Phase 10) ────────────────────────────────

    async def send_approval_prompt(
        self,
        *,
        admin_identity: Identity,
        approval_id: str,
        sender: Identity,
        preview: str,
    ) -> None:
        """Send an interactive card with three approval buttons.

        Feishu's interactive cards carry button ``value`` payloads
        that come back to ``_on_card_action`` when clicked. We use
        the SDK's standard ``approve:<choice>:<approval_id>`` shape
        so the codec reuses the framework helpers.
        """
        if self._api is None:
            return

        # Resolve admin's open_id from the metadata we stored on
        # construction; fall back to parsing the external_id.
        admin_open_id = admin_identity.metadata.get("open_id") or ""
        if not admin_open_id and admin_identity.external_id.startswith(
            "feishu:user:",
        ):
            admin_open_id = admin_identity.external_id[len("feishu:user:"):]
        if not admin_open_id:
            logger.warning(
                "Feishu connector '%s': cannot parse admin open_id %r",
                self.instance_name, admin_identity.external_id,
            )
            return

        body_text = build_prompt_text(sender, preview)
        # Feishu Card v1 schema. Each button's ``value`` field is the
        # opaque payload that comes back on click.
        card = {
            "config": {"wide_screen_mode": True},
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": body_text},
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "text": "✅ Allow once"},
                            "type": "primary",
                            "value": {
                                "action": encode_action(
                                    APPROVAL_CHOICE_ALLOW_ONCE, approval_id,
                                ),
                            },
                        },
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "text": "🔓 Allow forever",
                            },
                            "type": "default",
                            "value": {
                                "action": encode_action(
                                    APPROVAL_CHOICE_ALLOW_FOREVER, approval_id,
                                ),
                            },
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "text": "🚫 Deny"},
                            "type": "danger",
                            "value": {
                                "action": encode_action(
                                    APPROVAL_CHOICE_DENY, approval_id,
                                ),
                            },
                        },
                    ],
                },
            ],
        }

        body = (
            CreateMessageRequestBody.builder()
            .receive_id(admin_open_id)
            .msg_type("interactive")
            .content(json.dumps(card, ensure_ascii=False))
            .build()
        )
        req = (
            CreateMessageRequest.builder()
            .receive_id_type("open_id")
            .request_body(body)
            .build()
        )
        try:
            assert self._api is not None  # noqa: S101
            await self._api.im.v1.message.acreate(req)  # pyright: ignore[reportOptionalMemberAccess]
        except Exception:
            logger.exception(
                "Feishu connector '%s': failed to send approval prompt",
                self.instance_name,
            )

    def _on_card_action(self, data: Any) -> None:
        """Lark dispatches interactive-card button clicks here on the
        WS thread. Hop to the main loop and route to the broker.
        """
        if self._main_loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._dispatch_card_action(data),
                self._main_loop,
            )
        except Exception:
            logger.exception(
                "Feishu connector '%s': failed to hop card action",
                self.instance_name,
            )

    async def _dispatch_card_action(self, data: Any) -> None:
        """Parse a card-button click and route it to the approval
        broker. Lark's payload shape for card actions varies by SDK
        version; we read defensively from common attribute paths.
        """
        broker = getattr(self, "_broker", None)
        if broker is None:
            return

        # Pull the button ``value.action`` out of the event. The SDK
        # types vary across releases; be defensive and dict-walk if
        # the typed accessor isn't there.
        action_str = self._extract_card_action(data)
        if not action_str:
            return
        decoded = decode_action(action_str)
        if decoded is None:
            logger.debug(
                "Feishu connector '%s': ignoring unrecognised card "
                "action %r",
                self.instance_name, action_str,
            )
            return
        choice, approval_id = decoded

        clicker_open_id = self._extract_card_clicker(data)
        if not clicker_open_id:
            logger.warning(
                "Feishu connector '%s': card action without operator id",
                self.instance_name,
            )
            return
        clicker = Identity(
            platform=self.platform,
            external_id=f"feishu:user:{clicker_open_id}",
            display_name="",
            is_group=False,
            metadata={"open_id": clicker_open_id},
        )

        try:
            resolved = await broker.resolve(approval_id, choice, clicker)
        except Exception:
            logger.exception(
                "Feishu connector '%s': broker.resolve raised",
                self.instance_name,
            )
            return

        if resolved is None:
            return

        # Edit the original card to swap the buttons for an outcome
        # line — same UX contract as Telegram/Slack/Discord.
        message_id = self._extract_card_message_id(data)
        if not message_id:
            return
        outcome = build_outcome_text(
            sender=resolved.event.identity,
            choice=choice,
            admin=clicker,
        )
        new_card = {
            "config": {"wide_screen_mode": True},
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": outcome},
                },
            ],
        }
        try:
            body = (
                PatchMessageRequestBody.builder()
                .content(json.dumps(new_card, ensure_ascii=False))
                .build()
            )
            req = (
                PatchMessageRequest.builder()
                .message_id(message_id)
                .request_body(body)
                .build()
            )
            assert self._api is not None  # noqa: S101
            await self._api.im.v1.message.apatch(req)  # pyright: ignore[reportOptionalMemberAccess]
        except Exception:
            logger.exception(
                "Feishu connector '%s': failed to edit approval prompt",
                self.instance_name,
            )

    @staticmethod
    def _extract_card_action(data: Any) -> str:
        """Defensive accessor for the ``value.action`` field."""
        action = getattr(data, "action", None)
        if action is None:
            event = getattr(data, "event", None)
            action = getattr(event, "action", None) if event else None
        value = getattr(action, "value", None) if action is not None else None
        if isinstance(value, dict):
            return value.get("action", "") or ""
        return ""

    @staticmethod
    def _extract_card_clicker(data: Any) -> str:
        """Defensive accessor for the operator/clicker open_id."""
        operator = getattr(data, "operator", None)
        if operator is None:
            event = getattr(data, "event", None)
            operator = getattr(event, "operator", None) if event else None
        if operator is None:
            return ""
        return getattr(operator, "open_id", "") or ""

    @staticmethod
    def _extract_card_message_id(data: Any) -> str:
        """Defensive accessor for the source message_id."""
        message_id = getattr(data, "open_message_id", "")
        if not message_id:
            event = getattr(data, "event", None)
            if event is not None:
                message_id = getattr(event, "open_message_id", "")
        return message_id or ""

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _resolve_receive(identity: Identity) -> tuple[str, str]:
        """Return ``(receive_id, receive_id_type)`` for a Tank Identity.

        Feishu accepts ``open_id``, ``user_id``, ``union_id``,
        ``email``, or ``chat_id`` as ``receive_id_type``. We use
        ``open_id`` for individual users and ``chat_id`` for groups,
        matching the prefix scheme :meth:`_dispatch_message` uses.
        """
        ext = identity.external_id or ""
        # Prefer metadata when available; fall back to parsing the
        # external_id prefix shape we emit on inbound.
        meta_open = identity.metadata.get("open_id") if identity.metadata else None
        meta_chat = identity.metadata.get("chat_id") if identity.metadata else None

        if ext.startswith("feishu:user:"):
            open_id = meta_open or ext[len("feishu:user:"):]
            return open_id, "open_id"
        if ext.startswith("feishu:chat:"):
            chat_id = meta_chat or ext[len("feishu:chat:"):]
            return chat_id, "chat_id"
        # Unknown shape — best-effort fallback.
        return ext, "open_id"
