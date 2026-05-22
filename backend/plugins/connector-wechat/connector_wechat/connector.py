"""WeChat connector implementation.

Uses Tencent's iLink Bot API for personal WeChat accounts. Transport
is HTTP long-polling (no public endpoint or webhook required). Media
is transferred through an AES-128-ECB encrypted CDN.

Supports text, images, voice, files, typing indicators, and message
chunking. Group messaging is configurable but defaults to disabled
(iLink bot identities typically cannot receive group messages).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Literal

from tank_contracts.connector import (
    Attachment,
    Connector,
    ConnectorCapabilities,
    Identity,
    MessageEvent,
    SendResult,
)
from tank_contracts.connector_sdk import (
    BackgroundTaskRunner,
    build_prompt_text,
)

from .audio import TranscodeError, transcode_to_silk
from .chunker import chunk_message
from .crypto import decrypt_media, encrypt_media, parse_key
from .ilink_client import (
    ILinkClient,
    ILinkAPIError,
    SessionExpiredError,
    Update,
)
from .state import WeChatState

logger = logging.getLogger("WeChatConnector")

_SHUTDOWN_TIMEOUT_S = 5.0
_MAX_MESSAGE_LENGTH = 4000
_INTER_CHUNK_DELAY_S = 0.3
_DEDUP_WINDOW_S = 300.0  # 5 minutes
_SESSION_EXPIRED_PAUSE_S = 600.0  # 10 minutes
_MAX_INBOUND_MEDIA_BYTES = 25 * 1024 * 1024


def _aes_key_for_api(key: bytes) -> str:
    """Encode AES key as base64(hex_string) for iLink API.

    The API expects base64 of the hex-encoded key, not base64 of raw bytes.
    """
    import base64
    return base64.b64encode(key.hex().encode("ascii")).decode("ascii")


@dataclass(frozen=True)
class _UploadedMedia:
    """Result of a CDN upload: the AES key and the encrypted download param."""
    key: bytes
    encrypt_query_param: str


# Allowed CDN hosts for SSRF protection
_ALLOWED_CDN_HOSTS = frozenset({
    "novac2c.cdn.weixin.qq.com",
})


class WeChatConnector(Connector):
    """Platform adapter for WeChat via iLink Bot API."""

    platform = "wechat"

    def __init__(
        self,
        *,
        instance_name: str,
        account_id: str,
        token: str,
        state_dir: str,
        base_url: str = "https://ilinkai.weixin.qq.com",
        cdn_base_url: str = "https://novac2c.cdn.weixin.qq.com/c2c",
        group_policy: str = "disabled",
        group_allowlist: list[str] | None = None,
        voice_in: bool = True,
        voice_out: bool = False,
    ) -> None:
        super().__init__(
            instance_name=instance_name,
            capabilities=ConnectorCapabilities(
                supports_edits=False,
                edit_min_interval_ms=0,
                max_message_length=_MAX_MESSAGE_LENGTH,
                supports_images_in=True,
                supports_images_out=True,
                supports_voice_in=voice_in,
                supports_voice_out=voice_out,
                supports_typing_indicator=True,
            ),
        )
        self._account_id = account_id
        self._token = token
        self._base_url = base_url
        self._cdn_base_url = cdn_base_url
        self._group_policy = group_policy
        self._group_allowlist: frozenset[str] = frozenset(group_allowlist or [])
        self._voice_in = voice_in
        self._voice_out = voice_out

        from pathlib import Path
        self._state = WeChatState(Path(state_dir))
        self._client: ILinkClient | None = None
        self._runner = BackgroundTaskRunner(
            instance_name=instance_name,
            platform=self.platform,
            shutdown_timeout_s=_SHUTDOWN_TIMEOUT_S,
        )
        self._shutdown_requested = False
        self._seen_ids: dict[str, float] = {}

    # ── Lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        if self._connected:
            return
        self._client = ILinkClient(
            self._account_id,
            self._token,
            base_url=self._base_url,
            cdn_base_url=self._cdn_base_url,
        )
        await self._client.open()
        self._shutdown_requested = False
        self._runner.spawn(self._run_poll_loop())
        self._connected = True
        if self._group_policy != "disabled":
            logger.warning(
                "WeChat connector '%s': group_policy=%s — iLink bot identities "
                "typically cannot receive ordinary WeChat group messages",
                self.instance_name, self._group_policy,
            )
        logger.info(
            "WeChat connector '%s' started (account=%s, voice_in=%s, voice_out=%s)",
            self.instance_name, self._account_id, self._voice_in, self._voice_out,
        )

    async def stop(self) -> None:
        if not self._connected:
            return
        self._shutdown_requested = True
        # Close the HTTP session first so the in-flight long-poll request
        # (up to 35s) is aborted immediately rather than blocking drain.
        if self._client is not None:
            with contextlib.suppress(Exception):
                await self._client.close()
            self._client = None
        await self._runner.drain()
        self._connected = False
        logger.info("WeChat connector '%s' stopped", self.instance_name)

    # ── Outbound ────────────────────────────────────────────────────

    async def send(
        self,
        identity: Identity,
        text: str,
        *,
        reply_to: str | None = None,
        attachments: tuple[Attachment, ...] = (),
    ) -> SendResult:
        if self._client is None:
            logger.warning("WeChat send: not connected")
            return SendResult(ok=False, error="wechat:not_connected")

        peer_id = self._parse_peer_id(identity.external_id)
        context_token = self._state.get_context_token(peer_id)
        if not context_token:
            logger.warning("WeChat send: no context_token for peer=%s", peer_id)
            return SendResult(ok=False, error="wechat:no_context_token")

        logger.info("WeChat send: peer=%s text=%d chars", peer_id, len(text))

        # Route image attachments
        for att in attachments:
            if att.kind == "image":
                return await self._send_image(peer_id, att, context_token)

        if not text:
            return SendResult(ok=True)

        # Chunk oversized messages
        chunks = chunk_message(text, _MAX_MESSAGE_LENGTH)
        last_message_id: str | None = None
        for i, chunk in enumerate(chunks):
            try:
                resp = await self._client.send_message(peer_id, chunk, context_token)
                logger.info("WeChat send result: errcode=%d msg_id=%s", resp.errcode, resp.message_id)
                last_message_id = resp.message_id
            except SessionExpiredError:
                logger.warning("WeChat send: session expired")
                return SendResult(ok=False, error="wechat:session_expired")
            except (ILinkAPIError, Exception) as e:
                logger.warning("WeChat send failed: %s", e)
                return SendResult(ok=False, error=f"wechat:{e}")
            if i < len(chunks) - 1:
                await asyncio.sleep(_INTER_CHUNK_DELAY_S)

        return SendResult(ok=True, message_id=last_message_id)

    async def send_typing(self, identity: Identity) -> None:
        if self._client is None:
            return
        peer_id = self._parse_peer_id(identity.external_id)
        ticket = self._state.get_typing_ticket(peer_id)
        if not ticket:
            try:
                config = await self._client.get_config(peer_id)
                ticket = config.typing_ticket
                if ticket:
                    self._state.save_typing_ticket(peer_id, ticket)
            except Exception:
                logger.debug("Failed to fetch typing ticket for %s", peer_id)
                return
        if ticket:
            try:
                await self._client.send_typing(peer_id, ticket)
            except Exception:
                logger.debug("Failed to send typing to %s", peer_id)

    async def send_voice(
        self,
        identity: Identity,
        data: bytes,
        *,
        mime_type: str = "audio/ogg",
        caption: str = "",
    ) -> SendResult:
        # Native WeChat voice via iLink CDN is unreliable: the CDN rejects
        # uploads with x-error-code=-5102019 even when the payload mirrors
        # working reference impls byte-for-byte. Hermes Agent reaches the
        # same conclusion and falls back to file attachments. We expose
        # the capability via ``voice_out`` config but default it off so
        # the framework sends the LLM text response instead.
        if not self._voice_out:
            return SendResult(ok=False, error="wechat:voice_out_disabled")
        if self._client is None:
            return SendResult(ok=False, error="wechat:not_connected")

        peer_id = self._parse_peer_id(identity.external_id)
        context_token = self._state.get_context_token(peer_id)
        if not context_token:
            return SendResult(ok=False, error="wechat:no_context_token")

        try:
            silk_bytes, duration_ms = await transcode_to_silk(data)
            uploaded = await self._upload_media(
                peer_id, silk_bytes, media_type=4,  # VOICE
            )
            resp = await self._client.send_voice_message(
                peer_id, context_token,
                cdn_url=uploaded.encrypt_query_param,
                aes_key=_aes_key_for_api(uploaded.key),
                file_size=len(silk_bytes),
                duration_ms=duration_ms,
            )
            return SendResult(ok=True, message_id=resp.message_id)
        except TranscodeError as e:
            logger.warning("WeChat voice transcode failed: %s", e)
            return SendResult(ok=False, error=f"wechat:voice_transcode:{e}")
        except SessionExpiredError:
            return SendResult(ok=False, error="wechat:session_expired")
        except Exception as e:
            return SendResult(ok=False, error=f"wechat:voice_send:{e}")

    async def send_approval_prompt(
        self,
        *,
        admin_identity: Identity,
        approval_id: str,
        sender: Identity,
        preview: str,
    ) -> None:
        """Send text-based approval prompt (WeChat has no native buttons)."""
        if self._client is None:
            return
        peer_id = self._parse_peer_id(admin_identity.external_id)
        context_token = self._state.get_context_token(peer_id)
        if not context_token:
            logger.warning("Cannot send approval prompt: no context token for admin %s", peer_id)
            return

        prompt = build_prompt_text(sender, preview)
        text = (
            f"{prompt}\n\n"
            f"Reply with one of:\n"
            f"• YES — allow this message\n"
            f"• ALWAYS — allow this sender permanently\n"
            f"• NO — deny\n\n"
            f"[approval_id: {approval_id}]"
        )
        try:
            await self._client.send_message(peer_id, text, context_token)
        except Exception:
            logger.exception("Failed to send approval prompt to %s", peer_id)

    # ── Long-poll loop ──────────────────────────────────────────────

    async def _run_poll_loop(self) -> None:
        """Background task: long-poll for messages with retry/backoff."""
        consecutive_errors = 0
        logger.info("WeChat poll loop starting (cursor=%s)", self._state.sync_cursor[:20] if self._state.sync_cursor else None)
        while not self._shutdown_requested:
            try:
                assert self._client is not None  # noqa: S101
                response = await self._client.get_updates(
                    cursor=self._state.sync_cursor,
                    timeout=35,
                )
                consecutive_errors = 0

                if response.updates:
                    logger.info("WeChat received %d update(s)", len(response.updates))
                    await self._process_updates(response.updates)

                if response.cursor:
                    self._state.save_cursor(response.cursor)

            except SessionExpiredError:
                logger.warning(
                    "WeChat session expired (errcode=-14); pausing %ds",
                    int(_SESSION_EXPIRED_PAUSE_S),
                )
                await asyncio.sleep(_SESSION_EXPIRED_PAUSE_S)

            except asyncio.TimeoutError:
                continue

            except asyncio.CancelledError:
                raise

            except Exception:
                if self._shutdown_requested:
                    break
                consecutive_errors += 1
                if consecutive_errors <= 2:
                    logger.warning("Poll error (attempt %d), retrying in 2s", consecutive_errors, exc_info=True)
                    await asyncio.sleep(2)
                else:
                    logger.warning("3+ consecutive poll errors; backing off 30s", exc_info=True)
                    await asyncio.sleep(30)
                    consecutive_errors = 0

    # ── Inbound processing ──────────────────────────────────────────

    async def _process_updates(self, updates: list[Update]) -> None:
        now = time.monotonic()
        # Prune expired dedup entries
        self._seen_ids = {
            mid: ts for mid, ts in self._seen_ids.items()
            if now - ts < _DEDUP_WINDOW_S
        }

        for update in updates:
            msg_id = update.message_id
            if not msg_id:
                logger.warning("WeChat skipping update with empty msg_id: raw_keys=%s", list(update.raw.keys()))
                continue
            if msg_id in self._seen_ids:
                logger.debug("WeChat dedup: %s", msg_id)
                continue
            self._seen_ids[msg_id] = now

            # Store context token
            if update.context_token:
                self._state.save_context_token(update.peer_id, update.context_token)
                logger.debug("WeChat saved context_token for peer=%s", update.peer_id)
            else:
                logger.debug("WeChat update has no context_token (peer=%s)", update.peer_id)

            # Group policy gate
            if update.is_group:
                if self._group_policy == "disabled":
                    logger.info("WeChat skipping group message (policy=disabled)")
                    continue
                if self._group_policy == "allowlist" and update.peer_id not in self._group_allowlist:
                    continue

            await self._handle_message(update)

    async def _handle_message(self, update: Update) -> None:
        if self._on_message is None:
            logger.warning("WeChat _handle_message called but _on_message is None!")
            return

        logger.info("WeChat handling message: type=%s peer=%s", update.message_type, update.peer_id)

        identity = self._make_identity(update)
        text = ""
        attachments: list[Attachment] = []

        if update.message_type == "text":
            # iLink text is in content.text_item.text
            text_item = update.content.get("text_item", {})
            text = text_item.get("text", "") if isinstance(text_item, dict) else update.content.get("text", "")
        elif update.message_type == "image":
            att = await self._download_inbound_media(update, "image")
            if att:
                attachments.append(att)
        elif update.message_type == "voice":
            # Check for transcription first
            transcription = update.content.get("transcription", "")
            if transcription:
                text = transcription
            elif self._voice_in:
                att = await self._download_inbound_media(update, "audio")
                if att:
                    attachments.append(att)
        elif update.message_type == "video":
            att = await self._download_inbound_media(update, "file")
            if att:
                attachments.append(att)
        elif update.message_type == "file":
            att = await self._download_inbound_media(update, "file")
            if att:
                attachments.append(att)
        else:
            text = update.content.get("text", "")

        if not text and not attachments:
            return

        event = MessageEvent(
            identity=identity,
            text=text,
            attachments=tuple(attachments),
            raw=update.raw,
        )
        try:
            await self._on_message(event)
        except Exception:
            logger.exception("Message handler raised for %s", update.message_id)

    # ── Media handling ──────────────────────────────────────────────

    async def _download_inbound_media(
        self, update: Update, kind: Literal["image", "audio", "file"],
    ) -> Attachment | None:
        """Download and decrypt inbound media from CDN."""
        content = update.content
        url = content.get("url", "") or content.get("encrypted_query_param", "")
        key_raw = content.get("aes_key", "") or content.get("key", "")

        if not url or not key_raw:
            logger.debug("Missing URL or key for %s message %s", kind, update.message_id)
            return None

        if not self._validate_cdn_url(url):
            logger.warning("Blocked unsafe URL (SSRF protection): %s", url[:100])
            return None

        if self._client is None:
            return None

        try:
            encrypted_data = await self._client.download_media(url)
        except Exception:
            logger.exception("Media download failed for %s", update.message_id)
            return None

        if len(encrypted_data) > _MAX_INBOUND_MEDIA_BYTES:
            logger.info("Dropping oversized media (%d bytes)", len(encrypted_data))
            return None

        try:
            key = parse_key(key_raw)
            plaintext = decrypt_media(encrypted_data, key)
        except Exception:
            logger.exception("Media decryption failed for %s", update.message_id)
            return None

        mime_type = self._guess_mime_type(kind, content)
        filename = content.get("file_name", "")
        return Attachment(kind=kind, data=plaintext, mime_type=mime_type, filename=filename)

    async def _send_image(self, peer_id: str, attachment: Attachment, context_token: str) -> SendResult:
        """Encrypt and upload an image, then send the reference."""
        if self._client is None:
            return SendResult(ok=False, error="wechat:not_connected")

        if isinstance(attachment.data, str):
            # URL — need to download first
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(attachment.data) as resp:
                        if resp.status != 200:
                            return SendResult(ok=False, error=f"wechat:image_fetch:{resp.status}")
                        image_data = await resp.read()
            except Exception as e:
                return SendResult(ok=False, error=f"wechat:image_fetch:{e}")
        else:
            image_data = attachment.data

        if not image_data:
            return SendResult(ok=False, error="wechat:empty_image")

        try:
            uploaded = await self._upload_media(peer_id, image_data, media_type=1)  # IMAGE
            resp = await self._client.send_image_message(
                peer_id, context_token,
                cdn_url=uploaded.encrypt_query_param,
                aes_key=_aes_key_for_api(uploaded.key),
                file_size=len(image_data),
            )
            return SendResult(ok=True, message_id=resp.message_id)
        except SessionExpiredError:
            return SendResult(ok=False, error="wechat:session_expired")
        except Exception as e:
            return SendResult(ok=False, error=f"wechat:image_send:{e}")

    # ── Helpers ─────────────────────────────────────────────────────

    async def _upload_media(
        self, peer_id: str, plaintext: bytes, *, media_type: int,
    ) -> _UploadedMedia:
        """Encrypt, upload media to CDN. Returns upload result with CDN params."""
        assert self._client is not None

        ciphertext, key = encrypt_media(plaintext)
        aeskey_hex = key.hex()
        rawfilemd5 = hashlib.md5(plaintext).hexdigest()
        # AES-128-ECB with PKCS7: padded size
        filesize = ((len(plaintext) + 1 + 15) // 16) * 16

        resp = await self._client.get_upload_url(
            media_type=media_type,
            to_user_id=peer_id,
            rawsize=len(plaintext),
            rawfilemd5=rawfilemd5,
            filesize=filesize,
            aeskey_hex=aeskey_hex,
        )
        upload_url = (resp.get("upload_full_url") or "").strip()
        filekey = resp.get("filekey", "")
        if not upload_url:
            upload_param = resp.get("upload_param", "")
            if upload_param:
                upload_url = f"{self._cdn_base_url}/upload?encrypted_query_param={upload_param}&filekey={filekey}"
        else:
            # iLink sometimes returns upload_full_url without filekey — append it
            # if missing (CDN rejects uploads lacking the filekey query param).
            if filekey and "filekey=" not in upload_url:
                sep = "&" if "?" in upload_url else "?"
                upload_url = f"{upload_url}{sep}filekey={filekey}"
        if not upload_url:
            raise ILinkAPIError(-1, "No upload URL returned")

        encrypt_query_param = await self._client.upload_media(upload_url, ciphertext)
        if not encrypt_query_param:
            raise ILinkAPIError(-1, "No encrypt_query_param from CDN upload")

        return _UploadedMedia(key=key, encrypt_query_param=encrypt_query_param)

    def _make_identity(self, update: Update) -> Identity:
        if update.is_group:
            external_id = f"wechat:group:{update.peer_id}"
        else:
            external_id = f"wechat:user:{update.peer_id}"
        return Identity(
            platform=self.platform,
            external_id=external_id,
            display_name=update.sender_name,
            is_group=update.is_group,
            metadata={"peer_id": update.peer_id},
        )

    @staticmethod
    def _parse_peer_id(external_id: str) -> str:
        """Parse wechat:user:xxx or wechat:group:xxx → xxx."""
        parts = external_id.split(":", 2)
        if len(parts) == 3 and parts[0] == "wechat":
            return parts[2]
        return external_id

    @staticmethod
    def _validate_cdn_url(url: str) -> bool:
        """SSRF protection: only allow known CDN hosts."""
        try:
            parsed = urllib.parse.urlparse(url)
            return parsed.hostname in _ALLOWED_CDN_HOSTS
        except Exception:
            return False

    @staticmethod
    def _guess_mime_type(kind: str, content: dict[str, Any]) -> str:
        mime = content.get("mime_type", "")
        if mime:
            return mime
        if kind == "image":
            return "image/jpeg"
        if kind == "audio":
            return "audio/silk"
        if kind == "file":
            return "application/octet-stream"
        return ""
