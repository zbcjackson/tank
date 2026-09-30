"""Guard SDK adapter primitives; no Tank DesktopExecutor is involved."""

from __future__ import annotations

import inspect
import asyncio
from pathlib import Path
import sys
from functools import wraps
from typing import Any, cast

from tank_backend.agents.subagent import SubAgentContext, SubAgentStopped
from tank_backend.agents.task_runtime import TaskOperation
from yutori.navigator.macos.computer import MacOSComputer
from yutori.navigator.macos.transport import (
    CuaDriverConnectionError,
    CuaDriverTransport,
    CuaDriverUncertainActionError,
)
from yutori.navigator.macos.types import CancellationLatch


class CheckedTransport(CuaDriverTransport):
    """Preserve session failures and expose unconfirmed cleanup."""

    def __init__(self, context: SubAgentContext | None = None) -> None:
        super().__init__()
        self.context = context
        self._owned_sessions: set[str] = set()
        self.cleanup_error: Exception | None = None
        self.stderr_tail = b""
        self.connection_error: CuaDriverConnectionError | None = None

    async def start(self) -> None:
        if self.context is not None:
            self.context.check("desktop")
        if not self.running:
            self.stderr_tail = b""
        try:
            await super().start()
        except CuaDriverConnectionError as exc:
            detail = self.stderr_tail.decode("utf-8", errors="replace").strip()
            raise CuaDriverConnectionError(
                f"{exc} Driver stderr: {detail or '(empty)'}. "
                "Check CuaDriver.app installation and run "
                "`uv run --no-sync cua-driver doctor` from backend/."
            ) from exc

    async def _drain_stderr(self) -> None:
        # The pinned SDK discards this stream. Keep a bounded tail while still
        # draining it so a verbose driver cannot block startup or grow memory.
        process = self._process
        if process is None or process.stderr is None:
            return
        while chunk := await process.stderr.read(4096):
            self.stderr_tail = (self.stderr_tail + chunk)[-8192:]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        read_only: bool = False,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        try:
            if self.connection_error is not None and (
                name != "end_session" or not self.running
            ):
                raise self.connection_error
            if not self.running:
                if name == "end_session" and self.context is not None:
                    raise CuaDriverConnectionError("cleanup cannot start a new driver session")
                await self.start()
            if self.context is not None:
                session = arguments.get("session")
                cleanup = name == "end_session" and session in self._owned_sessions
                if not cleanup:
                    self.context.check("desktop")
                if name == "start_session" and isinstance(session, str):
                    self._owned_sessions.add(session)
            try:
                # SDK reconnect closes the MCP lease, ending its task session.
                # A session-bound request cannot be replayed on a fresh lease.
                return await self._call_tool_once(
                    name, arguments, timeout_seconds=timeout_seconds
                )
            except CuaDriverConnectionError as exc:
                detail = self.stderr_tail.decode("utf-8", errors="replace").strip()
                self.connection_error = CuaDriverConnectionError(
                    f"cua-driver {name} failed: {exc} "
                    f"Driver stderr: {detail or '(empty)'}. Session was not reconnected."
                )
                if read_only:
                    raise self.connection_error from exc
                raise CuaDriverUncertainActionError(
                    f"cua-driver {name} acknowledgement lost; action was not retried. {exc}"
                ) from exc
        except Exception as exc:
            if name == "end_session":
                self.cleanup_error = exc
            raise

    async def close(self) -> None:
        await super().close()
        if self.cleanup_error is not None:
            raise RuntimeError(
                "cua-driver end_session cleanup unconfirmed"
            ) from self.cleanup_error


class _CheckedInput:
    def __init__(self, inner: Any, context: SubAgentContext) -> None:
        self.inner, self.context = inner, context

    def write(self, data: bytes) -> None:
        self.context.check("shell")
        self.inner.write(data)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


class _CheckedProcess:
    def __init__(self, inner: asyncio.subprocess.Process, context: SubAgentContext) -> None:
        self.inner = inner
        self.stdin = _CheckedInput(inner.stdin, context) if inner.stdin is not None else None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


