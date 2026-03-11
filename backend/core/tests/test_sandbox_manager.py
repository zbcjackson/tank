"""Tests for SandboxManager with mocked docker-py."""

from unittest.mock import MagicMock, patch

import pytest

from tank_backend.sandbox.config import SandboxConfig
from tank_backend.sandbox.manager import SandboxManager, _strip_command_echo
from tank_backend.sandbox.types import SessionInfo, SessionStatus

MODULE = "tank_backend.sandbox.manager"


@pytest.fixture
def config():
    return SandboxConfig(
        enabled=True,
        image="tank-sandbox:latest",
        workspace_host_path="/tmp/test-workspace",
        memory_limit="512m",
        cpu_count=1,
        default_timeout=30,
        max_timeout=60,
    )


@pytest.fixture
def mock_docker_client():
    """Create a mock Docker client with container."""
    client = MagicMock()
    container = MagicMock()
    container.short_id = "abc123"
    container.id = "abc123full"
    client.containers.run.return_value = container
    return client, container


@pytest.fixture
def manager(config, mock_docker_client):
    """Create a SandboxManager with pre-set mocked Docker internals."""
    client, container = mock_docker_client
    mgr = SandboxManager(config)
    # Directly inject mocked internals — no patching needed
    mgr._client = client
    mgr._container = container
    return mgr


class TestSandboxConfig:
    def test_from_dict_defaults(self):
        cfg = SandboxConfig.from_dict({})
        assert cfg.enabled is False

    def test_from_dict_custom(self):
        cfg = SandboxConfig.from_dict({
            "enabled": True,
            "image": "custom:v1",
            "memory_limit": "2g",
            "cpu_count": 4,
        })
        assert cfg.enabled is True
        assert cfg.image == "custom:v1"
        assert cfg.memory_limit == "2g"
        assert cfg.cpu_count == 4

    def test_from_dict_full(self):
        cfg = SandboxConfig.from_dict({
            "enabled": True,
            "image": "tank-sandbox:latest",
            "workspace_host_path": "./ws",
            "memory_limit": "1g",
            "cpu_count": 2,
            "default_timeout": 120,
            "max_timeout": 600,
            "network_enabled": False,
        })
        assert cfg.network_enabled is False
        assert cfg.max_timeout == 600


class TestExecResult:
    def test_to_dict(self):
        from tank_backend.sandbox.types import ExecResult

        result = ExecResult(stdout="hello", stderr="", exit_code=0)
        d = result.to_dict()
        assert d["stdout"] == "hello"
        assert d["exit_code"] == 0
        assert d["timed_out"] is False

    def test_timed_out(self):
        from tank_backend.sandbox.types import ExecResult

        result = ExecResult(stdout="", stderr="", exit_code=124, timed_out=True)
        assert result.timed_out is True


class TestSessionInfo:
    def test_to_dict(self):
        info = SessionInfo(name="dev", exec_id="abc")
        d = info.to_dict()
        assert d["name"] == "dev"
        assert d["status"] == "running"
        assert d["output_lines"] == 0


class TestSandboxManagerContainerLifecycle:
    async def test_ensure_container_creates_once(self, config):
        mgr = SandboxManager(config)
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.short_id = "xyz"
        mock_client.containers.run.return_value = mock_container

        mock_docker = MagicMock()
        mock_docker.from_env.return_value = mock_client

        with patch.dict("sys.modules", {"docker": mock_docker}):
            await mgr.ensure_container()
            assert mgr._container is mock_container
            assert mock_client.containers.run.call_count == 1

            # Second call should not create again
            await mgr.ensure_container()
            assert mock_client.containers.run.call_count == 1

    async def test_cleanup_stops_container(self, manager):
        assert manager._container is not None
        await manager.cleanup()
        assert manager._container is None

    def test_is_running(self, manager):
        assert manager.is_running is True
        manager._container = None
        assert manager.is_running is False


