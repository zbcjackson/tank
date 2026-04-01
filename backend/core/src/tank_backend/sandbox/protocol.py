"""Sandbox protocol — structural interface for all sandbox backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import BashResult, ExecResult, ProcessOutput, SandboxCapabilities


@runtime_checkable
class Sandbox(Protocol):
    """Structural interface every sandbox backend must satisfy.

    This protocol defines the minimal contract for running commands in a sandbox.
    Concrete implementations (Docker, Seatbelt, Bubblewrap) provide the actual
    sandboxing mechanism.

    Session management methods (session_read, session_write, etc.) are optional
    extensions that only DockerSandbox provides today. Tools that need them
    depend on DockerSandbox directly.

    Background process methods (list_processes, poll_process, kill_process,
    process_log) are part of the protocol and work on all backends.
    """

    @property
    def capabilities(self) -> SandboxCapabilities:
        """Describe what this backend supports."""
        ...

    async def exec_command(
        self,
        command: str,
        timeout: int | None = None,
        working_dir: str = "/workspace",
        background: bool = False,
    ) -> ExecResult:
        """Run a command and return its output.

        Args:
            command: Shell command to execute.
            timeout: Maximum execution time in seconds (None = use default).
            working_dir: Working directory for the command.
            background: If True, start the process in the background and
                return immediately.  ``stdout`` will contain the process ID.

        Returns:
            ExecResult with stdout, stderr, exit_code, and timed_out flag.
            When *background* is True, ``stdout`` is the process ID and
            ``exit_code`` is 0.
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
        """
        ...

    async def cleanup(self) -> None:
        """Clean up sandbox resources."""
        ...

    @property
    def is_running(self) -> bool:
        """Check if the sandbox is running."""
        ...

    # ── Background process management ────────────────────────────

    def list_processes(self) -> list[dict]:
        """List all tracked background processes."""
        ...

    async def poll_process(self, process_id: str) -> ProcessOutput:
        """Read new output from a background process since last poll."""
        ...

    async def kill_process(self, process_id: str) -> None:
        """Kill a background process."""
        ...

    async def process_log(self, process_id: str) -> str:
        """Full output history for a background process."""
        ...
