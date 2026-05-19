"""Unit tests for WeChatConnector."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from connector_wechat import create_connector
from connector_wechat.connector import WeChatConnector
from connector_wechat.ilink_client import (
    SendResponse,
    SessionExpiredError,
    Update,
)
from tank_contracts.connector import (
    Identity,
    MessageEvent,
)


@pytest.fixture
def state_dir(tmp_path: Path) -> str:
    return str(tmp_path / "wechat_state")


@pytest.fixture
def connector(state_dir: str) -> WeChatConnector:
    return WeChatConnector(
        instance_name="test-wechat",
        account_id="acc_123",
        token="tok_456",
        state_dir=state_dir,
    )


# ── Factory tests ──────────────────────────────────────────────────


class TestFactory:
    def test_create_connector_happy_path(self, tmp_path: Path) -> None:
        spec = {
            "instance": "my-wechat",
            "config": {
                "account_id": "acc_x",
                "token": "tok_y",
                "state_dir": str(tmp_path),
            },
        }
        c = create_connector(spec)
        assert isinstance(c, WeChatConnector)
        assert c.instance_name == "my-wechat"
        assert c.platform == "wechat"

    def test_create_connector_missing_account_id(self) -> None:
        spec = {
            "instance": "bad",
            "config": {"token": "tok"},
        }
        with pytest.raises(ValueError, match="account_id"):
            create_connector(spec)

    def test_create_connector_missing_token(self) -> None:
        spec = {
            "instance": "bad",
            "config": {"account_id": "acc"},
        }
        with pytest.raises(ValueError, match="token"):
            create_connector(spec)

    def test_create_connector_defaults(self, tmp_path: Path) -> None:
        spec = {
            "instance": "defaults",
            "config": {
                "account_id": "acc",
                "token": "tok",
                "state_dir": str(tmp_path),
            },
        }
        c = create_connector(spec)
        assert c.capabilities.supports_edits is False
        assert c.capabilities.max_message_length == 4000
        assert c.capabilities.supports_images_in is True
        assert c.capabilities.supports_voice_in is True
        assert c.capabilities.supports_typing_indicator is True


# ── Capabilities ───────────────────────────────────────────────────


class TestCapabilities:
    def test_no_edits(self, connector: WeChatConnector) -> None:
        assert connector.capabilities.supports_edits is False

    def test_voice_disabled(self, state_dir: str) -> None:
        c = WeChatConnector(
            instance_name="no-voice",
            account_id="acc",
            token="tok",
            state_dir=state_dir,
            voice_in=False,
            voice_out=False,
        )
        assert c.capabilities.supports_voice_in is False
        assert c.capabilities.supports_voice_out is False


# ── Lifecycle ──────────────────────────────────────────────────────


class TestLifecycle:
    async def test_start_stop(self, connector: WeChatConnector) -> None:
        with patch.object(connector, "_run_poll_loop", new_callable=AsyncMock):
            await connector.start()
            assert connector.connected is True
            await connector.stop()
            assert connector.connected is False

    async def test_double_start(self, connector: WeChatConnector) -> None:
        with patch.object(connector, "_run_poll_loop", new_callable=AsyncMock):
            await connector.start()
            await connector.start()  # no-op
            assert connector.connected is True
            await connector.stop()

    async def test_stop_before_start(self, connector: WeChatConnector) -> None:
        await connector.stop()  # no-op, no error
        assert connector.connected is False


# ── Send ───────────────────────────────────────────────────────────


class TestSend:
    async def test_send_text_success(self, connector: WeChatConnector) -> None:
        connector._client = MagicMock()
        connector._client.send_message = AsyncMock(
            return_value=SendResponse(message_id="msg_1", errcode=0)
        )
        connector._state.save_context_token("wxid_abc", "ctx_tok")

        identity = Identity(
            platform="wechat",
            external_id="wechat:user:wxid_abc",
            metadata={"peer_id": "wxid_abc"},
        )
        result = await connector.send(identity, "Hello!")
        assert result.ok is True
        assert result.message_id == "msg_1"

    async def test_send_no_context_token(self, connector: WeChatConnector) -> None:
        connector._client = MagicMock()
        identity = Identity(
            platform="wechat",
            external_id="wechat:user:wxid_new",
            metadata={"peer_id": "wxid_new"},
        )
        result = await connector.send(identity, "Hello!")
        assert result.ok is False
        assert result.error == "wechat:no_context_token"

    async def test_send_not_connected(self, connector: WeChatConnector) -> None:
        identity = Identity(
            platform="wechat",
            external_id="wechat:user:wxid_abc",
            metadata={"peer_id": "wxid_abc"},
        )
        result = await connector.send(identity, "Hello!")
        assert result.ok is False
        assert result.error == "wechat:not_connected"

    async def test_send_chunked(self, connector: WeChatConnector) -> None:
        connector._client = MagicMock()
        connector._client.send_message = AsyncMock(
            return_value=SendResponse(message_id="msg_last", errcode=0)
        )
        connector._state.save_context_token("wxid_abc", "ctx_tok")

        identity = Identity(
            platform="wechat",
            external_id="wechat:user:wxid_abc",
            metadata={"peer_id": "wxid_abc"},
        )
        long_text = "x" * 8000  # exceeds 4000 limit
        result = await connector.send(identity, long_text)
        assert result.ok is True
        assert connector._client.send_message.call_count == 2

    async def test_send_session_expired(self, connector: WeChatConnector) -> None:
        connector._client = MagicMock()
        connector._client.send_message = AsyncMock(side_effect=SessionExpiredError())
        connector._state.save_context_token("wxid_abc", "ctx_tok")

        identity = Identity(
            platform="wechat",
            external_id="wechat:user:wxid_abc",
            metadata={"peer_id": "wxid_abc"},
        )
        result = await connector.send(identity, "Hello!")
        assert result.ok is False
        assert "session_expired" in (result.error or "")


# ── Send Typing ────────────────────────────────────────────────────


class TestSendTyping:
    async def test_typing_with_cached_ticket(self, connector: WeChatConnector) -> None:
        connector._client = MagicMock()
        connector._client.send_typing = AsyncMock()
        connector._state.save_typing_ticket("wxid_abc", "ticket_1")

        identity = Identity(
            platform="wechat",
            external_id="wechat:user:wxid_abc",
            metadata={"peer_id": "wxid_abc"},
        )
        await connector.send_typing(identity)
        connector._client.send_typing.assert_called_once_with("wxid_abc", "ticket_1")

    async def test_typing_fetches_ticket(self, connector: WeChatConnector) -> None:
        connector._client = MagicMock()
        from connector_wechat.ilink_client import ConfigResponse
        connector._client.get_config = AsyncMock(
            return_value=ConfigResponse(typing_ticket="new_ticket")
        )
        connector._client.send_typing = AsyncMock()

        identity = Identity(
            platform="wechat",
            external_id="wechat:user:wxid_abc",
            metadata={"peer_id": "wxid_abc"},
        )
        await connector.send_typing(identity)
        connector._client.get_config.assert_called_once()
        connector._client.send_typing.assert_called_once_with("wxid_abc", "new_ticket")


# ── Send Voice ─────────────────────────────────────────────────────


class TestSendVoice:
    async def test_voice_success(self, connector: WeChatConnector) -> None:
        connector._client = MagicMock()
        connector._client.get_upload_url = AsyncMock(return_value="https://cdn/upload")
        connector._client.upload_media = AsyncMock(return_value="https://cdn/file")
        connector._client.send_file_message = AsyncMock(
            return_value=SendResponse(message_id="voice_1", errcode=0)
        )
        connector._state.save_context_token("wxid_abc", "ctx_tok")

        identity = Identity(
            platform="wechat",
            external_id="wechat:user:wxid_abc",
            metadata={"peer_id": "wxid_abc"},
        )
        result = await connector.send_voice(identity, b"audio_data")
        assert result.ok is True
        assert result.message_id == "voice_1"

    async def test_voice_disabled(self, state_dir: str) -> None:
        c = WeChatConnector(
            instance_name="no-voice",
            account_id="acc",
            token="tok",
            state_dir=state_dir,
            voice_out=False,
        )
        c._client = MagicMock()
        c._state.save_context_token("wxid_abc", "ctx_tok")

        identity = Identity(
            platform="wechat",
            external_id="wechat:user:wxid_abc",
            metadata={"peer_id": "wxid_abc"},
        )
        result = await c.send_voice(identity, b"audio_data")
        assert result.ok is False
        assert "voice_out_disabled" in (result.error or "")


# ── Inbound processing ─────────────────────────────────────────────


class TestInbound:
    async def test_text_message_dispatched(self, connector: WeChatConnector) -> None:
        handler = AsyncMock()
        connector.set_message_handler(handler)

        update = Update(
            message_id="m1",
            peer_id="wxid_sender",
            context_token="ctx_1",
            message_type="text",
            content={"text": "hello"},
            sender_name="Alice",
        )
        await connector._process_updates([update])

        handler.assert_called_once()
        event: MessageEvent = handler.call_args[0][0]
        assert event.text == "hello"
        assert event.identity.external_id == "wechat:user:wxid_sender"
        assert event.identity.display_name == "Alice"

    async def test_deduplication(self, connector: WeChatConnector) -> None:
        handler = AsyncMock()
        connector.set_message_handler(handler)

        update = Update(
            message_id="m1",
            peer_id="wxid_sender",
            context_token="ctx_1",
            message_type="text",
            content={"text": "hello"},
        )
        await connector._process_updates([update])
        await connector._process_updates([update])  # duplicate

        assert handler.call_count == 1

    async def test_context_token_stored(self, connector: WeChatConnector) -> None:
        handler = AsyncMock()
        connector.set_message_handler(handler)

        update = Update(
            message_id="m1",
            peer_id="wxid_sender",
            context_token="new_ctx",
            message_type="text",
            content={"text": "hi"},
        )
        await connector._process_updates([update])
        assert connector._state.get_context_token("wxid_sender") == "new_ctx"

    async def test_group_disabled(self, connector: WeChatConnector) -> None:
        handler = AsyncMock()
        connector.set_message_handler(handler)

        update = Update(
            message_id="m1",
            peer_id="group_123",
            context_token="ctx",
            message_type="text",
            content={"text": "hi"},
            is_group=True,
        )
        await connector._process_updates([update])
        handler.assert_not_called()

    async def test_group_open(self, state_dir: str) -> None:
        c = WeChatConnector(
            instance_name="groups",
            account_id="acc",
            token="tok",
            state_dir=state_dir,
            group_policy="open",
        )
        handler = AsyncMock()
        c.set_message_handler(handler)

        update = Update(
            message_id="m1",
            peer_id="group_123",
            context_token="ctx",
            message_type="text",
            content={"text": "hi"},
            is_group=True,
            sender_name="Bob",
        )
        await c._process_updates([update])
        handler.assert_called_once()
        event: MessageEvent = handler.call_args[0][0]
        assert event.identity.is_group is True
        assert event.identity.external_id == "wechat:group:group_123"

    async def test_group_allowlist(self, state_dir: str) -> None:
        c = WeChatConnector(
            instance_name="groups",
            account_id="acc",
            token="tok",
            state_dir=state_dir,
            group_policy="allowlist",
            group_allowlist=["group_allowed"],
        )
        handler = AsyncMock()
        c.set_message_handler(handler)

        # Allowed group
        update1 = Update(
            message_id="m1",
            peer_id="group_allowed",
            context_token="ctx",
            message_type="text",
            content={"text": "hi"},
            is_group=True,
        )
        # Denied group
        update2 = Update(
            message_id="m2",
            peer_id="group_denied",
            context_token="ctx",
            message_type="text",
            content={"text": "hi"},
            is_group=True,
        )
        await c._process_updates([update1, update2])
        assert handler.call_count == 1

    async def test_voice_transcription(self, connector: WeChatConnector) -> None:
        handler = AsyncMock()
        connector.set_message_handler(handler)

        update = Update(
            message_id="m1",
            peer_id="wxid_sender",
            context_token="ctx",
            message_type="voice",
            content={"transcription": "hello world"},
        )
        await connector._process_updates([update])
        event: MessageEvent = handler.call_args[0][0]
        assert event.text == "hello world"
        assert len(event.attachments) == 0


# ── Identity parsing ───────────────────────────────────────────────


class TestIdentity:
    def test_parse_user_peer_id(self) -> None:
        assert WeChatConnector._parse_peer_id("wechat:user:wxid_abc") == "wxid_abc"

    def test_parse_group_peer_id(self) -> None:
        assert WeChatConnector._parse_peer_id("wechat:group:grp_123") == "grp_123"

    def test_parse_raw_id(self) -> None:
        assert WeChatConnector._parse_peer_id("wxid_raw") == "wxid_raw"


# ── SSRF protection ────────────────────────────────────────────────


class TestSSRF:
    def test_allowed_cdn_host(self) -> None:
        assert WeChatConnector._validate_cdn_url(
            "https://novac2c.cdn.weixin.qq.com/c2c/file123"
        ) is True

    def test_https_allowed(self) -> None:
        assert WeChatConnector._validate_cdn_url("https://other.example.com/file") is True

    def test_http_non_cdn_blocked(self) -> None:
        assert WeChatConnector._validate_cdn_url("http://internal.local/secret") is False

    def test_invalid_url(self) -> None:
        assert WeChatConnector._validate_cdn_url("not a url") is False
