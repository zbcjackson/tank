"""Data types for the sandbox module."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SessionStatus(str, Enum):
    """Status of a bash session."""

    RUNNING = "running"
    EXITED = "exited"


@dataclass(frozen=True)
class SandboxCapabilities:
    """Describes what a sandbox backend can do.

    Tools use this to adapt their behavior — e.g. ``sandbox_bash`` is
    only offered when ``persistent_sessions`` is True.
    """

    persistent_sessions: bool = False
    background_processes: bool = False
    same_path_mounts: bool = False
    backend_name: str = "unknown"


@dataclass(frozen=True)
class ExecResult:
    """Result of a one-shot command execution."""

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
        }


@dataclass(frozen=True)
class BashResult:
    """Result of a bash session command."""

    output: str
    session: str
    exit_code: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"output": self.output, "session": self.session}
        if self.exit_code is not None:
            result["exit_code"] = self.exit_code
        return result


@dataclass
class SessionInfo:
    """Tracks a persistent bash session inside the container."""

    name: str
    exec_id: str
    socket: Any = None  # docker socket object
    status: SessionStatus = SessionStatus.RUNNING
    output_buffer: deque[str] = field(default_factory=lambda: deque(maxlen=10000))
    poll_offset: int = 0  # index into output_buffer for incremental reads

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "output_lines": len(self.output_buffer),
        }


class ProcessStatus(str, Enum):
    """Status of a background process."""

    RUNNING = "running"
    EXITED = "exited"


@dataclass
class ProcessInfo:
    """Tracks a background process across all backends.

    For Docker: wraps a detached exec ID.
    For Seatbelt/Bubblewrap: wraps a ``subprocess.Popen`` object.
    """

    process_id: str
    command: str
    handle: Any = None  # Popen or Docker exec_id
    status: ProcessStatus = ProcessStatus.RUNNING
    exit_code: int | None = None
    output_buffer: deque[str] = field(default_factory=lambda: deque(maxlen=10000))
    poll_offset: int = 0

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "process_id": self.process_id,
            "command": self.command,
            "status": self.status.value,
            "output_lines": len(self.output_buffer),
        }
        if self.exit_code is not None:
            result["exit_code"] = self.exit_code
        return result


@dataclass(frozen=True)
class ProcessOutput:
    """Output from polling a background process."""

    output: str
    status: str
    exit_code: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"output": self.output, "status": self.status}
        if self.exit_code is not None:
            result["exit_code"] = self.exit_code
        return result
