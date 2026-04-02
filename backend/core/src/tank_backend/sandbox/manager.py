"""Docker sandbox backend — container lifecycle, exec, and PTY sessions."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shlex
import threading
import time
from pathlib import Path
from typing import Any

from .config import SandboxConfig
from .types import (
    BashResult,
    ExecResult,
    ProcessInfo,
    ProcessOutput,
    ProcessStatus,
    SandboxCapabilities,
    SessionInfo,
    SessionStatus,
)

logger = logging.getLogger(__name__)


def _raw_socket(sock: Any) -> Any:
    """Unwrap the Docker socket to get the underlying raw socket."""
    return sock._sock if hasattr(sock, "_sock") else sock


class DockerSandbox:
    """Docker sandbox backend — manages a container and its bash sessions.

    One DockerSandbox per assistant session. The container is created lazily
    on the first tool call and destroyed when ``cleanup`` is called.
    """

    def __init__(
        self,
        config: SandboxConfig,
        volumes: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self._config = config
        self._volumes = volumes
        self._container: Any | None = None
        self._client: Any | None = None
        self._sessions: dict[str, SessionInfo] = {}
        self._reader_threads: dict[str, threading.Thread] = {}
        self._bg_processes: dict[str, ProcessInfo] = {}
        self._bg_readers: dict[str, threading.Thread] = {}

    # ── Container lifecycle ──────────────────────────────────────

    async def ensure_container(self) -> None:
        """Create the Docker container if it doesn't exist yet."""
        if self._container is not None:
            return
        await asyncio.to_thread(self._create_container)

    def _create_container(self) -> None:
        import docker

        self._client = docker.from_env()

        workspace = str(Path(self._config.workspace_host_path).resolve())
        os.makedirs(workspace, exist_ok=True)

        network_mode = "bridge" if self._config.network_enabled else "none"

        if self._volumes is not None:
            # Same-path mounts: use provided volumes, set HOME to host user's home
            volumes = dict(self._volumes)
            host_home = str(Path.home())
            working_dir = host_home
            environment = {"HOME": host_home}
        else:
            # Legacy: single workspace mount at /workspace
            volumes = {workspace: {"bind": "/workspace", "mode": "rw"}}
            working_dir = "/workspace"
            environment = {}

        self._container = self._client.containers.run(
            image=self._config.image,
            command="sleep infinity",
            detach=True,
            stdin_open=True,
            tty=False,
            working_dir=working_dir,
            volumes=volumes,
            environment=environment or None,
            mem_limit=self._config.memory_limit,
            nano_cpus=self._config.cpu_count * 1_000_000_000,
            network_mode=network_mode,
            remove=True,
            labels={"tank.sandbox": "true"},
        )
        logger.info("Sandbox container started: %s", self._container.short_id)

    async def cleanup(self) -> None:
        """Stop and remove the container, close all sessions."""
        # Kill reader threads first
        for name in list(self._reader_threads):
            self._stop_reader(name)

        if self._container is not None:
            await asyncio.to_thread(self._destroy_container)

    def _destroy_container(self) -> None:
        try:
            self._container.stop(timeout=5)
        except Exception:
            with contextlib.suppress(Exception):
                self._container.kill()
        self._container = None
        self._sessions.clear()
        logger.info("Sandbox container destroyed")

    @property
    def is_running(self) -> bool:
        return self._container is not None

    @property
    def capabilities(self) -> SandboxCapabilities:
        return SandboxCapabilities(
            persistent_sessions=True,
            background_processes=True,
            same_path_mounts=self._volumes is not None,
            backend_name="docker",
        )

    def _effective_timeout(self, timeout: int | None) -> int:
        """Clamp an optional timeout to [default, max]."""
        return min(timeout or self._config.default_timeout, self._config.max_timeout)

    # ── One-shot exec ────────────────────────────────────────────

    async def exec_command(
        self,
        command: str,
        timeout: int | None = None,
        working_dir: str = "/workspace",
        background: bool = False,
    ) -> ExecResult:
        """Run a command to completion, or start it in the background."""
        await self.ensure_container()
        if background:
            return await asyncio.to_thread(
                self._exec_background, command, working_dir
            )
        return await asyncio.to_thread(
            self._exec_sync, command, self._effective_timeout(timeout), working_dir
        )

    def _exec_sync(
        self, command: str, timeout: int, working_dir: str
    ) -> ExecResult:
        wrapped = f"timeout {timeout} bash -c {shlex.quote(command)}"
        exit_code, output = self._container.exec_run(
            ["bash", "-c", wrapped],
            workdir=working_dir,
            demux=True,
        )
        stdout = (output[0] or b"").decode("utf-8", errors="replace")
        stderr = (output[1] or b"").decode("utf-8", errors="replace")
        timed_out = exit_code == 124  # timeout(1) exit code
        return ExecResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            timed_out=timed_out,
        )

    def _exec_background(self, command: str, working_dir: str) -> ExecResult:
        """Start a detached exec inside the container and track it."""
        import uuid

        process_id = uuid.uuid4().hex[:12]

        exec_result = self._client.api.exec_create(
            self._container.id,
            ["bash", "-c", command],
            stdin=False,
            tty=False,
            workdir=working_dir,
        )
        exec_id = exec_result["Id"]
        sock = self._client.api.exec_start(exec_id, socket=True, tty=False)

        info = ProcessInfo(
            process_id=process_id,
            command=command,
            handle=exec_id,
        )
        self._bg_processes[process_id] = info

        thread = threading.Thread(
            target=self._bg_reader_loop,
            args=(process_id, sock),
            daemon=True,
            name=f"bg-reader-{process_id}",
        )
        self._bg_readers[process_id] = thread
        thread.start()

        logger.info("Background process started: %s (exec_id=%s)", process_id, exec_id[:12])
        return ExecResult(stdout=process_id, stderr="", exit_code=0, timed_out=False)

    def _bg_reader_loop(self, process_id: str, sock: Any) -> None:
        """Background thread: read from Docker exec socket into output buffer."""
        info = self._bg_processes.get(process_id)
        if info is None:
            return

        raw = _raw_socket(sock)
        try:
            while True:
                try:
                    data = raw.recv(4096)
                except OSError:
                    break
                if not data:
                    break
                text = data.decode("utf-8", errors="replace")
                info.output_buffer.append(text)
        except Exception as exc:
            logger.debug("BG reader for %s ended: %s", process_id, exc)
        finally:
            # Check exit code via Docker inspect
            try:
                inspect = self._client.api.exec_inspect(info.handle)
                info.exit_code = inspect.get("ExitCode")
            except Exception:
                pass
            info.status = ProcessStatus.EXITED

    # ── Background process management (protocol) ─────────────────

    def list_processes(self) -> list[dict]:
        """List all tracked background processes."""
        return [info.to_dict() for info in self._bg_processes.values()]

    async def poll_process(self, process_id: str) -> ProcessOutput:
        """Read new output from a background process since last poll."""
        info = self._bg_processes.get(process_id)
        if info is None:
            raise ValueError(f"Process '{process_id}' not found")

        buf = info.output_buffer
        offset = info.poll_offset
        current_len = len(buf)
        if current_len <= offset:
            new_text = ""
        else:
            new_text = "".join(list(buf)[offset:current_len])
            info.poll_offset = current_len

        return ProcessOutput(
            output=new_text,
            status=info.status.value,
            exit_code=info.exit_code,
        )

    async def kill_process(self, process_id: str) -> None:
        """Kill a background process by sending SIGKILL to the exec."""
        info = self._bg_processes.get(process_id)
        if info is None:
            raise ValueError(f"Process '{process_id}' not found")
        if info.status == ProcessStatus.RUNNING:
            # Docker doesn't have a direct "kill exec" API — we use exec_inspect
            # to get the PID and then kill it inside the container
            try:
                inspect = self._client.api.exec_inspect(info.handle)
                pid = inspect.get("Pid")
                if pid and pid > 0:
                    self._container.exec_run(["kill", "-9", str(pid)])
            except Exception:
                pass
            info.status = ProcessStatus.EXITED
            logger.info("Background process killed: %s", process_id)

    async def process_log(self, process_id: str) -> str:
        """Full output history for a background process."""
        info = self._bg_processes.get(process_id)
        if info is None:
            raise ValueError(f"Process '{process_id}' not found")
        return "".join(info.output_buffer)

    # ── Persistent bash sessions ─────────────────────────────────

    async def bash_command(
        self,
        command: str,
        session: str = "default",
        timeout: int | None = None,
    ) -> BashResult:
        """Send a command to a persistent bash session and wait for output.

        The session is created implicitly if it doesn't exist.
        Working directory and env vars persist across calls.
        """
        await self.ensure_container()
        if session not in self._sessions:
            await asyncio.to_thread(self._create_session, session)

        info = self._sessions[session]
        if info.status == SessionStatus.EXITED:
            # Recreate dead session
            self._remove_session(session)
            await asyncio.to_thread(self._create_session, session)
            info = self._sessions[session]

        return await asyncio.to_thread(
            self._bash_command_sync, info, command, self._effective_timeout(timeout)
        )

    def _create_session(self, name: str) -> None:
        """Create a new bash session inside the container."""
        exec_result = self._client.api.exec_create(
            self._container.id,
            ["bash"],
            stdin=True,
            tty=True,
            workdir="/workspace",
        )
        exec_id = exec_result["Id"]
        sock = self._client.api.exec_start(exec_id, socket=True, tty=True)

        info = SessionInfo(name=name, exec_id=exec_id, socket=sock)
        self._sessions[name] = info

        # Start background reader thread
        thread = threading.Thread(
            target=self._reader_loop,
            args=(name,),
            daemon=True,
            name=f"sandbox-reader-{name}",
        )
        self._reader_threads[name] = thread
        thread.start()

        logger.info("Created bash session: %s", name)

    def _reader_loop(self, session_name: str) -> None:
        """Background thread that reads from the PTY socket into the buffer."""
        info = self._sessions.get(session_name)
        if info is None or info.socket is None:
            return

        sock = _raw_socket(info.socket)
        try:
            while True:
                try:
                    data = sock.recv(4096)
                except OSError:
                    break
                if not data:
                    break
                text = data.decode("utf-8", errors="replace")
                info.output_buffer.append(text)
        except Exception as e:
            logger.debug("Reader for session %s ended: %s", session_name, e)
        finally:
            info.status = SessionStatus.EXITED

    def _bash_command_sync(
        self, info: SessionInfo, command: str, timeout: int
    ) -> BashResult:
        """Write command to PTY, wait for output, return result."""
        sock = _raw_socket(info.socket)

        # Record buffer position before sending
        start_len = len(info.output_buffer)

        # Use a unique marker to detect command completion
        marker = f"__TANK_DONE_{id(info)}_{time.monotonic_ns()}__"
        full_command = f"{command}\necho {marker} $?\n"
        sock.sendall(full_command.encode("utf-8"))

        # Wait for marker in output
        deadline = time.monotonic() + timeout
        output_parts: list[str] = []
        exit_code: int | None = None

        while time.monotonic() < deadline:
            time.sleep(0.05)
            # Collect new output since start_len
            current_len = len(info.output_buffer)
            if current_len > start_len:
                new_items = list(info.output_buffer)[start_len:current_len]
                start_len = current_len
                output_parts.extend(new_items)

                # Check if marker appeared
                combined = "".join(output_parts)
                marker_idx = combined.find(marker)
                if marker_idx != -1:
                    # Extract output before marker and exit code after
                    before_marker = combined[:marker_idx]
                    after_marker = combined[marker_idx + len(marker) :].strip()
                    # Parse exit code
                    for token in after_marker.split():
                        try:
                            exit_code = int(token)
                            break
                        except ValueError:
                            continue

                    # Clean up: remove the echo command from output
                    # The output includes the typed command (PTY echo)
                    clean = _strip_command_echo(before_marker, command)
                    return BashResult(
                        output=clean.rstrip("\r\n") + "\n" if clean.strip() else "",
                        session=info.name,
                        exit_code=exit_code,
                    )

        # Timeout
        combined = "".join(output_parts)
        clean = _strip_command_echo(combined, command)
        return BashResult(
            output=clean.rstrip("\r\n") + "\n[timed out]\n" if clean.strip() else "[timed out]\n",
            session=info.name,
            exit_code=None,
        )

    # ── Raw session I/O (for interactive programs) ───────────────

    def _get_session(self, session: str) -> SessionInfo:
        """Look up a session by name or raise ValueError."""
        info = self._sessions.get(session)
        if info is None:
            raise ValueError(f"Session '{session}' not found")
        return info

    async def session_write(self, session: str, data: str) -> None:
        """Write raw data to a session's stdin."""
        info = self._get_session(session)
        if info.status == SessionStatus.EXITED:
            raise ValueError(f"Session '{session}' has exited")

        sock = _raw_socket(info.socket)
        await asyncio.to_thread(sock.sendall, data.encode("utf-8"))

    async def session_read(self, session: str) -> str:
        """Read recent output from a session (non-blocking poll)."""
        info = self._get_session(session)

        buf = info.output_buffer
        offset = info.poll_offset
        current_len = len(buf)
        if current_len <= offset:
            return ""
        new_items = list(buf)[offset:current_len]
        info.poll_offset = current_len
        return "".join(new_items)

    # ── Session management ───────────────────────────────────────

    def list_sessions(self) -> list[dict[str, Any]]:
        return [info.to_dict() for info in self._sessions.values()]

    async def session_log(self, session: str) -> str:
        """Full output history for a session."""
        info = self._get_session(session)
        return "".join(info.output_buffer)

    async def session_kill(self, session: str) -> None:
        """Kill a session (SIGTERM, then SIGKILL)."""
        info = self._get_session(session)

        if info.status == SessionStatus.RUNNING:
            sock = _raw_socket(info.socket)
            with contextlib.suppress(Exception):
                sock.close()
            info.status = SessionStatus.EXITED

    def session_clear(self, session: str) -> None:
        """Clear a session's output buffer."""
        info = self._get_session(session)
        info.output_buffer.clear()
        info.poll_offset = 0

    def _remove_session(self, session: str) -> None:
        """Remove a session from tracking."""
        self._stop_reader(session)
        self._sessions.pop(session, None)

    async def session_remove(self, session: str) -> None:
        """Remove a terminated session from tracking."""
        info = self._sessions.get(session)
        if info is not None and info.status == SessionStatus.RUNNING:
            await self.session_kill(session)
        self._remove_session(session)

    def _stop_reader(self, session: str) -> None:
        thread = self._reader_threads.pop(session, None)
        if thread is not None and thread.is_alive():
            # Close socket to unblock recv
            info = self._sessions.get(session)
            if info and info.socket:
                with contextlib.suppress(Exception):
                    _raw_socket(info.socket).close()
            thread.join(timeout=2)


def _strip_command_echo(output: str, command: str) -> str:
    """Remove the PTY echo of the typed command from the output.

    When a PTY is in echo mode, the command we sent appears in the output.
    Strip the first occurrence of each line of the command and the marker line.
    """
    lines = output.split("\n")
    cmd_lines = command.strip().split("\n")
    result: list[str] = []
    cmd_idx = 0
    for line in lines:
        if "__TANK_DONE_" in line:
            continue
        stripped = line.rstrip("\r")
        if cmd_idx < len(cmd_lines) and cmd_lines[cmd_idx] in stripped:
            cmd_idx += 1
            continue
        result.append(line)
    return "\n".join(result)
