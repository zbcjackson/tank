"""Sandbox protocol — structural interface for all sandbox backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import BashResult, ExecResult


@runtime_checkable
class Sandbox(Protocol):
    """Structural interface every sandbox backend must satisfy.

    This protocol defines the minimal contract for running commands in a sandbox.
    Concrete implementations (Docker, Seatbelt, Bubblewrap) provide the actual
    sandboxing mechanism.

    The protocol is intentionally minimal — session management methods
    (session_read, session_write, etc.) are optional extensions that only
    DockerSandbox provides today. Tools that need them depend on DockerSandbox
    directly.
    """

    async def exec_command(
        self,
        command: str,
        timeout: int | None = None,
        working_dir: str = "/workspace",
    ) -> ExecResult:
        """Run a command to completion and return its output.

        Args:
            command: Shell command to execute
            timeout: Maximum execution time in seconds (None = use default)
            working_dir: Working directory for the command

        Returns:
            ExecResult with stdout, stderr, exit_code, and timed_out flag
        """
        ...

    async def bash_command(
        self,
        command: str,
        session: str = "default",
        timeout: int | None = None,
    ) -> BashResult:
        """Send a command to a bash session and wait for output.

        For stateless backends (Seatbelt, Bubblewrap), this is just a wrapper
        around exec_command. For stateful backends (Docker), this maintains
        persistent PTY sessions where working directory and env vars persist.

        Args:
            command: Shell command to execute
            session: Session identifier (ignored by stateless backends)
            timeout: Maximum execution time in seconds (None = use default)

        Returns:
            BashResult with output, session name, and optional exit_code
        """
        ...

    async def cleanup(self) -> None:
        """Clean up sandbox resources.

        For Docker: stop and remove container, close all sessions.
        For stateless backends: no-op.
        """
        ...

    @property
    def is_running(self) -> bool:
        """Check if the sandbox is running.

        For Docker: True if container exists.
        For stateless backends: always True.
        """
        ...