class TestSandboxManagerExec:
    async def test_exec_command_success(self, manager):
        manager._container.exec_run.return_value = (0, (b"hello\n", b""))

        result = await manager.exec_command("echo hello")
        assert result.stdout == "hello\n"
        assert result.stderr == ""
        assert result.exit_code == 0
        assert result.timed_out is False

    async def test_exec_command_with_stderr(self, manager):
        manager._container.exec_run.return_value = (1, (b"", b"error msg\n"))

        result = await manager.exec_command("bad_cmd")
        assert result.stderr == "error msg\n"
        assert result.exit_code == 1

    async def test_exec_command_timeout(self, manager):
        manager._container.exec_run.return_value = (124, (b"partial", b""))

        result = await manager.exec_command("sleep 999", timeout=1)
        assert result.timed_out is True
        assert result.exit_code == 124

    async def test_exec_command_respects_max_timeout(self, manager):
        """Timeout should be capped at max_timeout."""
        manager._container.exec_run.return_value = (0, (b"ok", b""))

        await manager.exec_command("echo ok", timeout=9999)
        # The wrapped command should use max_timeout (60), not 9999
        call_args = manager._container.exec_run.call_args
        cmd = call_args[0][0]
        assert "timeout 60" in " ".join(cmd)

    async def test_exec_command_none_output(self, manager):
        """Handle None stdout/stderr from demux."""
        manager._container.exec_run.return_value = (0, (None, None))

        result = await manager.exec_command("true")
        assert result.stdout == ""
        assert result.stderr == ""

    async def test_exec_ensures_container(self, config):
        """exec_command should create container if not exists."""
        mgr = SandboxManager(config)
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.short_id = "new"
        mock_container.exec_run.return_value = (0, (b"ok", b""))
        mock_client.containers.run.return_value = mock_container

        mock_docker = MagicMock()
        mock_docker.from_env.return_value = mock_client

        with patch.dict("sys.modules", {"docker": mock_docker}):
            result = await mgr.exec_command("echo ok")
            assert result.stdout == "ok"
            assert mock_client.containers.run.call_count == 1


class TestSandboxManagerSessions:
    def test_list_sessions_empty(self, manager):
        assert manager.list_sessions() == []

    async def test_session_not_found_raises(self, manager):
        with pytest.raises(ValueError, match="not found"):
            await manager.session_read("nonexistent")

    async def test_session_log_not_found_raises(self, manager):
        with pytest.raises(ValueError, match="not found"):
            await manager.session_log("nonexistent")

    async def test_session_kill_not_found_raises(self, manager):
        with pytest.raises(ValueError, match="not found"):
            await manager.session_kill("nonexistent")

    def test_session_clear_not_found_raises(self, manager):
        with pytest.raises(ValueError, match="not found"):
            manager.session_clear("nonexistent")

    async def test_session_write_not_found_raises(self, manager):
        with pytest.raises(ValueError, match="not found"):
            await manager.session_write("nonexistent", "data")

    async def test_session_write_exited_raises(self, manager):
        info = SessionInfo(
            name="dead",
            exec_id="x",
            status=SessionStatus.EXITED,
        )
        manager._sessions["dead"] = info
        with pytest.raises(ValueError, match="has exited"):
            await manager.session_write("dead", "data")

    def test_session_clear(self, manager):
        info = SessionInfo(name="test", exec_id="x")
        info.output_buffer.append("line1")
        info.output_buffer.append("line2")
        info.poll_offset = 2
        manager._sessions["test"] = info

        manager.session_clear("test")
        assert len(info.output_buffer) == 0
        assert info.poll_offset == 0

    async def test_session_log(self, manager):
        info = SessionInfo(name="test", exec_id="x")
        info.output_buffer.append("line1\n")
        info.output_buffer.append("line2\n")
        manager._sessions["test"] = info

        log = await manager.session_log("test")
        assert log == "line1\nline2\n"

    async def test_session_read_incremental(self, manager):
        info = SessionInfo(name="test", exec_id="x")
        manager._sessions["test"] = info

        # No output yet
        output = await manager.session_read("test")
        assert output == ""

        # Add some output
        info.output_buffer.append("chunk1")
        info.output_buffer.append("chunk2")

        output = await manager.session_read("test")
        assert output == "chunk1chunk2"

        # Second read returns nothing new
        output = await manager.session_read("test")
        assert output == ""

        # More output
        info.output_buffer.append("chunk3")
        output = await manager.session_read("test")
        assert output == "chunk3"

    async def test_session_kill(self, manager):
        mock_sock = MagicMock()
        info = SessionInfo(name="test", exec_id="x", socket=mock_sock)
        manager._sessions["test"] = info

        await manager.session_kill("test")
        assert info.status == SessionStatus.EXITED

    async def test_session_remove(self, manager):
        mock_sock = MagicMock()
        info = SessionInfo(name="test", exec_id="x", socket=mock_sock)
        manager._sessions["test"] = info

        await manager.session_remove("test")
        assert "test" not in manager._sessions

    def test_list_sessions(self, manager):
        manager._sessions["a"] = SessionInfo(name="a", exec_id="1")
        manager._sessions["b"] = SessionInfo(
            name="b", exec_id="2", status=SessionStatus.EXITED
        )
        sessions = manager.list_sessions()
        assert len(sessions) == 2
        names = {s["name"] for s in sessions}
        assert names == {"a", "b"}


class TestHelpers:
    def test_strip_command_echo_basic(self):
        output = "echo hello\nhello\n"
        result = _strip_command_echo(output, "echo hello")
        assert "hello" in result
        # The command echo line should be stripped
        assert result.count("echo hello") == 0

    def test_strip_command_echo_removes_marker(self):
        output = "hello\n__TANK_DONE_123_456__ 0\n"
        result = _strip_command_echo(output, "echo hello")
        assert "__TANK_DONE_" not in result
