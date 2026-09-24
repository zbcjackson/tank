"""Opt-in input release for exclusive, controlled macOS benchmark runs."""
from __future__ import annotations

import asyncio
from typing import Any

from ..tools import computer_use_macos as macos
from ..tools.computer_native import run_native


class MacOSInputCleanup:
    """Release inputs after joined actions; keep app output available to validators.

    The operator must leave the desktop idle. This does not close applications,
    restore clipboard/window state, or establish cross-process desktop ownership.
    """

    @staticmethod
    def _state() -> tuple[list[int], list[int]]:
        quartz = macos._load_quartz()
        state = quartz.kCGEventSourceStateCombinedSessionState
        return (
            [k for k in range(128) if quartz.CGEventSourceKeyState(state, k)],
            [b for b in range(32) if quartz.CGEventSourceButtonState(state, b)],
        )

    async def begin(self) -> None:
        keys, buttons = await run_native(self._state)
        if keys or buttons:
            raise RuntimeError("Desktop inputs already held; trial not started")

    def _release(self) -> dict[str, Any]:
        quartz = macos._load_quartz()
        keys, buttons = self._state()
        errors: list[str] = []
        for key in keys:
            try:
                event = quartz.CGEventCreateKeyboardEvent(None, key, False)
                quartz.CGEventSetFlags(event, 0)
                quartz.CGEventPost(quartz.kCGHIDEventTap, event)
            except Exception as exc:
                errors.append(type(exc).__name__)
        for button in buttons:
            try:
                kind = (quartz.kCGEventLeftMouseUp if button == 0 else
                        quartz.kCGEventRightMouseUp if button == 1 else quartz.kCGEventOtherMouseUp)
                point = quartz.CGEventGetLocation(quartz.CGEventCreate(None))
                event = quartz.CGEventCreateMouseEvent(None, kind, point, button)
                quartz.CGEventSetFlags(event, 0)
                quartz.CGEventPost(quartz.kCGHIDEventTap, event)
            except Exception as exc:
                errors.append(type(exc).__name__)
        return {"keys_before": keys, "buttons_before": buttons, "errors": errors}

    async def finish(self) -> dict[str, Any]:
        result = await run_native(self._release)
        await asyncio.sleep(0.1)  # CGEventPost is asynchronous; verify delivered releases.
        keys, buttons = await run_native(self._state)
        result.update(keys_after=keys, buttons_after=buttons,
                      confirmed=not keys and not buttons and not result["errors"])
        return result
