"""Tests for Seatbelt sandbox backend."""

import dataclasses
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from tank_backend.sandbox.backends.seatbelt import (
    SeatbeltSandbox,
    _build_seatbelt_profile,
    _quote,
)
from tank_backend.sandbox.backends.shared import BackendPolicy, NetworkMode

MODULE = "tank_backend.sandbox.backends.seatbelt"


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def default_policy():
    return BackendPolicy()


@pytest.fixture
def custom_policy():
    return BackendPolicy(
        read_only_paths=("/usr/local", "/opt"),
        writable_paths=("/tmp/workspace",),
        denied_paths=("/etc/shadow",),
        network=NetworkMode.ALLOW_ALL,
        default_timeout=60,
        max_timeout=300,
        working_dir="/tmp/workspace",
    )


@pytest.fixture
def restricted_network_policy():
    return BackendPolicy(
        network=NetworkMode.RESTRICTED,
        allowed_hosts=("github.com", "pypi.org"),
    )


# ── Profile generation tests ──────────────────────────────────────


class TestQuote:
    def test_quote_simple_path(self):
        assert _quote("/usr/bin") == "/usr/bin"

    def test_quote_with_backslash(self):
        assert _quote("C:\\Users\\test") == "C:\\\\Users\\\\test"

    def test_quote_with_double_quote(self):
        assert _quote('path with "quotes"') == 'path with \\"quotes\\"'

    def test_quote_mixed(self):
        assert _quote('C:\\path\\"test"') == 'C:\\\\path\\\\\\"test\\"'


class TestBuildSeatbeltProfile:
    def test_minimal_profile(self, default_policy):
        profile = _build_seatbelt_profile(default_policy)
        assert "(version 1)" in profile
        assert "(deny default)" in profile
        assert "(allow process-exec)" in profile
        assert "(deny network*)" in profile  # default is NONE

    def test_read_only_paths(self):
        """With allow-read-default, read_only_paths are not explicitly listed."""
        policy = BackendPolicy(read_only_paths=("/usr/local", "/opt"))
        profile = _build_seatbelt_profile(policy)
        # All reads are allowed by default — no per-path read rules
        assert "(allow file-read*)" in profile
        # Should not have write permission
        assert '(allow file-write* (subpath "/usr/local"))' not in profile

    def test_writable_paths(self):
        policy = BackendPolicy(writable_paths=("/tmp/workspace",))
        profile = _build_seatbelt_profile(policy)
        assert '(allow file-write* (subpath "/tmp/workspace"))' in profile

    def test_denied_paths(self):
        policy = BackendPolicy(denied_paths=("/etc/shadow", "/root"))
        profile = _build_seatbelt_profile(policy)
        assert '(deny file-read* (subpath "/etc/shadow"))' in profile
        assert '(deny file-write* (subpath "/etc/shadow"))' in profile
        assert '(deny file-read* (subpath "/root"))' in profile

    def test_network_none(self):
        policy = BackendPolicy(network=NetworkMode.NONE)
        profile = _build_seatbelt_profile(policy)
        assert "(deny network*)" in profile

    def test_network_allow_all(self):
        policy = BackendPolicy(network=NetworkMode.ALLOW_ALL)
        profile = _build_seatbelt_profile(policy)
        assert "(allow network*)" in profile
        assert "(deny network*)" not in profile

    def test_network_restricted_with_hosts(self, restricted_network_policy):
        profile = _build_seatbelt_profile(restricted_network_policy)
        # Should allow network (Seatbelt can't filter by hostname)
        assert "(allow network*)" in profile
        # Should document the intended hosts as a comment
        assert "github.com" in profile
        assert "pypi.org" in profile
        assert "advisory" in profile

    def test_baseline_allows_all_reads(self, default_policy):
        """Allow-read-default: profile has a blanket file-read allow."""
        profile = _build_seatbelt_profile(default_policy)
        assert "(allow file-read*)" in profile
        assert '(allow file-write* (literal "/dev/null"))' in profile

    def test_path_with_special_chars(self):
        policy = BackendPolicy(denied_paths=('/path with "quotes"',))
        profile = _build_seatbelt_profile(policy)
        assert 'path with \\"quotes\\"' in profile


