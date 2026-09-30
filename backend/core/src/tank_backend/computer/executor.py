"""DesktopExecutor — the capability interface injected into plugin agents.

Part B design ("brain in the plugin, hands in the executor"): a plugin
agent (e.g. agent-n2) implements the Agent ABC and receives a
DesktopExecutor; every host action it takes goes through this interface,
so the security red lines are enforced uniformly for all engines:

- bash: persistent cwd per executor, ``sudo``/``su`` rejected, output
  truncated to 10k chars per stream;
- files: ``edit_file`` only replaces a uniquely-matching ``old`` string
  (read-before-edit is mechanically enforced);
- coordinates/keys: normalized through ``computer_use_common`` exactly
  like the built-in tools (0-1000 scale, bbox centers, key synonyms).

The desktop primitives reuse the platform backends the Part A tools
built (``_click_ydotool`` / ``_click_macos`` / portal screenshot /
A13 crop) — the executor returns small typed results, not ToolResult,
because its consumer is agent code, not an LLM tool loop.

Cancellation contract for engine authors: ``run`` is an async
generator; the supervisor stops it by cancelling the task — clean up
in ``finally`` on ``CancelledError``.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import re
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

from ..tools import computer_use, computer_use_macos
from ..tools.computer_native import join_on_cancel, run_native
from ..tools.computer_use_common import (
    BATCH_ACTIONS,
    PYAUTOGUI_KEY_ALIASES,
    YDOTOOL_KEY_ALIASES,
    crop_and_upscale,
    normalize_keys,
    normalize_point,
    normalized_to_pixel,
    parse_region,
)

if TYPE_CHECKING:
    from ..agents.subagent import SubAgentContext

_WAIT_MIN_S = 0.1
_WAIT_MAX_S = 5.0
_OUTPUT_TRUNC = 10_000
_DEFAULT_SIZE = (1920, 1080)

# sudo/su as the first token of the command or of any pipeline/list
# segment (operators: |, ;, &, &&, ||).
_SUDO_RE = re.compile(r"(?:^|[|;&]+\s*)(?:sudo|su)(?:\s|$)")


@dataclass(frozen=True, slots=True)
class Screenshot:
    """A captured screen image.

    ``width``/``height`` are always the FULL screen size in pixels
    (point space on macOS), even when ``region`` cropped the image —
    normalized coordinates convert against the full screen.
    """

    png: bytes
    width: int
    height: int
    region: tuple[int, int, int, int] | None = None


@dataclass(frozen=True, slots=True)
class BashResult:
    exit_code: int
    stdout: str
    stderr: str
    cwd: str  # working directory AFTER the command ran
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class BatchStep:
    action: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class BatchResult:
    steps: tuple[BatchStep, ...]
    failed_at: int | None
    skipped: tuple[str, ...]
    screenshot: Screenshot | None


@runtime_checkable
class DesktopExecutor(Protocol):
    """Host capabilities available to a desktop-control agent."""

    # ── desktop primitives (0-1000 normalized coordinates) ──────────

    async def screenshot(self, region: Any = None) -> Screenshot:
        """Capture the screen; optionally crop+upscale a 0-1000 region."""
        ...

    async def click(
        self, x: Any, y: Any = None, button: str = "left", clicks: int = 1,
    ) -> None: ...

    async def type_text(self, text: str) -> None: ...

    async def key_press(self, keys: str, repeat: int = 1) -> None: ...

    async def key_down(self, key: str) -> None: ...

    async def key_up(self, key: str) -> None: ...

    async def scroll(
        self, amount: int, x: Any = None, y: Any = None,
    ) -> None: ...

    async def mouse_move(self, x: Any, y: Any = None) -> None: ...

    async def mouse_down(self, button: str = "left") -> None: ...

    async def mouse_up(self, button: str = "left") -> None: ...

    async def hold_key(self, keys: str, duration_s: float = 1.0) -> None: ...

    async def drag(
        self, x1: Any, y1: Any = None, x2: Any = None, y2: Any = None,
    ) -> None: ...

    async def wait(self, delay_s: float) -> None: ...

    async def batch(
        self, actions: list[dict[str, Any]], screenshot_after: bool = True,
    ) -> BatchResult:
        """Run a sequence of actions (A10 semantics: fail-fast, skipped
        list, one screenshot of the final state)."""
        ...

    # ── bash (persistent cwd, no sudo, output truncated) ────────────

    async def bash(self, command: str, timeout_s: int = 120) -> BashResult: ...

    # ── files (edit is read-before-edit by construction) ────────────

    async def read_file(self, path: str) -> str: ...

    async def write_file(self, path: str, content: str) -> None: ...

    async def edit_file(self, path: str, old: str, new: str) -> None: ...


class _BaseExecutor:
    """Platform-independent behavior: size cache, coordinate math, wait,
    bash, files, batch. Subclasses provide the desktop primitives."""

    def __init__(
        self, cwd: Path | str | None = None, *, context: SubAgentContext | None = None,
    ) -> None:
        self._cwd = Path(cwd).resolve() if cwd is not None else Path.cwd().resolve()
        self._size: tuple[int, int] | None = None
        self._context = context
        self._held_keys: set[str] = set()
        self._held_buttons: set[str] = set()
        self._process: asyncio.subprocess.Process | None = None

    async def _native(
        self, permission: str | None, function: Any, *args: Any, **kwargs: Any,
    ) -> Any:
        context = self._context
        if context is None:
            return await asyncio.to_thread(function, *args, **kwargs)

        def invoke() -> Any:
            if permission is not None:
                context.check(permission)
                target = getattr(function, "__self__", None)
                if permission == "filesystem" and isinstance(target, Path):
                    operation = "file_write" if function.__name__ == "write_text" else "file_read"
                    context.runtime.check_policy_now(operation, {"path": str(target)})
            return function(*args, **kwargs)

        return await run_native(invoke)

    async def _input_state(
        self, name: str, down: bool, held: set[str], action: Any,
    ) -> None:
        if self._context is not None and not down and name not in held:
            return

        def emit() -> None:
            if down:
                held.add(name)
            action()
            if not down:
                held.discard(name)

        await self._native("desktop" if down else None, emit)

    async def _stop_process(self) -> None:
        process = self._process
        if process is None or process.returncode is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
            async with asyncio.timeout(1):
                await process.wait()
        except TimeoutError:
            os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
        except ProcessLookupError:
            await process.wait()

    async def aclose(self) -> None:
        failures = []
        try:
            await self._stop_process()
        except (Exception, asyncio.CancelledError):
            failures.append("process")
        for key in tuple(self._held_keys):
            try:
                await cast(DesktopExecutor, self).key_up(key)
            except Exception:
                failures.append(key)
        for button in tuple(self._held_buttons):
            try:
                await cast(DesktopExecutor, self).mouse_up(button)
            except Exception:
                failures.append(button)
        if failures:
            raise RuntimeError("task input release unconfirmed")

    # -- shared helpers ------------------------------------------------

    def _point(self, x: Any, y: Any) -> tuple[int, int]:
        point = normalize_point(x, y)
        if point is None:
            raise ValueError(
                "coordinates must be 0-1000 normalized ints (or a bbox "
                "[x1,y1,x2,y2] whose center is used)"
            )
        return point

    def _pixel(self, nx: int, ny: int) -> tuple[int, int]:
        return normalized_to_pixel(nx, ny, self._size or _DEFAULT_SIZE)

    def _capture(self) -> bytes:
        raise NotImplementedError

    async def screenshot(self, region: Any = None) -> Screenshot:
        png = await self._native("desktop", self._capture)
        width, height = computer_use._png_size(png)
        if width and height:
            self._size = (width, height)

        if region is None:
            return Screenshot(png, width, height)

        parsed = parse_region(region)
        if parsed is None:
            raise ValueError(
                "region must be [x1, y1, x2, y2] in 0-1000 normalized "
                "coordinates with x2 > x1, y2 > y1"
            )
        cropped = await self._native("desktop",
            crop_and_upscale, png, parsed, (width, height),
        )
        return Screenshot(cropped, width, height, parsed)

    async def wait(self, delay_s: float) -> None:
        try:
            delay = float(delay_s)
        except (TypeError, ValueError):
            delay = 1.0
        await asyncio.sleep(max(_WAIT_MIN_S, min(_WAIT_MAX_S, delay)))

    # -- bash ------------------------------------------------------------

    async def bash(self, command: str, timeout_s: int = 120) -> BashResult:
        if _SUDO_RE.search(command):
            raise PermissionError("sudo/su is not allowed in DesktopExecutor.bash")

        # One process: run the command from the tracked cwd, then report
        # the shell's final $PWD back via a marker line (stripped before
        # returning) while preserving the command's exit code.
        marker = "__TANK_PWD__"
        wrapped = (
            f'cd "{self._cwd}" && {{ {command}\n}}; __rc=$?; '
            f'printf \'\\n{marker}%s\\n\' "$PWD"; exit $__rc'
        )
        if self._context is None:
            proc = await asyncio.to_thread(
                subprocess.run, ["bash", "-c", wrapped],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=timeout_s,
            )
        else:
            self._context.check("shell")
            self._process = await asyncio.create_subprocess_exec(
                "bash", "-c", wrapped, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, start_new_session=True,
            )
            try:
                self._context.check("shell")
                async with asyncio.timeout(timeout_s):
                    out, err = await self._process.communicate()
                proc = subprocess.CompletedProcess(
                    ["bash"], self._process.returncode or 0,
                    out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace"),
                )
            finally:
                await join_on_cancel(self._stop_process())
                self._process = None

        stdout = proc.stdout or ""
        cwd = self._cwd
        if marker in stdout:
            head, _, tail = stdout.rpartition(marker)
            stdout = head.rstrip("\n")
            new_cwd = tail.strip()
            if new_cwd:
                cwd = Path(new_cwd).resolve()
                self._cwd = cwd

        truncated = False
        if len(stdout) > _OUTPUT_TRUNC:
            omitted = len(stdout) - _OUTPUT_TRUNC
            stdout = stdout[:_OUTPUT_TRUNC] + f"\n[truncated: {omitted} chars omitted]"
            truncated = True
        stderr = proc.stderr or ""
        if len(stderr) > _OUTPUT_TRUNC:
            omitted = len(stderr) - _OUTPUT_TRUNC
            stderr = stderr[:_OUTPUT_TRUNC] + f"\n[truncated: {omitted} chars omitted]"
            truncated = True

        return BashResult(
            exit_code=proc.returncode, stdout=stdout, stderr=stderr,
            cwd=str(cwd), truncated=truncated,
        )

    # -- files -----------------------------------------------------------

    def _resolve(self, path: str) -> Path:
        p = Path(path)
        return p if p.is_absolute() else self._cwd / p

    async def read_file(self, path: str) -> str:
        return await self._native("filesystem", self._resolve(path).read_text, "utf-8")

    async def write_file(self, path: str, content: str) -> None:
        await self._native("filesystem", self._resolve(path).write_text, content, "utf-8")

    async def edit_file(self, path: str, old: str, new: str) -> None:
        target = self._resolve(path)
        content = await self._native("filesystem", target.read_text, "utf-8")
        matches = content.count(old)
        if matches != 1:
            raise ValueError(
                f"edit_file: 'old' matches {matches} times in {target} "
                f"(must be exactly 1) — read the file first"
            )
        await self._native("filesystem",
            target.write_text, content.replace(old, new, 1), "utf-8",
        )

    # -- batch (A10 semantics) -------------------------------------------

    async def batch(
        self, actions: list[dict[str, Any]], screenshot_after: bool = True,
    ) -> BatchResult:
        if not isinstance(actions, list) or not actions:
            raise ValueError("batch: 'actions' must be a non-empty list")

        steps: list[BatchStep] = []
        failed_at: int | None = None
        skipped: list[str] = []
        for index, raw in enumerate(actions):
            if not isinstance(raw, dict):
                raise ValueError(f"batch: action #{index} is not an object")
            name = raw.get("action")
            if name not in BATCH_ACTIONS:
                raise ValueError(
                    f"batch: unknown action {name!r}; "
                    f"valid: {sorted(BATCH_ACTIONS)}"
                )
            if name == "wait":
                await self.wait(raw.get("delay_s", 1.0))
                steps.append(BatchStep("wait", True))
                continue
            kwargs = {k: v for k, v in raw.items() if k != "action"}
            try:
                await getattr(self, name)(**kwargs)
                steps.append(BatchStep(name, True))
            except Exception as e:  # noqa: BLE001 — reported to the caller
                steps.append(BatchStep(name, False, str(e)))
                failed_at = index
                skipped = [a.get("action", "?") for a in actions[index + 1:]]
                break

        shot: Screenshot | None = None
        if screenshot_after:
            shot = await self.screenshot()

        return BatchResult(
            steps=tuple(steps),
            failed_at=failed_at,
            skipped=tuple(skipped),
            screenshot=shot,
        )


class _LinuxExecutor(_BaseExecutor):
    """Wayland/X11 backend: ydotool primary, pyautogui fallback."""

    def _capture(self) -> bytes:
        return computer_use._capture_screenshot()

    async def click(
        self, x: Any, y: Any = None, button: str = "left", clicks: int = 1,
    ) -> None:
        nx, ny = self._point(x, y)
        px, py = self._pixel(nx, ny)
        if computer_use._ydotool_available():
            await self._native("desktop",
                computer_use._click_ydotool, px, py, button, clicks,
            )
        else:
            await self._native("desktop",
                computer_use._run_pyautogui, "click", px, py,
                button=button, clicks=clicks,
            )

    async def type_text(self, text: str) -> None:
        if any(ord(c) >= 128 for c in text):
            await self._native("desktop", computer_use._paste_linux, text)
        elif computer_use._ydotool_available():
            for i in range(0, len(text), 50):
                await self._native("desktop", computer_use._type_ydotool, text[i : i + 50])
                if i + 50 < len(text):
                    await asyncio.sleep(0.1)
        else:
            await self._native("desktop",
                computer_use._run_pyautogui, "write", text, interval=0,
            )

    async def _key_state(self, key: str, down: bool) -> None:
        keys = normalize_keys(key)
        if not keys or len(keys) != 1:
            raise ValueError("key_down/up requires one valid key")
        if computer_use._ydotool_available():
            mapped = YDOTOOL_KEY_ALIASES.get(keys[0], keys[0])
            def emit() -> None:
                sock = computer_use._ydotool_client()
                try:
                    computer_use._ydotool_emit(
                        sock, computer_use._YD_EV_KEY,
                        computer_use._LINUX_KEYCODES[mapped], int(down),
                    )
                finally:
                    sock.close()
            await self._input_state(keys[0], down, self._held_keys, emit)
        else:
            mapped = PYAUTOGUI_KEY_ALIASES.get(keys[0], keys[0])
            await self._input_state(keys[0], down, self._held_keys, lambda: (
                computer_use._run_pyautogui("keyDown" if down else "keyUp", mapped)
            ))

    async def key_down(self, key: str) -> None:
        await self._key_state(key, True)

    async def key_up(self, key: str) -> None:
        await self._key_state(key, False)

    async def key_press(self, keys: str, repeat: int = 1) -> None:
        key_list = normalize_keys(keys)
        if not key_list:
            raise ValueError(f"key_press: invalid 'keys' {keys!r}")
        times = max(1, min(20, int(repeat)))
        ydotool = computer_use._ydotool_available()
        aliases = YDOTOOL_KEY_ALIASES if ydotool else PYAUTOGUI_KEY_ALIASES
        mapped = [aliases.get(k, k) for k in key_list]
        for _ in range(times):
            if ydotool:
                await self._native("desktop", computer_use._key_ydotool, mapped)
            else:
                await self._native("desktop",
                    computer_use._run_pyautogui, "hotkey", *mapped,
                )

    async def scroll(self, amount: int, x: Any = None, y: Any = None) -> None:
        amount = int(amount)
        if abs(amount) > 50:
            raise ValueError("scroll: amount must be between -50 and 50")
        px: int | None = None
        py: int | None = None
        if x is not None or y is not None:
            nx, ny = self._point(x, y)
            px, py = self._pixel(nx, ny)
        if computer_use._ydotool_available():
            await self._native("desktop", computer_use._scroll_ydotool, amount, px, py)
        else:
            kwargs: dict[str, Any] = {}
            if px is not None:
                kwargs["x"] = px
            if py is not None:
                kwargs["y"] = py
            await self._native("desktop",
                computer_use._run_pyautogui, "scroll", amount, **kwargs,
            )

    async def mouse_move(self, x: Any, y: Any = None) -> None:
        nx, ny = self._point(x, y)
        px, py = self._pixel(nx, ny)
        if computer_use._ydotool_available():
            await self._native("desktop", computer_use._move_ydotool, px, py)
        else:
            await self._native("desktop", computer_use._run_pyautogui, "moveTo", px, py)

    async def mouse_down(self, button: str = "left") -> None:
        await self._mouse_button(button, down=True)

    async def mouse_up(self, button: str = "left") -> None:
        await self._mouse_button(button, down=False)

    async def _mouse_button(self, button: str, down: bool) -> None:
        def action() -> None:
            if computer_use._ydotool_available():
                computer_use._mouse_button_ydotool(button, down)
            else:
                computer_use._run_pyautogui("mouseDown" if down else "mouseUp", button=button)
        await self._input_state(button, down, self._held_buttons, action)

    async def hold_key(self, keys: str, duration_s: float = 1.0) -> None:
        key_list = normalize_keys(keys)
        if not key_list:
            raise ValueError(f"hold_key: invalid 'keys' {keys!r}")
        duration = max(0.1, min(10.0, float(duration_s)))
        if self._context is not None:
            try:
                for key in key_list:
                    await self.key_down(key)
                await asyncio.sleep(duration)
            finally:
                for key in reversed(key_list):
                    await join_on_cancel(self.key_up(key))
            return
        if computer_use._ydotool_available():
            await self._native("desktop",
                computer_use._hold_key_ydotool, key_list, duration,
            )
        else:
            mapped = [PYAUTOGUI_KEY_ALIASES.get(k, k) for k in key_list]
            await self._native("desktop",
                computer_use._run_pyautogui, "keyDown", *mapped,
            )
            await asyncio.sleep(duration)
            await self._native("desktop",
                computer_use._run_pyautogui, "keyUp", *mapped,
            )

    async def drag(
        self, x1: Any, y1: Any = None, x2: Any = None, y2: Any = None,
    ) -> None:
        start = self._point(x1, y1)
        end = self._point(x2, y2)
        sx, sy = self._pixel(*start)
        ex, ey = self._pixel(*end)
        if computer_use._ydotool_available():
            await self._native("desktop", computer_use._drag_ydotool, sx, sy, ex, ey)
        else:
            await self._native("desktop",
                computer_use._run_pyautogui, "drag", sx, sy, ex, ey,
                duration=0.4, button="left",
            )


class _MacOSExecutor(_BaseExecutor):
    """macOS backend: screencapture + CGEvent/AppleScript."""

    def _point(self, x: Any, y: Any) -> tuple[int, int]:
        point = normalize_point(x, y, strict=True)
        if point is None:
            raise ValueError("coordinates must be finite numbers in the 0-1000 range")
        return point

    def _capture(self) -> bytes:
        return computer_use_macos._capture_screenshot_macos()

    async def click(
        self, x: Any, y: Any = None, button: str = "left", clicks: int = 1,
    ) -> None:
        nx, ny = self._point(x, y)
        px, py = self._pixel(nx, ny)
        await self._native("desktop",
            computer_use_macos._click_macos, px, py, button, clicks,
        )

    async def type_text(self, text: str) -> None:
        await self._native("desktop", computer_use_macos._type_macos, text)

    async def _key_state(self, key: str, down: bool) -> None:
        keys = normalize_keys(key)
        if not keys or len(keys) != 1:
            raise ValueError("key_down/up requires one valid key")
        if self._context is not None and not down and keys[0] not in self._held_keys:
            return
        def emit() -> None:
            quartz = computer_use_macos._load_quartz()
            modifier_codes = {"cmd": 55, "ctrl": 59, "alt": 58, "shift": 56}
            code = modifier_codes.get(keys[0], computer_use_macos._KEYCODE_MAP.get(keys[0]))
            if code is None:
                raise ValueError(f"unsupported key: {key}")
            event = quartz.CGEventCreateKeyboardEvent(None, code, down)
            if down:
                self._held_keys.add(keys[0])
            quartz.CGEventPost(quartz.kCGHIDEventTap, event)
            if not down:
                self._held_keys.discard(keys[0])
        await self._native("desktop" if down else None, emit)

    async def key_down(self, key: str) -> None:
        await self._key_state(key, True)

    async def key_up(self, key: str) -> None:
        await self._key_state(key, False)

    async def key_press(self, keys: str, repeat: int = 1) -> None:
        key_list = normalize_keys(keys)
        if not key_list:
            raise ValueError(f"key_press: invalid 'keys' {keys!r}")
        times = max(1, min(20, int(repeat)))
        for _ in range(times):
            await self._native("desktop", computer_use_macos._key_macos, key_list)

    async def scroll(self, amount: int, x: Any = None, y: Any = None) -> None:
        amount = int(amount)
        if abs(amount) > 50:
            raise ValueError("scroll: amount must be between -50 and 50")
        px: int | None = None
        py: int | None = None
        if x is not None or y is not None:
            nx, ny = self._point(x, y)
            px, py = self._pixel(nx, ny)
        await self._native("desktop", computer_use_macos._scroll_macos, amount, px, py)

    async def mouse_move(self, x: Any, y: Any = None) -> None:
        nx, ny = self._point(x, y)
        px, py = self._pixel(nx, ny)
        await self._native("desktop", computer_use_macos._move_macos, px, py)

    async def mouse_down(self, button: str = "left") -> None:
        def emit() -> None:
            self._held_buttons.add(button)
            computer_use_macos._mouse_button_macos(button, True)
        await self._native("desktop", emit)

    async def mouse_up(self, button: str = "left") -> None:
        if self._context is not None and button not in self._held_buttons:
            return
        await self._native(None, computer_use_macos._mouse_button_macos, button, False)
        self._held_buttons.discard(button)

    async def hold_key(self, keys: str, duration_s: float = 1.0) -> None:
        key_list = normalize_keys(keys)
        if not key_list:
            raise ValueError(f"hold_key: invalid 'keys' {keys!r}")
        duration = max(0.1, min(10.0, float(duration_s)))
        if self._context is not None:
            try:
                for key in key_list:
                    await self.key_down(key)
                await asyncio.sleep(duration)
            finally:
                for key in reversed(key_list):
                    await join_on_cancel(self.key_up(key))
            return
        await self._native("desktop",
            computer_use_macos._hold_key_macos, key_list, duration,
        )

    async def drag(
        self, x1: Any, y1: Any = None, x2: Any = None, y2: Any = None,
    ) -> None:
        start = self._point(x1, y1)
        end = self._point(x2, y2)
        sx, sy = self._pixel(*start)
        ex, ey = self._pixel(*end)
        await self._native("desktop", computer_use_macos._drag_macos, sx, sy, ex, ey)


class _TaskDesktopExecutor:
    """Compatibility view: the public executor protocol, governed by one task runtime."""

    def __init__(self, inner: _BaseExecutor, context: SubAgentContext) -> None:
        from ..agents.task_runtime import TaskOperation

        self._inner, self._context = inner, context
        self._operations = {}
        for name in (
            "screenshot", "click", "type_text", "key_press", "key_down", "scroll", "mouse_move",
            "mouse_down", "hold_key", "drag", "wait", "batch", "bash", "read_file",
            "write_file", "edit_file",
        ):
            permission = "shell" if name == "bash" else (
                "filesystem" if name.endswith("_file") else "desktop"
            )
            operation = TaskOperation(
                "desktop." + name, frozenset({permission}),
                "read" if name in {"screenshot", "read_file", "wait"} else "action",
                lambda call, name=name: self._invoke(name, call),
                lambda call, name=name: self._preflight(name, call),
            )
            context.runtime.register(operation)
            self._operations[name] = operation
        context.runtime.own("desktop-executor", inner.aclose)

    async def _preflight(self, name: str, call: Any) -> None:
        args, kwargs = call
        values = inspect.signature(getattr(self._inner, name)).bind(*args, **kwargs).arguments
        if name == "bash":
            await self._context.runtime.authorize("run_command", {"command": values["command"]})
        elif name.endswith("_file"):
            await self._context.runtime.authorize(
                {"read_file": "file_read", "write_file": "file_write",
                 "edit_file": "file_edit"}[name],
                {"path": str(self._inner._resolve(values["path"]).resolve())},
            )

    async def _invoke(self, name: str, call: Any) -> Any:
        args, kwargs = call
        result = await getattr(self._inner, name)(*args, **kwargs)
        if isinstance(result, BatchResult) and result.failed_at is not None:
            raise RuntimeError("native batch effect could not be confirmed")
        return result

    def __getattr__(self, name: str) -> Any:
        if name in {"key_up", "mouse_up"}:
            return getattr(self._inner, name)
        if name not in self._operations:
            raise AttributeError(name)

        async def invoke(*args: Any, **kwargs: Any) -> Any:
            return await self._context.runtime.execute(self._operations[name], (args, kwargs))
        return invoke


def create_desktop_executor(
    cwd: Path | str | None = None, *, context: SubAgentContext | None = None,
) -> DesktopExecutor:
    """Create the platform executor, optionally bound to the host's original task."""
    import sys

    inner = _MacOSExecutor(cwd, context=context) if sys.platform == "darwin" else _LinuxExecutor(
        cwd, context=context,
    )
    if context is not None:
        return cast(DesktopExecutor, _TaskDesktopExecutor(inner, context))
    return inner
