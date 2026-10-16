"""Benchmark-only, one-action frames for an explicitly owned native window.

Synchronous methods run within the caller's joined native work/desktop lease.
The caller supplies its cancellation/deadline check; this is not a task runtime
or a production tool. No activation, retries or model calls occur here.
"""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import io
from uuid import uuid4

from agent_computer_use.channels import native
from PIL import Image
from tank_backend.tools.computer_observation import Observation


class OwnedInputGuard:
    def __init__(self, config: native.NativeConfig, *, check: Callable[[], None]) -> None:
        self.config = config
        self.check = check
        self.session_id = uuid4().hex
        self._frame: Observation | None = None
        self._window: native.NativeWindow | None = None
        self._scene = ""

    def _capture(self) -> tuple[native.NativeWindow, bytes, str]:
        self.check()
        window = native.read_window(self.config)
        png = native.macos._capture_screenshot_macos(
            include_cursor=False, display=window.display_geometry[0],
        )
        if native.read_window(self.config) != window:
            raise ValueError("Window changed during capture")
        with Image.open(io.BytesIO(png)) as image:
            if image.size != window.display_geometry[3:5]:
                raise ValueError("Screenshot dimensions changed")
            x, y, width, height = window.bounds
            scene = hashlib.sha256(
                image.convert("RGB").crop((x, y, x + width, y + height)).tobytes(),
            ).hexdigest()
        self.check()
        return window, png, scene

    def observe(self) -> tuple[Observation, bytes]:
        self._frame = None
        window, png, scene = self._capture()
        frame, png = Observation.capture(
            png, session_id=self.session_id, display_id=window.display_geometry[0],
            display_geometry=window.display_geometry,
        )
        self._frame = frame
        self._window, self._scene = window, scene
        return frame, png

    def _consume(self, frame_id: str) -> tuple[Observation, native.NativeWindow]:
        frame, self._frame = self._frame, None
        if frame is None or frame.frame_id != frame_id:
            raise ValueError("Missing or stale frame")
        window, _, scene = self._capture()
        if window != self._window or scene != self._scene:
            raise ValueError("Window or observed scene changed")
        return frame, window

    def _before_dispatch(self, window: native.NativeWindow) -> None:
        if not native.inputs_idle():
            raise ValueError("Inputs busy")
        if native.read_window(self.config) != window:
            raise ValueError("Window changed before dispatch")
        self.check()

    def click(self, frame_id: str, x: object, y: object) -> None:
        frame, window = self._consume(frame_id)
        px, py = frame.map_point(x, y)
        left, top, width, height = window.bounds
        if not (left <= px < left + width and top <= py < top + height):
            raise ValueError("Point is outside the owned window")
        if not native.pointer_target_is_exposed(window, px, py):
            raise ValueError("Target occluded")
        self._before_dispatch(window)
        native.macos._click_macos(px, py, clear_modifiers=True)

    def key_press(self, frame_id: str, key: str) -> None:
        _, window = self._consume(frame_id)
        if key != "enter":
            raise ValueError("This smoke guard permits only enter")
        self._before_dispatch(window)
        native.macos._key_macos(["return"])
