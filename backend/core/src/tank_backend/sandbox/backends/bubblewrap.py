"""Bubblewrap (Linux) sandbox backend.

Uses bubblewrap (bwrap) to run commands in a restricted environment.
Bubblewrap provides namespace-based isolation on Linux with fine-grained
filesystem and network controls.

Network filtering:
- "none": --unshare-net (no network access)
- "allow_all": --share-net (full network access)
- "restricted": --unshare-net + socat proxy for allowed hosts

Limitations:
- Stateless: each exec_command spawns a fresh bwrap process.
- No persistent sessions (bash_command wraps exec_command).
- Restricted network mode requires socat for host filtering.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess

from ..types import BashResult, ExecResult, ProcessOutput, SandboxCapabilities
from .shared import BackendPolicy, NetworkMode

logger = logging.getLogger(__name__)


# ── Bubblewrap command builder ────────────────────────────────────


def _build_bwrap_args(
    policy: BackendPolicy,
    command: str,
    working_dir: str,
) -> list[str]:
    """Build bwrap command-line arguments from policy.

    Returns a list like:
        ["bwrap", "--ro-bind", "/usr", "/usr", ..., "bash", "-c", command]
    """
    args = ["bwrap"]

    # Filesystem bindings
    # Denied paths are simply not mounted (bwrap denies by default)
    denied_set = set(policy.denied_paths)

    for path in policy.read_only_paths:
        if path not in denied_set:
            args.extend(["--ro-bind", path, path])

    for path in policy.writable_paths:
        if path not in denied_set:
            args.extend(["--bind", path, path])

    # Always bind essential device nodes
    args.extend([
        "--dev-bind", "/dev/null", "/dev/null",
        "--dev-bind", "/dev/zero", "/dev/zero",
        "--dev-bind", "/dev/random", "/dev/random",
        "--dev-bind", "/dev/urandom", "/dev/urandom",
    ])

    # Proc filesystem (needed for many commands)
    args.extend(["--proc", "/proc"])

    # Network configuration
    if policy.network == NetworkMode.NONE:
        args.append("--unshare-net")
    elif policy.network == NetworkMode.ALLOW_ALL:
        args.append("--share-net")
    elif policy.network == NetworkMode.RESTRICTED:
        # For restricted mode, we unshare network and would need socat proxy
        # For now, just unshare (socat setup is complex and requires runtime state)
        args.append("--unshare-net")
        if policy.allowed_hosts:
            logger.warning(
                "Restricted network mode with allowed_hosts not fully implemented. "
                "Network is disabled. Allowed hosts: %s",
                policy.allowed_hosts,
            )

    # Die with parent process
    args.append("--die-with-parent")

    # Set working directory
    args.extend(["--chdir", working_dir])

    # Execute command via bash
    args.extend(["bash", "-c", command])

    return args


# ── Sandbox implementation ────────────────────────────────────────


class BubblewrapSandbox:
    """Linux Bubblewrap sandbox backend.

    Satisfies the ``Sandbox`` protocol. Each command is executed in an
    isolated ``bwrap`` invocation — there is no persistent container or session.
    """

    def __init__(self, policy: BackendPolicy | None = None) -> None:
        self._policy = policy or BackendPolicy()

        from .process_tracker import ProcessTracker

        self._tracker = ProcessTracker()

    # ── Sandbox protocol ──────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """Always True — Bubblewrap is stateless."""
        return True

    @property
    def capabilities(self) -> SandboxCapabilities:
        return SandboxCapabilities(
            persistent_sessions=False,
            background_processes=True,
            same_path_mounts=True,
            backend_name="bubblewrap",
        )

    async def cleanup(self) -> None:
        """Kill any tracked background processes."""
        self._tracker.cleanup()

    async def exec_command(
        self,
        command: str,
        timeout: int | None = None,
        working_dir: str | None = None,
        background: bool = False,
    ) -> ExecResult:
        """Run *command* inside a Bubblewrap sandbox and return the result."""
        effective_timeout = self._effective_timeout(timeout)
        cwd = working_dir or self._policy.working_dir

        if background:
            return await asyncio.to_thread(
                self._exec_background, command, cwd
            )

        return await asyncio.to_thread(
            self._exec_sync, command, effective_timeout, cwd
        )

    async def bash_command(
        self,
        command: str,
        session: str = "default",
        timeout: int | None = None,
    ) -> BashResult:
        """Run *command* via exec_command (no persistent session).

        The *session* parameter is accepted for protocol compatibility
        but has no effect — Bubblewrap is stateless.
        """
        result = await self.exec_command(command, timeout=timeout)
        output = result.stdout
        if result.stderr:
            output = f"{output}[stderr]\n{result.stderr}" if output else result.stderr
        if result.timed_out:
            output = f"{output}[timed out]\n" if output else "[timed out]\n"
        return BashResult(
            output=output,
            session=session,
            exit_code=result.exit_code,
        )

    # ── Background process management ────────────────────────────

    def list_processes(self) -> list[dict]:
        return self._tracker.list_all()

    async def poll_process(self, process_id: str) -> ProcessOutput:
        return self._tracker.poll(process_id)

    async def kill_process(self, process_id: str) -> None:
        self._tracker.kill(process_id)

    async def process_log(self, process_id: str) -> str:
        return self._tracker.log(process_id)

    # ── Internals ─────────────────────────────────────────────────

    def _effective_timeout(self, timeout: int | None) -> int:
        """Clamp an optional timeout to [default, max]."""
        return min(
            timeout or self._policy.default_timeout,
            self._policy.max_timeout,
        )

    def _exec_background(self, command: str, working_dir: str) -> ExecResult:
        """Start a background process and return its ID."""
        cmd = _build_bwrap_args(self._policy, command, working_dir)
        try:
            process_id = self._tracker.start(cmd, command, working_dir)
            return ExecResult(
                stdout=process_id,
                stderr="",
                exit_code=0,
                timed_out=False,
            )
        except RuntimeError as exc:
            return ExecResult(
                stdout="",
                stderr=str(exc),
                exit_code=1,
                timed_out=False,
            )

    def _exec_sync(
        self, command: str, timeout: int, working_dir: str
    ) -> ExecResult:
        """Blocking subprocess call — runs on a thread via to_thread."""
        cmd = _build_bwrap_args(self._policy, command, working_dir)

        logger.debug(
            "bubblewrap exec: %s (timeout=%ds, cwd=%s)", command, timeout, working_dir
        )

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                cwd="/",  # bwrap handles chdir internally
            )
            return ExecResult(
                stdout=proc.stdout.decode("utf-8", errors="replace"),
                stderr=proc.stderr.decode("utf-8", errors="replace"),
                exit_code=proc.returncode,
                timed_out=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = (exc.stdout or b"").decode("utf-8", errors="replace")
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
            return ExecResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=124,
                timed_out=True,
            )
        except FileNotFoundError:
            return ExecResult(
                stdout="",
                stderr="bwrap not found — is bubblewrap installed?",
                exit_code=127,
                timed_out=False,
            )
        except OSError as exc:
            return ExecResult(
                stdout="",
                stderr=f"Failed to launch bwrap: {exc}",
                exit_code=1,
                timed_out=False,
            )