# ── SeatbeltSandbox tests ─────────────────────────────────────────


class TestSeatbeltSandboxInit:
    def test_init_default_policy(self):
        sandbox = SeatbeltSandbox()
        assert sandbox.is_running is True
        assert "(version 1)" in sandbox.profile

    def test_init_custom_policy(self, custom_policy):
        sandbox = SeatbeltSandbox(custom_policy)
        assert "/tmp/workspace" in sandbox.profile
        assert "(allow network*)" in sandbox.profile

    def test_profile_property(self, custom_policy):
        sandbox = SeatbeltSandbox(custom_policy)
        profile = sandbox.profile
        assert isinstance(profile, str)
        assert len(profile) > 0


class TestSeatbeltSandboxLifecycle:
    def test_is_running_always_true(self):
        sandbox = SeatbeltSandbox()
        assert sandbox.is_running is True

    async def test_cleanup_is_noop(self):
        sandbox = SeatbeltSandbox()
        await sandbox.cleanup()
        # Should not raise, should still be "running"
        assert sandbox.is_running is True


class TestSeatbeltSandboxExecCommand:
    async def test_exec_command_success(self, default_policy):
        sandbox = SeatbeltSandbox(default_policy)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = b"hello world\n"
        mock_proc.stderr = b""

        with patch(f"{MODULE}.subprocess.run", return_value=mock_proc) as mock_run:
            result = await sandbox.exec_command("echo hello world")

        assert result.stdout == "hello world\n"
        assert result.stderr == ""
        assert result.exit_code == 0
        assert result.timed_out is False

        # Verify subprocess.run was called correctly
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert cmd[0] == "/usr/bin/sandbox-exec"
        assert cmd[1] == "-p"
        assert cmd[3] == "bash"
        assert cmd[4] == "-c"
        assert cmd[5] == "echo hello world"

    async def test_exec_command_with_stderr(self, default_policy):
        sandbox = SeatbeltSandbox(default_policy)
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = b""
        mock_proc.stderr = b"command not found\n"

        with patch(f"{MODULE}.subprocess.run", return_value=mock_proc):
            result = await sandbox.exec_command("bad_command")

        assert result.stderr == "command not found\n"
        assert result.exit_code == 1
        assert result.timed_out is False

    async def test_exec_command_timeout(self, default_policy):
        sandbox = SeatbeltSandbox(default_policy)
        exc = subprocess.TimeoutExpired(
            cmd=["sandbox-exec"],
            timeout=5,
            output=b"partial output",
            stderr=b"",
        )

        with patch(f"{MODULE}.subprocess.run", side_effect=exc):
            result = await sandbox.exec_command("sleep 999", timeout=5)

        assert result.stdout == "partial output"
        assert result.exit_code == 124
        assert result.timed_out is True

    async def test_exec_command_timeout_with_none_output(self, default_policy):
        sandbox = SeatbeltSandbox(default_policy)
        exc = subprocess.TimeoutExpired(
            cmd=["sandbox-exec"],
            timeout=5,
            output=None,
            stderr=None,
        )

        with patch(f"{MODULE}.subprocess.run", side_effect=exc):
            result = await sandbox.exec_command("sleep 999", timeout=5)

        assert result.stdout == ""
        assert result.stderr == ""
        assert result.timed_out is True

    async def test_exec_command_custom_timeout(self, custom_policy):
        sandbox = SeatbeltSandbox(custom_policy)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = b"ok"
        mock_proc.stderr = b""

        with patch(f"{MODULE}.subprocess.run", return_value=mock_proc) as mock_run:
            await sandbox.exec_command("echo ok", timeout=10)

        # Should use the requested timeout (10), not default (60)
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 10

    async def test_exec_command_respects_max_timeout(self, custom_policy):
        sandbox = SeatbeltSandbox(custom_policy)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = b"ok"
        mock_proc.stderr = b""

        with patch(f"{MODULE}.subprocess.run", return_value=mock_proc) as mock_run:
            # Request 9999s, should be clamped to max_timeout (300)
            await sandbox.exec_command("echo ok", timeout=9999)

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 300

    async def test_exec_command_custom_working_dir(self, default_policy):
        sandbox = SeatbeltSandbox(default_policy)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = b"/custom/dir\n"
        mock_proc.stderr = b""

        with patch(f"{MODULE}.subprocess.run", return_value=mock_proc) as mock_run:
            await sandbox.exec_command("pwd", working_dir="/custom/dir")

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] == "/custom/dir"

    async def test_exec_command_uses_policy_working_dir(self, custom_policy):
        sandbox = SeatbeltSandbox(custom_policy)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = b"ok"
        mock_proc.stderr = b""

        with patch(f"{MODULE}.subprocess.run", return_value=mock_proc) as mock_run:
            await sandbox.exec_command("echo ok")

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] == "/tmp/workspace"

    async def test_exec_command_sandbox_exec_not_found(self, default_policy):
        sandbox = SeatbeltSandbox(default_policy)

        with patch(f"{MODULE}.subprocess.run", side_effect=FileNotFoundError):
            result = await sandbox.exec_command("echo hi")

        assert result.exit_code == 127
        assert "sandbox-exec not found" in result.stderr
        assert "macOS" in result.stderr

    async def test_exec_command_os_error(self, default_policy):
        sandbox = SeatbeltSandbox(default_policy)

        with patch(
            f"{MODULE}.subprocess.run",
            side_effect=OSError("Permission denied"),
        ):
            result = await sandbox.exec_command("echo hi")

        assert result.exit_code == 1
        assert "Failed to launch" in result.stderr
        assert "Permission denied" in result.stderr

    async def test_exec_command_unicode_handling(self, default_policy):
        sandbox = SeatbeltSandbox(default_policy)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "你好世界\n".encode()
        mock_proc.stderr = b""

        with patch(f"{MODULE}.subprocess.run", return_value=mock_proc):
            result = await sandbox.exec_command("echo 你好世界")

        assert result.stdout == "你好世界\n"


