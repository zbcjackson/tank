"""Low-level async HTTP client for the iLink Bot API.

Wraps aiohttp with retry logic, error classification, and typed
response objects. Owns the ClientSession lifecycle.
"""

from __future__ import annotations

import base64
import logging
import os
import struct
from dataclasses import dataclass, field
from typing import Any

import aiohttp

logger = logging.getLogger("ILinkClient")

_DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
_DEFAULT_CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"
_POLL_TIMEOUT_S = 35
_HTTP_TIMEOUT_S = 40  # 5s buffer over poll timeout
_CHANNEL_VERSION = "2.2.0"


class SessionExpiredError(Exception):
    """Raised when the iLink API returns errcode=-14 (session expired)."""


class ILinkAPIError(Exception):
    """Raised for non-transient iLink API errors."""

    def __init__(self, errcode: int, errmsg: str) -> None:
        super().__init__(f"iLink API error {errcode}: {errmsg}")
        self.errcode = errcode
        self.errmsg = errmsg


@dataclass
class Update:
    """A single inbound message from getupdates."""

    message_id: str
    peer_id: str
    context_token: str = ""
    message_type: str = "text"
    content: dict[str, Any] = field(default_factory=dict)
    is_group: bool = False
    sender_name: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class UpdatesResponse:
    """Response from getupdates."""

    updates: list[Update] = field(default_factory=list)
    cursor: str | None = None


@dataclass
class SendResponse:
    """Response from sendmessage."""

    message_id: str = ""
    errcode: int = 0
    errmsg: str = ""


@dataclass
class ConfigResponse:
    """Response from getconfig (typing ticket)."""

    typing_ticket: str = ""


