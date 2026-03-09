"""Unit tests for CosyVoice Docker server manager."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, call, patch

import httpx
import pytest
from tts_cosyvoice.server import (
    CosyVoiceServer,
    CosyVoiceServerError,
    DEFAULT_CONTAINER,
    DEFAULT_IMAGE,
    DEFAULT_PORT,
)

MODULE = "tts_cosyvoice.server"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def server_config():
    return {
        "docker_image": "test-cosyvoice:latest",
        "docker_container": "test-cosyvoice",
        "port": 55000,
        "model_dir": "iic/CosyVoice2-0.5B",
        "docker_health_timeout": 5,
    }


@pytest.fixture
def server(server_config):
    return CosyVoiceServer(server_config)


# ---------------------------------------------------------------------------
# Constructor defaults
# ---------------------------------------------------------------------------


def test_defaults():
    """Empty config uses sensible defaults."""
    s = CosyVoiceServer({})
    assert s._image == DEFAULT_IMAGE
    assert s._container == DEFAULT_CONTAINER
    assert s._port == DEFAULT_PORT


def test_custom_config(server):
    """Config values are applied."""
    assert server._image == "test-cosyvoice:latest"
    assert server._container == "test-cosyvoice"
    assert server._port == 55000


# ---------------------------------------------------------------------------
# _image_exists
# ---------------------------------------------------------------------------


@patch(f"{MODULE}._run_docker")
def test_image_exists_true(mock_docker, server):
    mock_docker.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
    assert server._image_exists() is True
    mock_docker.assert_called_once_with(
        ["image", "inspect", "test-cosyvoice:latest"],
        check=False,
        capture=True,
    )


@patch(f"{MODULE}._run_docker")
def test_image_exists_false(mock_docker, server):
    mock_docker.return_value = subprocess.CompletedProcess([], 1, stdout="", stderr="")
    assert server._image_exists() is False


# ---------------------------------------------------------------------------
# _is_container_running
# ---------------------------------------------------------------------------


@patch(f"{MODULE}._run_docker")
def test_container_running_true(mock_docker, server):
    mock_docker.return_value = subprocess.CompletedProcess([], 0, stdout="true", stderr="")
    assert server._is_container_running() is True


@patch(f"{MODULE}._run_docker")
def test_container_running_false_not_found(mock_docker, server):
    mock_docker.return_value = subprocess.CompletedProcess([], 1, stdout="", stderr="")
    assert server._is_container_running() is False


@patch(f"{MODULE}._run_docker")
def test_container_running_false_stopped(mock_docker, server):
    mock_docker.return_value = subprocess.CompletedProcess([], 0, stdout="false", stderr="")
    assert server._is_container_running() is False


# ---------------------------------------------------------------------------
# _build_image
# ---------------------------------------------------------------------------


@patch(f"{MODULE}._run_docker")
def test_build_image(mock_docker, server):
    """Build calls docker build with correct args."""
    mock_docker.return_value = subprocess.CompletedProcess([], 0)
    server._build_image()

    args = mock_docker.call_args[0][0]
    assert args[0] == "build"
    assert "-t" in args
    assert "test-cosyvoice:latest" in args
    assert any("MODEL_DIR=" in a for a in args)


def test_cosyvoice_server_error_is_runtime_error():
    """CosyVoiceServerError is a RuntimeError subclass."""
    err = CosyVoiceServerError("boom")
    assert isinstance(err, RuntimeError)
    assert str(err) == "boom"


# ---------------------------------------------------------------------------
# _start_container
# ---------------------------------------------------------------------------


@patch(f"{MODULE}._run_docker")
def test_start_container(mock_docker, server):
    """Start removes stale container then runs a new one."""
    mock_docker.return_value = subprocess.CompletedProcess([], 0)
    server._start_container()

    calls = mock_docker.call_args_list
    # First call: rm -f (cleanup stale)
    assert calls[0] == call(
        ["rm", "-f", "test-cosyvoice"], check=False, capture=True
    )
    # Second call: run -d
    run_args = calls[1][0][0]
    assert run_args[0] == "run"
    assert "-d" in run_args
    assert "--name" in run_args
    assert "test-cosyvoice" in run_args
    assert f"55000:{DEFAULT_PORT}" in " ".join(run_args)


# ---------------------------------------------------------------------------
# _wait_healthy
# ---------------------------------------------------------------------------


@patch(f"{MODULE}.time")
@patch(f"{MODULE}.httpx")
def test_wait_healthy_immediate(mock_httpx, mock_time, server):
    """Server responds immediately — no retries needed."""
    mock_time.monotonic.side_effect = [0.0, 1.0]
    mock_time.sleep = MagicMock()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_httpx.get.return_value = mock_resp

    server._wait_healthy()  # Should not raise


@patch(f"{MODULE}.time")
@patch(f"{MODULE}.httpx")
@patch(f"{MODULE}._run_docker")
def test_wait_healthy_timeout(mock_docker, mock_httpx, mock_time, server):
    """Server never responds — raises after timeout."""
    # Simulate time passing beyond the 5s timeout
    mock_time.monotonic.side_effect = [0.0, 1.0, 3.0, 6.0]
    mock_time.sleep = MagicMock()

    mock_httpx.get.side_effect = httpx.ConnectError("refused")
    mock_httpx.ConnectError = httpx.ConnectError
    mock_httpx.ReadError = httpx.ReadError
    mock_httpx.TimeoutException = httpx.TimeoutException

    mock_docker.return_value = subprocess.CompletedProcess([], 0)

    with pytest.raises(CosyVoiceServerError, match="did not become healthy"):
        server._wait_healthy()


@patch(f"{MODULE}.time")
@patch(f"{MODULE}.httpx")
def test_wait_healthy_retries_then_succeeds(mock_httpx, mock_time, server):
    """Server fails twice then succeeds."""
    mock_time.monotonic.side_effect = [0.0, 1.0, 2.0, 3.0]
    mock_time.sleep = MagicMock()

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    mock_httpx.get.side_effect = [
        httpx.ConnectError("refused"),
        httpx.ConnectError("refused"),
        mock_resp,
    ]
    mock_httpx.ConnectError = httpx.ConnectError
    mock_httpx.ReadError = httpx.ReadError
    mock_httpx.TimeoutException = httpx.TimeoutException

    server._wait_healthy()  # Should not raise
    assert mock_httpx.get.call_count == 3


# ---------------------------------------------------------------------------
# ensure_running
# ---------------------------------------------------------------------------


@patch(f"{MODULE}.atexit")
@patch.object(CosyVoiceServer, "_wait_healthy")
@patch.object(CosyVoiceServer, "_start_container")
@patch.object(CosyVoiceServer, "_build_image")
@patch.object(CosyVoiceServer, "_image_exists", return_value=True)
@patch.object(CosyVoiceServer, "_is_container_running", return_value=False)
def test_ensure_running_starts_container(
    mock_running, mock_exists, mock_build, mock_start, mock_health, mock_atexit, server
):
    """Image exists, container not running → start + health check."""
    url = server.ensure_running()

    assert url == "http://localhost:55000"
    mock_build.assert_not_called()
    mock_start.assert_called_once()
    mock_health.assert_called_once()
    mock_atexit.register.assert_called_once_with(server.stop)


@patch.object(CosyVoiceServer, "_is_container_running", return_value=True)
def test_ensure_running_already_running(mock_running, server):
    """Container already running → return URL immediately."""
    url = server.ensure_running()
    assert url == "http://localhost:55000"


@patch(f"{MODULE}.atexit")
@patch.object(CosyVoiceServer, "_wait_healthy")
@patch.object(CosyVoiceServer, "_start_container")
@patch.object(CosyVoiceServer, "_build_image")
@patch.object(CosyVoiceServer, "_image_exists", return_value=False)
@patch.object(CosyVoiceServer, "_is_container_running", return_value=False)
def test_ensure_running_builds_image(
    mock_running, mock_exists, mock_build, mock_start, mock_health, mock_atexit, server
):
    """Image missing → build then start."""
    server.ensure_running()
    mock_build.assert_called_once()
    mock_start.assert_called_once()


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------


@patch(f"{MODULE}._run_docker")
def test_stop(mock_docker, server):
    """Stop calls docker stop + rm."""
    mock_docker.return_value = subprocess.CompletedProcess([], 0)
    server.stop()

    calls = mock_docker.call_args_list
    assert calls[0] == call(["stop", "test-cosyvoice"], check=False)
    assert calls[1] == call(["rm", "-f", "test-cosyvoice"], check=False)


@patch(f"{MODULE}._run_docker")
def test_stop_idempotent(mock_docker, server):
    """Calling stop twice only runs docker commands once."""
    mock_docker.return_value = subprocess.CompletedProcess([], 0)
    server.stop()
    server.stop()
    assert mock_docker.call_count == 2  # stop + rm from first call only