class TestSeatbeltSandboxBashCommand:
    async def test_bash_command_success(self, default_policy):
        sandbox = SeatbeltSandbox(default_policy)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = b"hello\n"
        mock_proc.stderr = b""

        with patch(f"{MODULE}.subprocess.run", return_value=mock_proc):
            result = await sandbox.bash_command("echo hello")

        assert result.output == "hello\n"
        assert result.session == "default"
        assert result.exit_code == 0

    async def test_bash_command_custom_session(self, default_policy):
        sandbox = SeatbeltSandbox(default_policy)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = b"ok\n"
        mock_proc.stderr = b""

        with patch(f"{MODULE}.subprocess.run", return_value=mock_proc):
            result = await sandbox.bash_command("echo ok", session="dev")

        assert result.session == "dev"

    async def test_bash_command_with_stderr(self, default_policy):
        sandbox = SeatbeltSandbox(default_policy)
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = b"output\n"
        mock_proc.stderr = b"error\n"

        with patch(f"{MODULE}.subprocess.run", return_value=mock_proc):
            result = await sandbox.bash_command("bad_cmd")

        assert "output\n" in result.output
        assert "[stderr]" in result.output
        assert "error\n" in result.output

    async def test_bash_command_timeout(self, default_policy):
        sandbox = SeatbeltSandbox(default_policy)
        exc = subprocess.TimeoutExpired(
            cmd=["sandbox-exec"],
            timeout=5,
            output=b"partial",
            stderr=b"",
        )

        with patch(f"{MODULE}.subprocess.run", side_effect=exc):
            result = await sandbox.bash_command("sleep 999", timeout=5)

        assert "[timed out]" in result.output
        assert result.exit_code == 124

    async def test_bash_command_only_stderr(self, default_policy):
        sandbox = SeatbeltSandbox(default_policy)
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = b""
        mock_proc.stderr = b"error only\n"

        with patch(f"{MODULE}.subprocess.run", return_value=mock_proc):
            result = await sandbox.bash_command("bad_cmd")

        assert result.output == "error only\n"

    async def test_bash_command_timeout_no_output(self, default_policy):
        sandbox = SeatbeltSandbox(default_policy)
        exc = subprocess.TimeoutExpired(
            cmd=["sandbox-exec"],
            timeout=5,
            output=None,
            stderr=None,
        )

        with patch(f"{MODULE}.subprocess.run", side_effect=exc):
            result = await sandbox.bash_command("sleep 999", timeout=5)

        assert result.output == "[timed out]\n"


