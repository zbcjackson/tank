"""Unit tests for ILinkClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from connector_wechat.ilink_client import (
    ILinkAPIError,
    ILinkClient,
    SessionExpiredError,
)


@pytest.fixture
def client() -> ILinkClient:
    return ILinkClient("acc_123", "tok_456")


class TestParseUpdate:
    def test_text_message(self) -> None:
        raw = {
            "msg_id": "m1",
            "from_user": "wxid_abc",
            "context_token": "ctx_1",
            "msg_type": "text",
            "content": {"text": "hello"},
        }
        update = ILinkClient._parse_update(raw)
        assert update.message_id == "m1"
        assert update.peer_id == "wxid_abc"
        assert update.context_token == "ctx_1"
        assert update.message_type == "text"
        assert update.content == {"text": "hello"}
        assert update.is_group is False

    def test_image_message(self) -> None:
        raw = {
            "msg_id": "m2",
            "from_user": "wxid_def",
            "context_token": "ctx_2",
            "msg_type": "image",
            "content": {"url": "https://cdn.example.com/img", "aes_key": "abc123"},
        }
        update = ILinkClient._parse_update(raw)
        assert update.message_type == "image"
        assert update.content["url"] == "https://cdn.example.com/img"

    def test_group_message(self) -> None:
        raw = {
            "msg_id": "m3",
            "from_user": "group_123",
            "context_token": "ctx_3",
            "msg_type": "text",
            "content": {"text": "hi"},
            "is_group": True,
            "sender_name": "Alice",
        }
        update = ILinkClient._parse_update(raw)
        assert update.is_group is True
        assert update.sender_name == "Alice"

    def test_string_content(self) -> None:
        raw = {
            "msg_id": "m4",
            "from_user": "wxid_x",
            "context_token": "ctx_4",
            "msg_type": "text",
            "content": "plain string",
        }
        update = ILinkClient._parse_update(raw)
        assert update.content == {"text": "plain string"}

    def test_missing_fields(self) -> None:
        raw = {"msg_id": "m5"}
        update = ILinkClient._parse_update(raw)
        assert update.message_id == "m5"
        assert update.peer_id == ""
        assert update.context_token == ""
        assert update.message_type == "text"


class TestGetUpdates:
    async def test_success(self, client: ILinkClient) -> None:
        response_data = {
            "ret": 0,
            "msgs": [
                {
                    "msg_id": "m1",
                    "from_user": "wxid_abc",
                    "context_token": "ctx_1",
                    "msg_type": "text",
                    "content": {"text": "hello"},
                }
            ],
            "get_updates_buf": "cursor_new",
            "sync_buf": "sync_new",
        }
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=response_data)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        client._session = mock_session

        result = await client.get_updates(cursor="old_cursor")
        assert len(result.updates) == 1
        assert result.updates[0].message_id == "m1"
        assert result.cursor == "cursor_new"

    async def test_session_expired(self, client: ILinkClient) -> None:
        response_data = {"errcode": -14, "errmsg": "session expired"}
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=response_data)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        client._session = mock_session

        with pytest.raises(SessionExpiredError):
            await client.get_updates(cursor=None)

    async def test_api_error(self, client: ILinkClient) -> None:
        response_data = {"errcode": -100, "errmsg": "bad request"}
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=response_data)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        client._session = mock_session

        with pytest.raises(ILinkAPIError) as exc_info:
            await client.get_updates(cursor=None)
        assert exc_info.value.errcode == -100


class TestSendMessage:
    async def test_success(self, client: ILinkClient) -> None:
        response_data = {
            "ret": 0,
            "msg_id": "sent_1",
        }
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=response_data)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        client._session = mock_session

        result = await client.send_message("wxid_abc", "hello", "ctx_token")
        assert result.message_id == "sent_1"
        assert result.errcode == 0


class TestGetConfig:
    async def test_success(self, client: ILinkClient) -> None:
        response_data = {
            "errcode": 0,
            "data": {"typing_ticket": "ticket_xyz"},
        }
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=response_data)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        client._session = mock_session

        result = await client.get_config("wxid_abc")
        assert result.typing_ticket == "ticket_xyz"
