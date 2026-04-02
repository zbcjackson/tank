"""Seatbelt (macOS) sandbox backend.

Uses macOS sandbox-exec to run commands in a restricted environment.
Seatbelt profiles are generated dynamically from BackendPolicy using
Apple's Scheme-based sandbox profile language (SBPL).

Limitations:
- Seatbelt cannot filter outbound network by hostname natively.
  In "restricted" network mode we allow all outbound and document
  the limitation.
- Stateless: each exec_command invocation spawns a fresh sandbox-exec
  process. There are no persistent sessions.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess

from ..types import BashResult, ExecResult, ProcessOutput, SandboxCapabilities
from .shared import BackendPolicy, NetworkMode

logger = logging.getLogger(__name__)


# ── Profile generation ────────────────────────────────────────────


def _quote(path: str) -> str:
    """Quote a path for use inside an SBPL literal string."""
    return path.replace("\\", "\\\\").replace('"', '\\"')


def _build_seatbelt_profile(policy: BackendPolicy) -> str:
    """Generate a Scheme-syntax Seatbelt profile from *policy*.

    Strategy: allow-read-default, deny sensitive paths.

    Modern macOS bash/coreutils need access to dyld shared cache, system
    frameworks, and other paths that are impractical to enumerate.  Instead
    of deny-default + allow-specific, we allow all reads by default and
    explicitly deny sensitive paths (``~/.ssh``, ``~/.gnupg``, etc.).

    Writes are still deny-default — only explicitly listed writable paths
    are allowed.
    """
    lines: list[str] = [
        "(version 1)",
        "(deny default)",
        "",
        ";; --- baseline: allow process execution and IPC ---",
        "(allow process-exec)",
        "(allow process-fork)",
        "(allow sysctl-read)",
        "(allow mach-lookup)",
        "(allow mach-register)",
        "(allow signal (target self))",
        "",
        ";; --- filesystem: allow-read-default, deny-write-default ---",
        "(allow file-read*)",
    ]

    # Denied paths — block both read and write
    if policy.denied_paths:
        lines.append("")
        lines.append(";; --- denied paths (sensitive) ---")
        for p in policy.denied_paths:
            lines.append(f'(deny file-read* (subpath "{_quote(p)}"))')
            lines.append(f'(deny file-write* (subpath "{_quote(p)}"))')

    # Writable paths — explicitly allowed
    if policy.writable_paths:
        lines.append("")
        lines.append(";; --- writable paths ---")
        for p in policy.writable_paths:
            lines.append(f'(allow file-write* (subpath "{_quote(p)}"))')

    # Always allow writing to /dev/null and /dev/tty
    lines.append("")
    lines.append(";; --- device writes ---")
    lines.append('(allow file-write* (literal "/dev/null"))')
    lines.append('(allow file-write* (literal "/dev/tty"))')

    # Network
    lines.append("")
    lines.append(";; --- network ---")
    if policy.network == NetworkMode.NONE:
        lines.append("(deny network*)")
    elif policy.network in (NetworkMode.ALLOW_ALL, NetworkMode.RESTRICTED):
        lines.append("(allow network*)")
        if policy.network == NetworkMode.RESTRICTED and policy.allowed_hosts:
            lines.append(
                f";; advisory: intended hosts = {', '.join(policy.allowed_hosts)}"
            )

    lines.append("")
    return "\n".join(lines)


# ── Sandbox implementation ────────────────────────────────────────


class SeatbeltSandbox:
    """macOS Seatbelt sandbox backend.

    Satisfies the ``Sandbox`` protocol.  Each command is executed in an
    isolated ``sandbox-exec`` invocation — there is no persistent
    container or session.
    """

    def __init__(self, policy: BackendPolicy | None = None) -> None:
        self._policy = policy or BackendPolicy()
        self._profile = _build_seatbelt_profile(self._policy)

        from .process_tracker import ProcessTracker

        self._tracker = ProcessTracker()

    # ── Sandbox protocol ──────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """Always True — Seatbelt is stateless."""
        return True

    @property
    def capabilities(self) -> SandboxCapabilities:
        return SandboxCapabilities(
            persistent_sessions=False,
            background_processes=True,
            same_path_mounts=True,
            backend_name="seatbelt",
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
        """Run *command* inside a Seatbelt sandbox and return the result."""
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
        but has no effect — Seatbelt is stateless.
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

    def _seatbelt_cmd(self, command: str) -> list[str]:
        """Build the sandbox-exec command list."""
        return [
            "/usr/bin/sandbox-exec",
            "-p",
            self._profile,
            "bash",
            "-c",
            command,
        ]

    def _exec_background(self, command: str, working_dir: str) -> ExecResult:
        """Start a background process and return its ID."""
        cmd = self._seatbelt_cmd(command)
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
        cmd = self._seatbelt_cmd(command)

        logger.debug("seatbelt exec: %s (timeout=%ds, cwd=%s)", command, timeout, working_dir)

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                cwd=working_dir,
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
                stderr=(
                    "sandbox-exec not found. "
                    "Expected at /usr/bin/sandbox-exec on macOS."
                ),
                exit_code=127,
                timed_out=False,
            )
        except OSError as exc:
            return ExecResult(
                stdout="",
                stderr=f"Failed to launch sandbox-exec: {exc}",
                exit_code=1,
                timed_out=False,
            )

    @property
    def profile(self) -> str:
        """Return the generated Seatbelt profile (useful for debugging)."""
        return self._profile