class TestSeatbeltSandboxIntegration:
    """Integration-style tests that verify the full flow."""

    async def test_profile_includes_policy_paths(self, custom_policy):
        sandbox = SeatbeltSandbox(custom_policy)
        profile = sandbox.profile

        # read_only_paths are covered by blanket (allow file-read*) — not emitted
        # Verify writable and denied paths are in the generated profile
        assert "(allow file-read*)" in profile
        assert "/tmp/workspace" in profile
        assert "/etc/shadow" in profile

    async def test_multiple_commands_independent(self, default_policy):
        sandbox = SeatbeltSandbox(default_policy)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = b"ok\n"
        mock_proc.stderr = b""

        with patch(f"{MODULE}.subprocess.run", return_value=mock_proc) as mock_run:
            await sandbox.exec_command("echo 1")
            await sandbox.exec_command("echo 2")

        # Each command should spawn a fresh sandbox-exec
        assert mock_run.call_count == 2


class TestBackendPolicy:
    def test_default_values(self):
        policy = BackendPolicy()
        assert policy.read_only_paths == ()
        assert policy.writable_paths == ()
        assert policy.denied_paths == ()
        assert policy.network == NetworkMode.NONE
        assert policy.allowed_hosts == ()
        assert policy.default_timeout == 120
        assert policy.max_timeout == 600
        assert policy.working_dir == "/tmp"

    def test_custom_values(self):
        policy = BackendPolicy(
            read_only_paths=("/usr",),
            writable_paths=("/tmp",),
            denied_paths=("/etc",),
            network=NetworkMode.ALLOW_ALL,
            allowed_hosts=("example.com",),
            default_timeout=60,
            max_timeout=300,
            working_dir="/workspace",
        )
        assert policy.read_only_paths == ("/usr",)
        assert policy.writable_paths == ("/tmp",)
        assert policy.denied_paths == ("/etc",)
        assert policy.network == NetworkMode.ALLOW_ALL
        assert policy.allowed_hosts == ("example.com",)
        assert policy.default_timeout == 60
        assert policy.max_timeout == 300
        assert policy.working_dir == "/workspace"

    def test_frozen_dataclass(self):
        policy = BackendPolicy()
        with pytest.raises(dataclasses.FrozenInstanceError):
            policy.network = NetworkMode.ALLOW_ALL


class TestNetworkMode:
    def test_enum_values(self):
        assert NetworkMode.NONE.value == "none"
        assert NetworkMode.ALLOW_ALL.value == "allow_all"
        assert NetworkMode.RESTRICTED.value == "restricted"

    def test_enum_comparison(self):
        assert NetworkMode.NONE == NetworkMode.NONE
        assert NetworkMode.NONE != NetworkMode.ALLOW_ALL
