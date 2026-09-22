"""Opt-in, frame-bound macOS image coordinates alongside the legacy tools."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from PIL import Image

from ..core.content import ImageBlock, TextBlock
from . import computer_use_macos as macos
from .base import BaseTool, ToolContext, ToolInfo, ToolMetadata, ToolParameter, ToolResult
from .computer_observation import Observation
from .computer_use_common import parse_region


@dataclass
class FrameState:
    """One current observation per tool group; owner is checked on every action."""

    observation: Observation | None = None
    png: bytes = b""
    lock: threading.Lock = field(default_factory=threading.Lock)


def _geometry() -> tuple[int, ...]:
    quartz = macos._load_quartz()
    display = quartz.CGMainDisplayID()
    bounds = quartz.CGDisplayBounds(display)
    mode = quartz.CGDisplayCopyDisplayMode(display)
    values = (
        display,
        *bounds[0],
        *bounds[1],
        quartz.CGDisplayModeGetPixelWidth(mode),
        quartz.CGDisplayModeGetPixelHeight(mode),
    )
    geometry = tuple(int(v) for v in values)
    if geometry[0] <= 0 or geometry[1:3] != (0, 0) or min(geometry[3:]) <= 0:
        raise ValueError("Only a valid main display at origin (0,0) is supported")
    return geometry


def _window_bounds(
    window_id: int | None, geometry: tuple[int, ...]
) -> tuple[int, int, int, int] | None:
    if window_id is None:
        return None
    if type(window_id) is not int or window_id <= 0:
        raise ValueError("Invalid window_id")
    quartz = macos._load_quartz()
    windows = quartz.CGWindowListCopyWindowInfo(quartz.kCGWindowListOptionOnScreenOnly, 0)
    for window in windows or []:
        if window.get("kCGWindowNumber") == window_id:
            rect = window["kCGWindowBounds"]
            x, y, w, h = (int(rect[k]) for k in ("X", "Y", "Width", "Height"))
            if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > geometry[3] or y + h > geometry[4]:
                raise ValueError("Window must be wholly on the main display")
            return x, y, x + w, y + h
    raise ValueError("Window is missing or no longer on screen")


def _pixel_hash(png: bytes, crop: tuple[int, int, int, int]) -> str:
    with Image.open(io.BytesIO(png)) as image:
        return hashlib.sha256(image.convert("RGB").crop(crop).tobytes()).hexdigest()


class FrameTool(BaseTool):
    def __init__(
        self, legacy: BaseTool, state: FrameState, check: Callable[[], None] | None = None,
    ) -> None:
        self.legacy = legacy
        self.state = state
        self.check = check

    def get_metadata(self) -> ToolMetadata:
        return self.legacy.get_metadata()

    def get_info(self) -> ToolInfo:
        info = self.legacy.get_info()
        return info.model_copy(
            update={
                "description": info.description
                + (
                    ' Opt in with coordinate_space="image": use zero-based pixels in the '
                    "returned image and its frame_id; the host reverses crop/zoom. "
                    "Legacy normalized coordinates remain the default."
                ),
                "parameters": [
                    *info.parameters,
                    ToolParameter(
                        name="coordinate_space",
                        type="string",
                        required=False,
                        description="legacy (default) or image (frame-bound image pixels)",
                    ),
                    ToolParameter(
                        name="frame_id",
                        type="string",
                        required=False,
                        description="Required for image-coordinate actions; returned by screenshot",
                    ),
                    ToolParameter(
                        name="window_id",
                        type="integer",
                        required=False,
                        description="Image mode: bind a main-display Quartz window ID",
                    ),
                ],
            }
        )

    def get_raw_schema(self) -> dict[str, Any]:
        info = self.legacy.get_info()
        legacy = self.legacy.get_raw_schema() or {
            "type": "object",
            "properties": {
                p.name: {"type": p.type, "description": p.description} for p in info.parameters
            },
            "required": [p.name for p in info.parameters if p.required],
            "additionalProperties": False,
        }
        for value in legacy["properties"].values():
            if value.get("type") == "array":
                value.setdefault("items", {})
        # Separate branches prevent a missing frame silently falling back to legacy.
        legacy = {
            **legacy,
            "properties": {
                **legacy["properties"],
                "coordinate_space": {"enum": ["legacy"]},
            },
        }
        properties: dict[str, Any] = {
            p.name: {"type": p.type, "description": p.description} for p in info.parameters
        }
        for key in ("x", "y", "x1", "y1", "x2", "y2"):
            if key in properties:
                properties[key] = {"type": "number", "description": "Position in image pixels"}
        if "region" in properties:
            properties["region"].update(items={"type": "integer", "minimum": 0, "maximum": 1000},
                                        minItems=4, maxItems=4)
        if "bbox" in properties:
            properties["bbox"] = {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 4,
                "maxItems": 4,
            }
        properties["coordinate_space"] = {"enum": ["image"]}
        properties["window_id"] = {"type": "integer", "minimum": 1}
        required = [p.name for p in info.parameters if p.required]
        if info.name != "screenshot":
            properties["frame_id"] = {"type": "string"}
            if info.name != "scroll":
                required.append("frame_id")
        image = {
            "type": "object",
            "properties": properties,
            "required": ["coordinate_space", *required],
            "additionalProperties": False,
        }
        if info.name == "click":
            image["oneOf"] = [
                {"required": ["x", "y"], "not": {"required": ["bbox"]}},
                {
                    "required": ["bbox"],
                    "not": {"anyOf": [{"required": ["x"]}, {"required": ["y"]}]},
                },
            ]
        if info.name == "scroll":
            image["oneOf"] = [
                {"required": ["x", "y", "frame_id"]},
                {
                    "not": {
                        "anyOf": [{"required": [k]} for k in ("x", "y", "frame_id", "window_id")]
                    }
                },
            ]
        return {"type": "object", "oneOf": [legacy, image]}

    async def execute(
        self,
        *,
        coordinate_space: str = "legacy",
        frame_id: str | None = None,
        ctx: ToolContext | None = None,
        **kwargs: Any,
    ) -> ToolResult | str:
        if coordinate_space == "legacy" and frame_id is None:
            if self.legacy.get_info().name == "screenshot":
                self.state.observation = None
            return await self.legacy.execute(**kwargs)
        if coordinate_space != "image":
            return ToolResult(content="Use coordinate_space=image with frame_id", error=True)
        allowed = {p.name for p in self.legacy.get_info().parameters} | {"window_id"}
        if kwargs.keys() - allowed:
            return ToolResult(content="Unknown image-coordinate arguments", error=True)
        if self.legacy.get_info().name == "scroll" and "x" not in kwargs and "y" not in kwargs:
            if frame_id is not None or "window_id" in kwargs:
                return ToolResult(content="Unpositioned scroll has no frame/window", error=True)
            return await self.legacy.execute(**kwargs)
        if ctx is None or not ctx.session_id:
            return ToolResult(content="Image coordinates require a session; re-observe", error=True)
        cancelled = threading.Event()
        task = asyncio.create_task(
            asyncio.to_thread(
                self._locked_execute,
                ctx.session_id,
                frame_id,
                kwargs,
                cancelled,
            )
        )
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled.set()
            try:
                await asyncio.shield(task)
            except (ValueError, RuntimeError, OSError):
                pass  # Preserve cancellation even if the in-flight capture fails.
            finally:
                self.state.observation = None
            raise
        except (ValueError, RuntimeError, OSError) as exc:
            self.state.observation = None
            return ToolResult(content=f"{exc}; re-observe with coordinate_space=image", error=True)

    def _locked_execute(
        self,
        session_id: str,
        frame_id: str | None,
        arguments: dict[str, Any],
        cancelled: threading.Event,
    ) -> ToolResult:
        with self.state.lock:
            if cancelled.is_set():
                raise ValueError("Action cancelled")
            return self._execute_image(session_id, frame_id, arguments, cancelled)

    def _execute_image(
        self,
        session_id: str,
        frame_id: str | None,
        arguments: dict[str, Any],
        cancelled: threading.Event,
    ) -> ToolResult:
        name = self.legacy.get_info().name
        if name == "screenshot":
            self.state.observation = None
            if frame_id is not None:
                raise ValueError("Screenshot creates a new frame; omit frame_id")
            geometry = _geometry()
            window_id = arguments.get("window_id")
            bounds = _window_bounds(window_id, geometry)
            png = macos._capture_screenshot_macos(include_cursor=False)
            if geometry != _geometry() or bounds != _window_bounds(window_id, geometry):
                raise ValueError("Display changed during capture")

            region = arguments.get("region")
            parsed = parse_region(region) if region is not None else None
            if region is not None and (
                not isinstance(region, list)
                or len(region) != 4
                or any(type(v) is not int or not 0 <= v <= 1000 for v in region)
                or parsed is None
            ):
                raise ValueError("Invalid screenshot region")
            observation, png = Observation.capture(
                png,
                session_id=session_id,
                display_id=int(macos._load_quartz().CGMainDisplayID()),
                region=parsed,
                window_id=window_id,
                window_bounds=bounds,
                display_geometry=geometry,
            )
            if observation.screen_size != geometry[3:5]:
                raise ValueError("Screenshot dimensions do not match display")
            self.state.observation = observation
            self.state.png = png
            return ToolResult(
                content=[
                    TextBlock(
                        text="Image coordinates (zero-based pixels). "
                        + json.dumps(
                            asdict(observation),
                        )
                    ),
                    ImageBlock(
                        source="data:image/png;base64," + base64.b64encode(png).decode(),
                        mime_type="image/png",
                        detail="auto",
                    ),
                ],
                display="Screenshot captured",
            )
        observation = self._validate_observation(session_id, frame_id, arguments)
        if cancelled.is_set():
            raise ValueError("Action cancelled")
        if self.check is not None:
            self.check()
        return self._dispatch_image(observation, arguments)

    async def validate(
        self, session_id: str, frame_id: str, window_id: int | None,
    ) -> Observation:
        """Validate a locate frame without injecting any desktop input."""
        def locked() -> Observation:
            with self.state.lock:
                return self._validate_observation(session_id, frame_id, {"window_id": window_id})

        return await asyncio.to_thread(locked)

    def _validate_observation(
        self, session_id: str, frame_id: str | None, arguments: dict[str, Any],
    ) -> Observation:
        observation = self.state.observation
        if observation is None or not frame_id or frame_id != observation.frame_id:
            raise ValueError("Missing or stale frame")
        if session_id != observation.session_id:
            raise ValueError("Frame belongs to another session")
        if arguments.get("window_id", observation.window_id) != observation.window_id:
            raise ValueError("Frame belongs to another window")
        if (
            _window_bounds(observation.window_id, observation.display_geometry)
            != observation.window_bounds
        ):
            raise ValueError("Window geometry changed")
        if _geometry() != observation.display_geometry:
            raise ValueError("Display geometry changed")
        current = macos._capture_screenshot_macos(include_cursor=False)
        if (
            _pixel_hash(current, observation.crop) != observation.scene_sha256
            or _geometry() != observation.display_geometry
        ):
            raise ValueError("Scene or geometry changed since observation")
        if (
            _window_bounds(observation.window_id, observation.display_geometry)
            != observation.window_bounds
        ):
            raise ValueError("Window changed during validation")
        return observation

    def _dispatch_image(self, observation: Observation, arguments: dict[str, Any]) -> ToolResult:
        name = self.legacy.get_info().name
        if name == "drag":
            start = observation.map_point(arguments.get("x1"), arguments.get("y1"))
            end = observation.map_point(arguments.get("x2"), arguments.get("y2"))
            macos._drag_macos(*start, *end)
            return ToolResult(content=f"Dragged image targets → Quartz {start} → {end}")
        bbox = arguments.get("bbox")
        if bbox is not None:
            if name != "click" or "x" in arguments or "y" in arguments:
                raise ValueError("Pass either x/y or bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                raise ValueError("bbox must have four image coordinates")
            observation.map_point(bbox[0], bbox[1])
            observation.map_point(bbox[2], bbox[3])
            if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                raise ValueError("bbox must be ordered and nonempty")
            x, y = observation.map_point((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
        else:
            x, y = observation.map_point(arguments.get("x"), arguments.get("y"))
        if name == "click":
            button, clicks = arguments.get("button", "left"), arguments.get("clicks", 1)
            if (
                button not in ("left", "right", "middle")
                or type(clicks) is not int
                or not 1 <= clicks <= 3
            ):
                raise ValueError("Invalid click button/count")
            macos._click_macos(x, y, button, clicks)
        elif name == "mouse_move":
            macos._move_macos(x, y)
        elif name == "scroll":
            amount = arguments.get("amount")
            if type(amount) is not int or not -50 <= amount <= 50:
                raise ValueError("scroll amount must be an integer between -50 and 50")
            macos._scroll_macos(amount, x, y)
        return ToolResult(content=f"{name}: image target → Quartz ({x}, {y})")
