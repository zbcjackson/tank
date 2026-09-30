"""Optional local macOS Vision OCR. Text evidence never implies an input action."""

import hashlib
import importlib
import io
import math
from collections.abc import Awaitable, Callable
from itertools import islice
from typing import Any
from uuid import uuid4

from PIL import Image

from tank_backend.agents.subagent import SubAgentContext, SubAgentStopped
from tank_backend.tools.computer_native import run_native
from tank_backend.tools.computer_observation import Observation

from .contracts import Element, Snapshot


def recognize_text(frame: Observation, png: bytes) -> tuple[Element, ...]:
    """Recognize the exact M2 image; return top-left image-pixel text bounds."""
    if len(png) > 16 * 1024 * 1024:
        raise ValueError("OCR image byte limit exceeded")
    if hashlib.sha256(png).hexdigest() != frame.image_sha256:
        raise ValueError("OCR image does not match its frame")
    with Image.open(io.BytesIO(png)) as image:
        if (image.format != "PNG" or image.size != frame.image_size
                or image.width * image.height > 16_000_000):
            raise ValueError("OCR requires the bound PNG dimensions")
    # PyObjC framework symbols are dynamic; imports must remain optional/lazy.
    vision: Any = importlib.import_module("Vision")
    request = vision.VNRecognizeTextRequest.alloc().init()
    request.setRevision_(3)
    request.setRecognitionLevel_(vision.VNRequestTextRecognitionLevelAccurate)
    request.setRecognitionLanguages_(["zh-Hans", "en-US"])
    request.setUsesLanguageCorrection_(False)
    handler = vision.VNImageRequestHandler.alloc().initWithData_options_(png, {})
    ok, error = handler.performRequests_error_([request], None)
    if not ok or error is not None:
        raise RuntimeError("Vision text recognition failed")
    width, height = frame.image_size
    regions = []
    for index, observation in enumerate(islice(request.results() or (), 501)):
        if index == 500:
            raise ValueError("OCR region limit exceeded")
        candidates = observation.topCandidates_(1)
        if not candidates:
            continue
        text = str(candidates[0].string())
        if len(text) > 4096:
            raise ValueError("OCR text limit exceeded")
        rect = observation.boundingBox()
        x, y, w, h = (float(rect.origin.x), float(rect.origin.y),
                      float(rect.size.width), float(rect.size.height))
        if (not all(math.isfinite(n) for n in (x, y, w, h))
                or not (0 <= x < x + w <= 1 and 0 <= y < y + h <= 1)):
            raise ValueError("Vision returned invalid text bounds")
        regions.append(Element(
            f"{frame.frame_id}:ocr:{len(regions)}", "text", text, (),
            kind="text_region", source="ocr",
            bounds=(x * width, (1 - y - h) * height, w * width, h * height),
        ))
    return tuple(regions)


class VisionObservationSource:
    """Local text-only observation using a host-supplied bound frame capture."""

    def __init__(
        self, bound: Observation, scope: str,
        capture: Callable[[], Awaitable[tuple[Observation, bytes]]],
    ) -> None:
        self.bound, self.scope, self.capture = bound, scope, capture
        self.closed = False
        self.task_id: str | None = None
        self.generation = 0

    async def observe(self, scope: str, context: SubAgentContext) -> Snapshot:
        context.check("desktop")
        context.runtime.check_open()
        if self.closed:
            raise SubAgentStopped("channel_closed")
        if scope != self.scope:
            raise SubAgentStopped("scope_mismatch")
        if self.task_id is not None and self.task_id != context.runtime.task_id:
            raise SubAgentStopped("task_mismatch")
        self.task_id = context.runtime.task_id
        frame, png = await self.capture()
        context.check("desktop")
        context.runtime.check_open()
        if self.closed:
            raise SubAgentStopped("channel_closed")
        if (frame.session_id, frame.window_id, frame.display_id, frame.display_geometry) != (
            self.bound.session_id, self.bound.window_id,
            self.bound.display_id, self.bound.display_geometry,
        ):
            raise SubAgentStopped("scope_mismatch")

        def read() -> tuple[Element, ...]:
            context.check("desktop")
            context.runtime.check_open()
            if self.closed:
                raise SubAgentStopped("channel_closed")
            return recognize_text(frame, png)

        try:
            elements = await run_native(read)
        except ModuleNotFoundError:
            return Snapshot(uuid4().hex, scope, self.generation, ready=False)
        context.check("desktop")
        context.runtime.check_open()
        if self.closed:
            raise SubAgentStopped("channel_closed")
        self.generation += 1
        return Snapshot(uuid4().hex, scope, self.generation, elements)

    async def aclose(self) -> None:
        self.closed = True
