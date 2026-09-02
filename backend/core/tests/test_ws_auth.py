"""Tests for WebSocket connection auth (protocol plan P0-2).

Two layers:

- ``check_ws_auth`` — the pure decision function, all token/require
  combinations.
- The ``/ws/{session_id}`` endpoint — a rejected connection must surface
  as a close with code 1008 before any session work happens. (The accept
  path needs the full Assistant machinery and is exercised end-to-end by
  the E2E suite, which connects token-less against the default
  require=false config.)
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tank_backend.api import deps
from tank_backend.api.auth import WS_AUTH_CLOSE_CODE, check_ws_auth
from tank_backend.config import AppConfig
from tank_backend.config.models import AuthConfig

# ---------------------------------------------------------------------------
# check_ws_auth — the decision matrix
# ---------------------------------------------------------------------------


def test_no_token_configured_auth_disabled_allows_everything():
    config = AuthConfig(token="", require=False)
    assert check_ws_auth(config, None) is True
    assert check_ws_auth(config, "anything") is True


def test_no_token_configured_require_true_fails_closed():
    config = AuthConfig(token="", require=True)
    assert check_ws_auth(config, None) is False
    assert check_ws_auth(config, "guess") is False


def test_token_configured_require_false_missing_token_allowed():
    config = AuthConfig(token="s3cret", require=False)
    assert check_ws_auth(config, None) is True


def test_token_configured_require_false_correct_token_allowed():
    config = AuthConfig(token="s3cret", require=False)
    assert check_ws_auth(config, "s3cret") is True


def test_token_configured_require_false_wrong_token_rejected():
    # LAN default still rejects a *wrong* token: a client that sends one is
    # trying to authenticate, so a mismatch is a misconfiguration, not an
    # anonymous client.
    config = AuthConfig(token="s3cret", require=False)
    assert check_ws_auth(config, "wrong") is False


def test_token_configured_require_true_matrix():
    config = AuthConfig(token="s3cret", require=True)
    assert check_ws_auth(config, None) is False
    assert check_ws_auth(config, "s3cret") is True
    assert check_ws_auth(config, "wrong") is False


def test_non_ascii_token_does_not_crash_compare():
    # hmac.compare_digest(str, str) rejects non-ASCII; the implementation
    # compares UTF-8 bytes instead.
    config = AuthConfig(token="tökèn", require=False)
    assert check_ws_auth(config, "tökèn") is True
    assert check_ws_auth(config, "токен") is False


# ---------------------------------------------------------------------------
# /ws/{session_id} endpoint — rejected connections close with 1008
# ---------------------------------------------------------------------------


@pytest.fixture()
def ws_client_factory() -> Iterator[Callable[[AuthConfig], TestClient]]:
    """Yield a factory building a TestClient bound to a custom auth config.

    Snapshots and restores the whole deps container: some modules
    (e.g. test_metrics_api) tear down to a cleared ``_mgr``, so the fixture
    must not assume ``deps.connection_manager()`` is usable and must leave
    deps exactly as it found them.
    """
    from tank_backend.api.manager import ConnectionManager
    from tank_backend.api.server import app
    from tank_backend.config.context import AppContext

    prior = (
        deps._deps["ctx"],
        deps._mgr["v"],
        deps._sub_mgr["v"],
        deps._channel_audio["v"],
    )

    def factory(auth: AuthConfig) -> TestClient:
        ctx = AppContext(app_config=AppConfig(auth=auth))
        # The reject path under test never touches the connection manager
        # (auth runs before any session work), so a fresh empty manager is
        # enough; constructing one keeps deps.init's types satisfied even
        # when the snapshot holds None.
        deps.init(
            ctx, ConnectionManager(app_context=ctx), prior[2], prior[3],
        )
        return TestClient(app, raise_server_exceptions=False)

    yield factory
    deps._deps["ctx"], deps._mgr["v"], deps._sub_mgr["v"], deps._channel_audio["v"] = prior


def _assert_rejected_with_1008(client: TestClient, url: str) -> None:
    # The server accepted, then immediately closed. The session only
    # raises the disconnect when the client reads a message — the raw
    # receive() returns the close frame as a dict, so read a typed
    # message to get WebSocketDisconnect raised with the close code.
    with client.websocket_connect(url) as ws, pytest.raises(WebSocketDisconnect) as excinfo:
        ws.receive_text()
    assert excinfo.value.code == WS_AUTH_CLOSE_CODE


def test_endpoint_require_true_missing_token_rejected(ws_client_factory):
    client = ws_client_factory(AuthConfig(token="s3cret", require=True))
    _assert_rejected_with_1008(client, "/ws/auth-test-session")


def test_endpoint_require_true_wrong_token_rejected(ws_client_factory):
    client = ws_client_factory(AuthConfig(token="s3cret", require=True))
    _assert_rejected_with_1008(client, "/ws/auth-test-session?token=wrong")


def test_endpoint_require_true_empty_token_fails_closed(ws_client_factory):
    # A misconfigured deployment (auth required, no secret) must not
    # silently run open — every connection is rejected.
    client = ws_client_factory(AuthConfig(token="", require=True))
    _assert_rejected_with_1008(client, "/ws/auth-test-session?token=s3cret")


def test_endpoint_require_false_wrong_token_still_rejected(ws_client_factory):
    # LAN default (no token sent) is unaffected, but a client presenting a
    # wrong token is misconfigured and rejected.
    client = ws_client_factory(AuthConfig(token="s3cret", require=False))
    _assert_rejected_with_1008(client, "/ws/auth-test-session?token=wrong")