def create_task_computer(context: SubAgentContext, **kwargs: Any) -> MacOSComputer:
    """Bind pinned SDK static/native hooks to one task without global monkey-patching."""

    class TaskComputer(MacOSComputer):
        @staticmethod
        def _read_text_file(path: Path) -> str:
            context.runtime.check_policy_now("file_read", {"path": str(path)})
            return MacOSComputer._read_text_file(path)

        @staticmethod
        def _write_text_file(path: Path, content: str) -> None:
            context.runtime.check_policy_now("file_write", {"path": str(path)})
            MacOSComputer._write_text_file(path, content)

        async def _spawn_supervised_shell(
            self, *args: Any, **options: Any,
        ) -> asyncio.subprocess.Process:
            context.check("shell")
            process = await super()._spawn_supervised_shell(*args, **options)
            # The SDK writes the business command after process startup/presentation.
            return cast(asyncio.subprocess.Process, _CheckedProcess(process, context))

        async def release_held_mouse_button(self) -> None:
            try:
                context.check("desktop")
            except (SubAgentStopped, asyncio.CancelledError, TimeoutError):
                # Mouse-down is emulated; completing it would be a NEW click/drag.
                self._left_mouse_down = False
                self._held_mouse_start = None
                return
            await super().release_held_mouse_button()

    return TaskComputer(**kwargs)


class GuardedComputer:
    """SDK method/signature compatibility over registered core operations."""

    _READS = {
        "screenshot", "get_dimensions", "get_environment", "wait", "wait_for_change",
        "poll_after_action", "list_windows", "resolve_window_target", "__aenter__",
    }
    _DESKTOP = {
        "click", "double_click", "triple_click", "move", "drag", "left_mouse_down",
        "left_mouse_up", "scroll", "type", "keypress", "key_down", "hold_key",
        "set_window_target", "unhide_app", "launch_app", "bring_to_front", "update_status_metrics",
    }
    _FILES = {"read_file": "file_read", "write_file": "file_write", "edit_file": "file_edit"}
    _SHELL = {"run_shell_command", "run_bash_command"}

    def __init__(self, computer: Any, context: SubAgentContext) -> None:
        self.computer = computer
        self.context = context
        self._operations: dict[str, TaskOperation[Any, Any]] = {}
        for name in self._READS | self._DESKTOP | set(self._FILES) | self._SHELL:
            value = getattr(computer, name, None)
            if not inspect.iscoroutinefunction(value):
                continue
            permission = "filesystem" if name in self._FILES else (
                "shell" if name in self._SHELL else "desktop"
            )
            operation = TaskOperation(
                "n2." + name, frozenset({permission}),
                "read" if name in self._READS or name == "read_file" else "action",
                lambda call, name=name: self._invoke(name, call),
                lambda call, name=name: self._preflight(name, call),
            )
            context.runtime.register(operation)
            self._operations[name] = operation

    async def _preflight(self, name: str, call: Any) -> None:
        args, kwargs = call
        method = getattr(self.computer, name)
        values = inspect.signature(method).bind(*args, **kwargs).arguments
        if name in self._FILES:
            path = values.get("file_path", values.get("path", ""))
            resolve = getattr(self.computer, "_resolve_file_path", Path)
            await self.context.runtime.authorize(self._FILES[name], {
                "path": str(resolve(path).resolve()),
            })
        elif name in self._SHELL:
            if values.get("run_in_background"):
                raise SubAgentStopped("background_shell_unsupported")
            await self.context.runtime.authorize("run_command", {
                "command": values.get("command", ""),
            })

    async def _invoke(self, name: str, call: Any) -> Any:
        args, kwargs = call
        result = await getattr(self.computer, name)(*args, **kwargs)
        if name == "get_dimensions":
            self.context.observe("dimensions", width=result[0], height=result[1])
        return result

    def __getattr__(self, name: str) -> Any:
        value = getattr(self.computer, name)
        if not inspect.iscoroutinefunction(value):
            return value
        if name in {"key_up", "release_held_mouse_button"}:
            return value

        @wraps(value)
        async def guarded(*args: Any, **kwargs: Any) -> Any:
            self.context.check()
            operation = self._operations.get(name)
            if operation is None:
                raise SubAgentStopped("operation_unregistered")
            return await self.context.runtime.execute(operation, (args, kwargs))

        return guarded

    async def __aenter__(self) -> GuardedComputer:
        self.context.check("desktop")
        if "__aenter__" in self._operations:
            await self.context.runtime.execute(self._operations["__aenter__"], ((), {}))
        return self

    async def aclose(self) -> None:
        await self.computer.aclose()


def create_computer(context: SubAgentContext) -> GuardedComputer:
    # Platform refusal precedes client creation, model requests and driver startup.
    if sys.platform != "darwin":
        raise RuntimeError(
            "N2 SDK supports macOS only; Linux X11 is unvalidated and Wayland unsupported"
        )
    for permission in ("desktop", "shell", "filesystem", "network"):
        context.check(permission)
    computer = create_task_computer(
        context,
        transport=CheckedTransport(context),
        owns_transport=True,
        cancellation=CancellationLatch(),
        execution_deadline=context.deadline,
        allow_local_shell=True,
        scope="desktop",
        presentation=False,
    )
    return GuardedComputer(computer, context)