class ILinkClient:
    """Async HTTP client for the iLink Bot API."""

    def __init__(
        self,
        account_id: str,
        token: str,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        cdn_base_url: str = _DEFAULT_CDN_BASE_URL,
    ) -> None:
        self._account_id = account_id
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._cdn_base_url = cdn_base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None

    async def open(self) -> None:
        if self._session is not None:
            return
        timeout = aiohttp.ClientTimeout(total=_HTTP_TIMEOUT_S)
        self._session = aiohttp.ClientSession(timeout=timeout)

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    # ── Public API ─────────────────────────────────────────────────

    async def get_updates(self, cursor: str | None, timeout: int = _POLL_TIMEOUT_S) -> UpdatesResponse:
        """Long-poll for new messages."""
        payload: dict[str, Any] = {"timeout": timeout}
        if cursor:
            payload["get_updates_buf"] = cursor
        data = await self._post("/ilink/bot/getupdates", payload)
        updates: list[Update] = []
        for raw_msg in data.get("msgs", []):
            updates.append(self._parse_update(raw_msg))
        new_cursor = data.get("get_updates_buf") or data.get("sync_buf")
        return UpdatesResponse(updates=updates, cursor=new_cursor)

    async def send_message(
        self,
        peer_id: str,
        content: str,
        context_token: str,
    ) -> SendResponse:
        """Send a text message to a peer."""
        msg: dict[str, Any] = {
            "from_user_id": "",
            "to_user_id": peer_id,
            "client_id": f"tank-wechat-{os.urandom(8).hex()}",
            "message_type": 2,  # BOT
            "message_state": 2,  # FINISH
            "item_list": [
                {"type": 1, "text_item": {"text": content}}
            ],
        }
        if context_token:
            msg["context_token"] = context_token
        payload = {"msg": msg, "base_info": {"channel_version": _CHANNEL_VERSION}}
        logger.info("iLink send: to=%s text_len=%d", peer_id, len(content))
        data = await self._post("/ilink/bot/sendmessage", payload)
        return SendResponse(
            message_id=str(data.get("msg_id", "")),
            errcode=data.get("ret", 0),
            errmsg=data.get("errmsg", ""),
        )

    async def send_image_message(
        self,
        peer_id: str,
        context_token: str,
        *,
        cdn_url: str,
        aes_key: str,
        file_size: int,
        width: int = 0,
        height: int = 0,
    ) -> SendResponse:
        """Send an image message with encrypted CDN reference."""
        msg: dict[str, Any] = {
            "from_user_id": "",
            "to_user_id": peer_id,
            "client_id": f"tank-wechat-{os.urandom(8).hex()}",
            "message_type": 2,
            "message_state": 2,
            "item_list": [
                {
                    "type": 2,  # IMAGE
                    "image_item": {
                        "media": {
                            "encrypt_query_param": cdn_url,
                            "aes_key": aes_key,
                            "encrypt_type": 1,
                        },
                        "mid_size": file_size,
                    },
                }
            ],
        }
        if context_token:
            msg["context_token"] = context_token
        payload = {"msg": msg, "base_info": {"channel_version": _CHANNEL_VERSION}}
        data = await self._post("/ilink/bot/sendmessage", payload)
        return SendResponse(
            message_id=str(data.get("msg_id", "")),
            errcode=data.get("ret", 0),
            errmsg=data.get("errmsg", ""),
        )

    async def send_file_message(
        self,
        peer_id: str,
        context_token: str,
        *,
        cdn_url: str,
        aes_key: str,
        file_size: int,
        filename: str,
    ) -> SendResponse:
        """Send a file/document message with encrypted CDN reference."""
        msg: dict[str, Any] = {
            "from_user_id": "",
            "to_user_id": peer_id,
            "client_id": f"tank-wechat-{os.urandom(8).hex()}",
            "message_type": 2,
            "message_state": 2,
            "item_list": [
                {
                    "type": 4,  # FILE
                    "file_item": {
                        "media": {
                            "encrypt_query_param": cdn_url,
                            "aes_key": aes_key,
                            "encrypt_type": 1,
                        },
                        "file_name": filename,
                        "len": str(file_size),
                    },
                }
            ],
        }
        if context_token:
            msg["context_token"] = context_token
        payload = {"msg": msg, "base_info": {"channel_version": _CHANNEL_VERSION}}
        data = await self._post("/ilink/bot/sendmessage", payload)
        return SendResponse(
            message_id=str(data.get("msg_id", "")),
            errcode=data.get("ret", 0),
            errmsg=data.get("errmsg", ""),
        )

    async def send_voice_message(
        self,
        peer_id: str,
        context_token: str,
        *,
        cdn_url: str,
        aes_key: str,
        file_size: int,
        duration_ms: int = 0,
    ) -> SendResponse:
        """Send a voice message with encrypted CDN reference."""
        msg: dict[str, Any] = {
            "from_user_id": "",
            "to_user_id": peer_id,
            "client_id": f"tank-wechat-{os.urandom(8).hex()}",
            "message_type": 2,
            "message_state": 2,
            "item_list": [
                {
                    "type": 3,  # VOICE
                    "voice_item": {
                        "media": {
                            "encrypt_query_param": cdn_url,
                            "aes_key": aes_key,
                            "encrypt_type": 1,
                        },
                        "encode_type": 6,  # SILK
                        "bits_per_sample": 16,
                        "sample_rate": 24000,
                        "playtime": duration_ms,
                    },
                }
            ],
        }
        if context_token:
            msg["context_token"] = context_token
        payload = {"msg": msg, "base_info": {"channel_version": _CHANNEL_VERSION}}
        data = await self._post("/ilink/bot/sendmessage", payload)
        return SendResponse(
            message_id=str(data.get("msg_id", "")),
            errcode=data.get("ret", 0),
            errmsg=data.get("errmsg", ""),
        )

    async def send_typing(self, peer_id: str, typing_ticket: str) -> None:
        """Send typing indicator."""
        payload = {
            "ilink_user_id": peer_id,
            "typing_ticket": typing_ticket,
            "status": 1,
        }
        await self._post("/ilink/bot/sendtyping", payload)

    async def get_config(self, peer_id: str) -> ConfigResponse:
        """Get config including typing ticket for a peer."""
        payload = {"ilink_user_id": peer_id}
        data = await self._post("/ilink/bot/getconfig", payload)
        ticket = data.get("typing_ticket", "") or data.get("data", {}).get("typing_ticket", "")
        return ConfigResponse(typing_ticket=ticket)

    async def get_upload_url(
        self,
        *,
        media_type: int,
        to_user_id: str,
        rawsize: int,
        rawfilemd5: str,
        filesize: int,
        aeskey_hex: str,
    ) -> dict[str, Any]:
        """Get a CDN upload URL for media.

        Returns the full API response (contains upload_full_url or upload_param).
        """
        import secrets

        payload: dict[str, Any] = {
            "filekey": secrets.token_hex(16),
            "media_type": media_type,
            "to_user_id": to_user_id,
            "rawsize": rawsize,
            "rawfilemd5": rawfilemd5,
            "filesize": filesize,
            "no_need_thumb": True,
            "aeskey": aeskey_hex,
        }
        data = await self._post("/ilink/bot/getuploadurl", payload)
        # Echo our filekey back to the caller — needed for URL construction
        # when only ``upload_param`` is returned (no ``upload_full_url``).
        data.setdefault("filekey", payload["filekey"])
        return data

    async def upload_media(self, upload_url: str, data: bytes) -> str:
        """Upload encrypted media to CDN via POST. Returns encrypt_query_param."""
        session = self._ensure_session()
        async with session.post(
            upload_url,
            data=data,
            headers={"Content-Type": "application/octet-stream"},
        ) as resp:
            if resp.status not in (200, 204):
                err_code = resp.headers.get("x-error-code", "")
                raise ILinkAPIError(
                    -1, f"CDN upload failed: HTTP {resp.status} x-error-code={err_code}",
                )
            # The download token comes from the response header, not the body
            encrypted_param = resp.headers.get("x-encrypted-param", "")
            if encrypted_param:
                return encrypted_param
            # Fallback: try response body
            try:
                body = await resp.json(content_type=None)
                return body.get("encrypted_query_param", "")
            except Exception:
                return ""

    async def download_media(self, url: str) -> bytes:
        """Download media from CDN (encrypted bytes)."""
        session = self._ensure_session()
        async with session.get(url) as resp:
            if resp.status != 200:
                raise ILinkAPIError(-1, f"CDN download failed: HTTP {resp.status}")
            return await resp.read()

    # ── QR Login Flow ──────────────────────────────────────────────

    async def request_qr_code(self) -> dict[str, Any]:
        """Request a QR code for login. Returns {qrcode, qrcode_img_content}."""
        session = self._ensure_session()
        url = f"{self._base_url}/ilink/bot/get_bot_qrcode?bot_type=3"
        headers = {"iLink-App-ClientVersion": "1"}
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise ILinkAPIError(-1, f"HTTP {resp.status}: {text[:200]}")
            data = await resp.json(content_type=None)
        ret = data.get("ret", data.get("errcode", 0))
        if ret != 0:
            raise ILinkAPIError(ret, data.get("errmsg", "unknown error"))
        # Response fields are at top level (qrcode, qrcode_img_content)
        return data

    async def poll_qr_status(self, qrcode: str) -> dict[str, Any]:
        """Poll QR code scan status. Returns login credentials when confirmed."""
        session = self._ensure_session()
        url = f"{self._base_url}/ilink/bot/get_qrcode_status?qrcode={qrcode}"
        headers = {"iLink-App-ClientVersion": "1"}
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise ILinkAPIError(-1, f"HTTP {resp.status}: {text[:200]}")
            return await resp.json(content_type=None)

    # ── Internal ───────────────────────────────────────────────────

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST to iLink API with auth headers."""
        session = self._ensure_session()
        # X-WECHAT-UIN: random uint32 as decimal string, base64-encoded
        uin = base64.b64encode(str(struct.unpack(">I", os.urandom(4))[0]).encode()).decode()
        headers = {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "Authorization": f"Bearer {self._token}",
            "iLink-App-Id": "bot",
            "iLink-App-ClientVersion": "131072",
            "X-WECHAT-UIN": uin,
        }
        url = f"{self._base_url}{path}"
        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise ILinkAPIError(-1, f"HTTP {resp.status}: {text[:200]}")
            data = await resp.json(content_type=None)

        errcode = data.get("errcode", data.get("ret", 0))
        if errcode == -14:
            raise SessionExpiredError()
        if errcode != 0:
            errmsg = data.get("errmsg", "unknown error")
            if errmsg and errmsg != "ok":
                raise ILinkAPIError(errcode, errmsg)
        return data

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("ILinkClient not opened; call open() first")
        return self._session

    @staticmethod
    def _parse_update(raw: dict[str, Any]) -> Update:
        """Parse a raw message dict into an Update dataclass."""
        # iLink API uses different field names than originally assumed.
        # Try both the actual API names and the legacy fallbacks.
        content_raw = raw.get("content", {})
        if isinstance(content_raw, str):
            content_raw = {"text": content_raw}

        # item_list contains message parts (text, image, etc.)
        item_list = raw.get("item_list")
        if item_list and isinstance(item_list, list) and not content_raw:
            first_item: dict[str, Any] = item_list[0] if item_list else {}
            content_raw = first_item

        msg_type_raw = raw.get("message_type", "") or raw.get("msg_type", "text")
        # Map iLink numeric message_type to our simplified string types
        _ILINK_MSG_TYPES: dict[int, str] = {1: "text", 3: "image", 34: "voice", 43: "video", 47: "file"}
        if isinstance(msg_type_raw, int):
            msg_type = _ILINK_MSG_TYPES.get(msg_type_raw, "text")
        elif msg_type_raw in ("text", "image", "voice", "video", "file"):
            msg_type = msg_type_raw
        else:
            msg_type = "text"
        is_group = bool(raw.get("group_id")) or raw.get("is_group", False) or raw.get("chat_type") == "group"
        sender_name = raw.get("sender_name", "") or raw.get("from_user_name", "")

        return Update(
            message_id=str(raw.get("message_id", "") or raw.get("msg_id", "")),
            peer_id=raw.get("from_user_id", "") or raw.get("from_user", "") or raw.get("peer_id", ""),
            context_token=raw.get("context_token", ""),
            message_type=msg_type,
            content=content_raw,
            is_group=is_group,
            sender_name=sender_name,
            raw=raw,
        )
