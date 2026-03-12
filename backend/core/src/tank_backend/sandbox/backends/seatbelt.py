"""Seatbelt (macOS) sandbox backend.

Uses macOS sandbox-exec to run commands in a restricted environment.
Seatbelt profiles are generated dynamically from SandboxPolicy using
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
from dataclasses import dataclass
from enum import Enum

from ..types import BashResult, ExecResult

logger = logging.getLogger(__name__)


# ── Policy types ──────────────────────────────────────────────────


class NetworkMode(str, Enum):
    """Network access level for the sandbox."""

    NONE = "none"
    ALLOW_ALL = "allow_all"
    RESTRICTED = "restricted"


@dataclass(frozen=True)
class SandboxPolicy:
    """Declarative policy that drives sandbox profile generation.

    Attributes:
        read_only_paths: Paths the sandboxed process may read.
        writable_paths:  Paths the sandboxed process may read *and* write.
        denied_paths:    Paths explicitly denied (overrides read/write).
        network:         Network access mode.
        allowed_hosts:   Hostnames to allow when network is RESTRICTED.
                         (Documented-only on Seatbelt — cannot be enforced.)
        default_timeout: Seconds before a command is killed.
        max_timeout:     Hard upper bound for any requested timeout.
        working_dir:     Default working directory for commands.
    """

    read_only_paths: tuple[str, ...] = ()
    writable_paths: tuple[str, ...] = ()
    denied_paths: tuple[str, ...] = ()
    network: NetworkMode = NetworkMode.NONE
    allowed_hosts: tuple[str, ...] = ()
    default_timeout: int = 120
    max_timeout: int = 600
    working_dir: str = "/tmp"


# ── Profile generation ────────────────────────────────────────────


def _quote(path: str) -> str:
    """Quote a path for use inside an SBPL literal string."""
    return path.replace("\\", "\\\\").replace('"', '\\"')


def _build_seatbelt_profile(policy: SandboxPolicy) -> str:
    """Generate a Scheme-syntax Seatbelt profile from *policy*.

    The profile starts with ``(version 1)`` and ``(deny default)`` so
    everything is blocked unless explicitly allowed.
    """
    lines: list[str] = [
        "(version 1)",
        "(deny default)",
        "",
        ";; --- baseline: allow process execution and minimal I/O ---",
        "(allow process-exec)",
        "(allow process-fork)",
        "(allow sysctl-read)",
        "(allow mach-lookup)",
        "(allow signal (target self))",
        "",
        ";; --- filesystem ---",
    ]

    # Denied paths first (deny takes priority in profile order)
    for p in policy.denied_paths:
        lines.append(f'(deny file-read* (subpath "{_quote(p)}"))')
        lines.append(f'(deny file-write* (subpath "{_quote(p)}"))')

    # Read-only paths
    for p in policy.read_only_paths:
        lines.append(f'(allow file-read* (subpath "{_quote(p)}"))')

    # Writable paths (implies read)
    for p in policy.writable_paths:
        lines.append(f'(allow file-read* (subpath "{_quote(p)}"))')
        lines.append(f'(allow file-write* (subpath "{_quote(p)}"))')

    # Always allow reading system essentials so bash/coreutils work
    lines.append("")
    lines.append(";; --- system essentials ---")
    lines.append('(allow file-read* (subpath "/usr/lib"))')
    lines.append('(allow file-read* (subpath "/usr/bin"))')
    lines.append('(allow file-read* (subpath "/bin"))')
    lines.append('(allow file-read* (subpath "/usr/share"))')
    lines.append('(allow file-read* (subpath "/dev"))')
    lines.append('(allow file-read* (subpath "/private/var/db"))')
    lines.append('(allow file-read* (literal "/private/etc/shells"))')
    lines.append('(allow file-read* (literal "/dev/null"))')
    lines.append('(allow file-read* (literal "/dev/urandom"))')
    lines.append('(allow file-write* (literal "/dev/null"))')
    lines.append('(allow file-write* (literal "/dev/tty"))')

    # Network
    lines.append("")
    lines.append(";; --- network ---")
    if policy.network == NetworkMode.NONE:
        lines.append("(deny network*)")
    elif policy.network in (NetworkMode.ALLOW_ALL, NetworkMode.RESTRICTED):
        # Seatbelt cannot filter by hostname — allow all outbound.
        # For RESTRICTED mode the allowed_hosts list is advisory only.
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

    def __init__(self, policy: SandboxPolicy | None = None) -> None:
        self._policy = policy or SandboxPolicy()
        self._profile = _build_seatbelt_profile(self._policy)

    # ── Sandbox protocol ──────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """Always True — Seatbelt is stateless."""
        return True

    async def cleanup(self) -> None:
        """No-op — nothing to tear down."""

    async def exec_command(
        self,
        command: str,
        timeout: int | None = None,
        working_dir: str | None = None,
    ) -> ExecResult:
        """Run *command* inside a Seatbelt sandbox and return the result."""
        effective_timeout = self._effective_timeout(timeout)
        cwd = working_dir or self._policy.working_dir

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

    # ── Internals ─────────────────────────────────────────────────

    def _effective_timeout(self, timeout: int | None) -> int:
        """Clamp an optional timeout to [default, max]."""
        return min(
            timeout or self._policy.default_timeout,
            self._policy.max_timeout,
        )

    def _exec_sync(
        self, command: str, timeout: int, working_dir: str
    ) -> ExecResult:
        """Blocking subprocess call — runs on a thread via to_thread."""
        cmd: list[str] = [
            "sandbox-exec",
            "-p",
            self._profile,
            "bash",
            "-c",
            command,
        ]

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
                stderr="sandbox-exec not found — is this macOS?",
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
