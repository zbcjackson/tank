"""Guard SDK adapter primitives; no Tank DesktopExecutor is involved."""

from __future__ import annotations

import inspect
import sys
from typing import Any

from tank_backend.agents.subagent import SubAgentContext
from yutori.navigator.macos.computer import MacOSComputer
from yutori.navigator.macos.transport import (
    CuaDriverConnectionError,
    CuaDriverTransport,
    CuaDriverUncertainActionError,
)
from yutori.navigator.macos.types import CancellationLatch


class CheckedTransport(CuaDriverTransport):
    """Preserve session failures and expose unconfirmed cleanup."""

    def __init__(self) -> None:
        super().__init__()
        self.cleanup_error: Exception | None = None
        self.stderr_tail = b""
        self.connection_error: CuaDriverConnectionError | None = None

    async def start(self) -> None:
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
                await self.start()
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


class GuardedComputer:
    """Keep SDK public methods/capabilities intact while checking each call."""

    def __init__(self, computer: Any, context: SubAgentContext) -> None:
        self.computer = computer
        self.context = context

    def __getattr__(self, name: str) -> Any:
        value = getattr(self.computer, name)
        if not inspect.iscoroutinefunction(value):
            return value
        # Releasing input is allowed even after authorization/cancel/budget.
        if name in {"key_up", "release_held_mouse_button"}:
            return value
        permission = (
            "shell"
            if name in {"run_bash_command", "run_shell_command"}
            else "filesystem"
            if name
            in {"read_file", "write_file", "edit_file", "grep_files", "glob_files"}
            else "desktop"
        )

        async def guarded(*args: Any, **kwargs: Any) -> Any:
            self.context.check(permission)
            result = await value(*args, **kwargs)
            if name == "get_dimensions":
                self.context.observe("dimensions", width=result[0], height=result[1])
            self.context.check(permission)
            return result

        return guarded

    async def __aenter__(self) -> GuardedComputer:
        self.context.check("desktop")
        enter = getattr(self.computer, "__aenter__", None)
        if enter is not None:
            await enter()
        self.context.check("desktop")
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
    computer = MacOSComputer(
        transport=CheckedTransport(),
        owns_transport=True,
        cancellation=CancellationLatch(),
        execution_deadline=context.deadline,
        allow_local_shell=True,
        scope="desktop",
        presentation=False,
    )
    return GuardedComputer(computer, context)
