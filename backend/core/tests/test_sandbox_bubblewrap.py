"""Tests for Bubblewrap sandbox backend."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from tank_backend.sandbox.backends.bubblewrap import (
    BubblewrapSandbox,
    NetworkMode,
    SandboxPolicy,
    _build_bwrap_args,
)

# ── Policy and argument generation tests ──────────────────────────


class TestBuildBwrapArgs:
    """Test bwrap command-line argument generation."""

    def test_minimal_policy(self):
        """Test with minimal policy (no paths, no network)."""
        policy = SandboxPolicy()
        args = _build_bwrap_args(policy, "echo hello", "/tmp")

        assert args[0] == "bwrap"
        assert "--unshare-net" in args
        assert "--die-with-parent" in args
        assert "--chdir" in args
        assert "/tmp" in args
        assert "bash" in args
        assert "-c" in args
        assert "echo hello" in args

    def test_read_only_paths(self):
        """Test read-only path bindings."""
        policy = SandboxPolicy(
            read_only_paths=("/usr", "/lib", "/bin"),
        )
        args = _build_bwrap_args(policy, "ls", "/tmp")

        assert "--ro-bind" in args
        # Each path appears twice (source and dest)
        assert args.count("/usr") == 2
        assert args.count("/lib") == 2
        assert args.count("/bin") == 2

    def test_writable_paths(self):
        """Test writable path bindings."""
        policy = SandboxPolicy(
            writable_paths=("/tmp", "/workspace"),
        )
        args = _build_bwrap_args(policy, "touch file", "/tmp")

        assert "--bind" in args
        assert args.count("/tmp") >= 2  # At least source and dest
        assert args.count("/workspace") == 2

    def test_denied_paths_excluded(self):
        """Test that denied paths are not mounted."""
        policy = SandboxPolicy(
            read_only_paths=("/usr", "/etc"),
            denied_paths=("/etc",),
        )
        args = _build_bwrap_args(policy, "cat /etc/passwd", "/tmp")

        # /usr should be mounted
        assert "/usr" in args
        # /etc should NOT be mounted (denied)
        # Count occurrences - should only appear in denied_paths, not in bindings
        etc_indices = [i for i, arg in enumerate(args) if arg == "/etc"]
        # If /etc appears, it should not be after --ro-bind or --bind
        for idx in etc_indices:
            if idx > 0:
                assert args[idx - 1] not in ("--ro-bind", "--bind")

    def test_network_none(self):
        """Test network disabled mode."""
        policy = SandboxPolicy(network=NetworkMode.NONE)
        args = _build_bwrap_args(policy, "curl example.com", "/tmp")

        assert "--unshare-net" in args
        assert "--share-net" not in args

    def test_network_allow_all(self):
        """Test network enabled mode."""
        policy = SandboxPolicy(network=NetworkMode.ALLOW_ALL)
        args = _build_bwrap_args(policy, "curl example.com", "/tmp")

        assert "--share-net" in args
        assert "--unshare-net" not in args

    def test_network_restricted(self):
        """Test restricted network mode (currently unshares network)."""
        policy = SandboxPolicy(
            network=NetworkMode.RESTRICTED,
            allowed_hosts=("example.com", "api.github.com"),
        )
        args = _build_bwrap_args(policy, "curl example.com", "/tmp")

        # Currently restricted mode just unshares network
        assert "--unshare-net" in args

    def test_essential_devices_always_bound(self):
        """Test that essential device nodes are always bound."""
        policy = SandboxPolicy()
        args = _build_bwrap_args(policy, "echo test", "/tmp")

        assert "--dev-bind" in args
        assert "/dev/null" in args
        assert "/dev/zero" in args
        assert "/dev/random" in args
        assert "/dev/urandom" in args

    def test_proc_filesystem_mounted(self):
        """Test that /proc is mounted."""
        policy = SandboxPolicy()
        args = _build_bwrap_args(policy, "ps", "/tmp")

        assert "--proc" in args
        assert "/proc" in args

    def test_working_directory_set(self):
        """Test that working directory is set correctly."""
        policy = SandboxPolicy()
        args = _build_bwrap_args(policy, "pwd", "/custom/path")

        assert "--chdir" in args
        chdir_idx = args.index("--chdir")
        assert args[chdir_idx + 1] == "/custom/path"

    def test_command_passed_to_bash(self):
        """Test that command is passed to bash -c."""
        policy = SandboxPolicy()
        command = "echo 'hello world' && ls -la"
        args = _build_bwrap_args(policy, command, "/tmp")

        assert "bash" in args
        assert "-c" in args
        bash_idx = args.index("bash")
        assert args[bash_idx + 1] == "-c"
        assert args[bash_idx + 2] == command


# ── BubblewrapSandbox class tests ──────────────────────────────────


class TestBubblewrapSandbox:
    """Test BubblewrapSandbox class."""

    def test_init_default_policy(self):
        """Test initialization with default policy."""
        sandbox = BubblewrapSandbox()
        assert sandbox.is_running is True
        assert sandbox._policy is not None

    def test_init_custom_policy(self):
        """Test initialization with custom policy."""
        policy = SandboxPolicy(
            read_only_paths=("/usr",),
            default_timeout=60,
        )
        sandbox = BubblewrapSandbox(policy)
        assert sandbox._policy == policy
        assert sandbox._policy.default_timeout == 60

    def test_is_running_always_true(self):
        """Test that is_running is always True (stateless)."""
        sandbox = BubblewrapSandbox()
        assert sandbox.is_running is True

    async def test_cleanup_noop(self):
        """Test that cleanup is a no-op."""
        sandbox = BubblewrapSandbox()
        await sandbox.cleanup()  # Should not raise

    def test_effective_timeout_default(self):
        """Test timeout defaults to policy default."""
        policy = SandboxPolicy(default_timeout=100)
        sandbox = BubblewrapSandbox(policy)
        assert sandbox._effective_timeout(None) == 100

    def test_effective_timeout_custom(self):
        """Test custom timeout is used when provided."""
        policy = SandboxPolicy(default_timeout=100)
        sandbox = BubblewrapSandbox(policy)
        assert sandbox._effective_timeout(50) == 50

    def test_effective_timeout_clamped_to_max(self):
        """Test timeout is clamped to max_timeout."""
        policy = SandboxPolicy(default_timeout=100, max_timeout=200)
        sandbox = BubblewrapSandbox(policy)
        assert sandbox._effective_timeout(300) == 200


# ── exec_command tests ────────────────────────────────────────────


MODULE = "tank_backend.sandbox.backends.bubblewrap"


class TestExecCommand:
    """Test exec_command method."""

    async def test_exec_command_success(self):
        """Test successful command execution."""
        sandbox = BubblewrapSandbox()

        with patch(f"{MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=b"hello world\n",
                stderr=b"",
                returncode=0,
            )

            result = await sandbox.exec_command("echo hello world")

            assert result.stdout == "hello world\n"
            assert result.stderr == ""
            assert result.exit_code == 0
            assert result.timed_out is False
            mock_run.assert_called_once()

    async def test_exec_command_with_stderr(self):
        """Test command execution with stderr output."""
        sandbox = BubblewrapSandbox()

        with patch(f"{MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=b"",
                stderr=b"command not found\n",
                returncode=127,
            )

            result = await sandbox.exec_command("nonexistent_cmd")

            assert result.stdout == ""
            assert result.stderr == "command not found\n"
            assert result.exit_code == 127
            assert result.timed_out is False

    async def test_exec_command_timeout(self):
        """Test command execution timeout."""
        sandbox = BubblewrapSandbox()

        with patch(f"{MODULE}.subprocess.run") as mock_run:
            exc = subprocess.TimeoutExpired(
                cmd=["bwrap"],
                timeout=5,
                output=b"partial output",
                stderr=b"",
            )
            mock_run.side_effect = exc

            result = await sandbox.exec_command("sleep 999", timeout=5)

            assert result.stdout == "partial output"
            assert result.exit_code == 124
            assert result.timed_out is True

    async def test_exec_command_bwrap_not_found(self):
        """Test error when bwrap is not installed."""
        sandbox = BubblewrapSandbox()

        with patch(f"{MODULE}.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()

            result = await sandbox.exec_command("echo test")

            assert result.exit_code == 127
            assert "bwrap not found" in result.stderr
            assert result.timed_out is False

    async def test_exec_command_os_error(self):
        """Test handling of OS errors."""
        sandbox = BubblewrapSandbox()

        with patch(f"{MODULE}.subprocess.run") as mock_run:
            mock_run.side_effect = OSError("Permission denied")

            result = await sandbox.exec_command("echo test")

            assert result.exit_code == 1
            assert "Failed to launch bwrap" in result.stderr
            assert "Permission denied" in result.stderr

    async def test_exec_command_custom_working_dir(self):
        """Test command execution with custom working directory."""
        sandbox = BubblewrapSandbox()

        with patch(f"{MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=b"/custom/path\n",
                stderr=b"",
                returncode=0,
            )

            await sandbox.exec_command("pwd", working_dir="/custom/path")

            # Verify bwrap args include --chdir /custom/path
            call_args = mock_run.call_args[0][0]
            assert "--chdir" in call_args
            chdir_idx = call_args.index("--chdir")
            assert call_args[chdir_idx + 1] == "/custom/path"

    async def test_exec_command_uses_policy_working_dir(self):
        """Test that policy working_dir is used when not specified."""
        policy = SandboxPolicy(working_dir="/workspace")
        sandbox = BubblewrapSandbox(policy)

        with patch(f"{MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=b"",
                stderr=b"",
                returncode=0,
            )

            await sandbox.exec_command("ls")

            call_args = mock_run.call_args[0][0]
            assert "--chdir" in call_args
            chdir_idx = call_args.index("--chdir")
            assert call_args[chdir_idx + 1] == "/workspace"

    async def test_exec_command_utf8_decoding(self):
        """Test UTF-8 decoding with error handling."""
        sandbox = BubblewrapSandbox()

        with patch(f"{MODULE}.subprocess.run") as mock_run:
            # Invalid UTF-8 sequence
            mock_run.return_value = MagicMock(
                stdout=b"hello \xff world",
                stderr=b"",
                returncode=0,
            )

            result = await sandbox.exec_command("echo test")

            # Should decode with replacement character
            assert "hello" in result.stdout
            assert "world" in result.stdout


# ── bash_command tests ────────────────────────────────────────────


class TestBashCommand:
    """Test bash_command method."""

    async def test_bash_command_success(self):
        """Test successful bash command."""
        sandbox = BubblewrapSandbox()

        with patch(f"{MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=b"output\n",
                stderr=b"",
                returncode=0,
            )

            result = await sandbox.bash_command("echo output")

            assert result.output == "output\n"
            assert result.session == "default"
            assert result.exit_code == 0

    async def test_bash_command_custom_session(self):
        """Test bash command with custom session name."""
        sandbox = BubblewrapSandbox()

        with patch(f"{MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=b"test\n",
                stderr=b"",
                returncode=0,
            )

            result = await sandbox.bash_command("echo test", session="custom")

            assert result.session == "custom"

    async def test_bash_command_with_stderr(self):
        """Test bash command with stderr output."""
        sandbox = BubblewrapSandbox()

        with patch(f"{MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=b"stdout\n",
                stderr=b"stderr\n",
                returncode=1,
            )

            result = await sandbox.bash_command("bad_cmd")

            assert "stdout\n" in result.output
            assert "[stderr]" in result.output
            assert "stderr\n" in result.output
            assert result.exit_code == 1

    async def test_bash_command_timeout(self):
        """Test bash command timeout."""
        sandbox = BubblewrapSandbox()

        with patch(f"{MODULE}.subprocess.run") as mock_run:
            exc = subprocess.TimeoutExpired(
                cmd=["bwrap"],
                timeout=5,
                output=b"partial",
                stderr=b"",
            )
            mock_run.side_effect = exc

            result = await sandbox.bash_command("sleep 999", timeout=5)

            assert "partial" in result.output
            assert "[timed out]" in result.output
            assert result.exit_code == 124

    async def test_bash_command_no_output(self):
        """Test bash command with no output."""
        sandbox = BubblewrapSandbox()

        with patch(f"{MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=b"",
                stderr=b"",
                returncode=0,
            )

            result = await sandbox.bash_command("true")

            assert result.output == ""
            assert result.exit_code == 0


# ── Integration-style tests ───────────────────────────────────────


class TestBubblewrapIntegration:
    """Integration-style tests (still mocked, but test full flow)."""

    async def test_full_command_flow(self):
        """Test complete command execution flow."""
        policy = SandboxPolicy(
            read_only_paths=("/usr", "/lib"),
            writable_paths=("/tmp",),
            network=NetworkMode.ALLOW_ALL,
            default_timeout=30,
        )
        sandbox = BubblewrapSandbox(policy)

        with patch(f"{MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=b"success\n",
                stderr=b"",
                returncode=0,
            )

            result = await sandbox.exec_command(
                "echo success",
                timeout=10,
                working_dir="/tmp",
            )

            assert result.stdout == "success\n"
            assert result.exit_code == 0

            # Verify bwrap args
            call_args = mock_run.call_args[0][0]
            assert call_args[0] == "bwrap"
            assert "--ro-bind" in call_args
            assert "--bind" in call_args
            assert "--share-net" in call_args
            assert "--chdir" in call_args

    async def test_protocol_compliance(self):
        """Test that BubblewrapSandbox satisfies Sandbox protocol."""
        from tank_backend.sandbox.protocol import Sandbox

        sandbox = BubblewrapSandbox()

        # Check protocol compliance
        assert isinstance(sandbox, Sandbox)
        assert hasattr(sandbox, "exec_command")
        assert hasattr(sandbox, "bash_command")
        assert hasattr(sandbox, "cleanup")
        assert hasattr(sandbox, "is_running")
