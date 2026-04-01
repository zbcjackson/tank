"""Shared background process management for stateless sandbox backends.

Both Seatbelt and Bubblewrap use subprocess.Popen for background processes.
This module provides the shared tracking logic so each backend only needs
to supply the command list.
"""

from __future__ import annotations

import contextlib
import logging
import subprocess
import threading
import uuid
from typing import Any

from ..types import ProcessInfo, ProcessOutput, ProcessStatus

logger = logging.getLogger(__name__)


class ProcessTracker:
    """Tracks background Popen processes with output buffering.

    Each backend creates one ProcessTracker instance and delegates
    list/poll/kill/log calls to it.
    """

    def __init__(self) -> None:
        self._processes: dict[str, ProcessInfo] = {}
        self._reader_threads: dict[str, threading.Thread] = {}

    def start(self, cmd: list[str], command_str: str, cwd: str) -> str:
        """Launch *cmd* in the background and return a process ID."""
        process_id = uuid.uuid4().hex[:12]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=cwd,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(str(exc)) from exc

        info = ProcessInfo(
            process_id=process_id,
            command=command_str,
            handle=proc,
        )
        self._processes[process_id] = info

        thread = threading.Thread(
            target=self._reader_loop,
            args=(process_id,),
            daemon=True,
            name=f"bg-reader-{process_id}",
        )
        self._reader_threads[process_id] = thread
        thread.start()

        logger.info("Background process started: %s (pid=%d)", process_id, proc.pid)
        return process_id

    def list_all(self) -> list[dict[str, Any]]:
        """Return summary dicts for all tracked processes."""
        self._reap_finished()
        return [info.to_dict() for info in self._processes.values()]

    def poll(self, process_id: str) -> ProcessOutput:
        """Read new output since last poll."""
        info = self._get(process_id)
        self._reap_one(info)

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

    def log(self, process_id: str) -> str:
        """Full output history."""
        info = self._get(process_id)
        return "".join(info.output_buffer)

    def kill(self, process_id: str) -> None:
        """Terminate a background process."""
        info = self._get(process_id)
        proc: subprocess.Popen = info.handle
        if info.status == ProcessStatus.RUNNING:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            info.status = ProcessStatus.EXITED
            info.exit_code = proc.returncode
            logger.info("Background process killed: %s", process_id)

    def cleanup(self) -> None:
        """Kill all tracked processes."""
        for pid in list(self._processes):
            with contextlib.suppress(Exception):
                self.kill(pid)
        self._processes.clear()
        self._reader_threads.clear()

    # ── Internals ─────────────────────────────────────────────────

    def _get(self, process_id: str) -> ProcessInfo:
        info = self._processes.get(process_id)
        if info is None:
            raise ValueError(f"Process '{process_id}' not found")
        return info

    def _reap_one(self, info: ProcessInfo) -> None:
        """Update status if the underlying process has exited."""
        if info.status != ProcessStatus.RUNNING:
            return
        proc: subprocess.Popen = info.handle
        rc = proc.poll()
        if rc is not None:
            info.status = ProcessStatus.EXITED
            info.exit_code = rc

    def _reap_finished(self) -> None:
        for info in self._processes.values():
            self._reap_one(info)

    def _reader_loop(self, process_id: str) -> None:
        """Background thread: read stdout into the output buffer."""
        info = self._processes.get(process_id)
        if info is None or info.handle is None:
            return

        proc: subprocess.Popen = info.handle
        try:
            assert proc.stdout is not None
            while True:
                data = proc.stdout.read(4096)
                if not data:
                    break
                text = data.decode("utf-8", errors="replace")
                info.output_buffer.append(text)
        except Exception as exc:
            logger.debug("Reader for %s ended: %s", process_id, exc)
        finally:
            self._reap_one(info)
