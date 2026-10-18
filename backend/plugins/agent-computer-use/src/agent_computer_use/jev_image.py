"""Read-only Jev image capability probes and reversible frame normalization."""

from __future__ import annotations

import hashlib
import io
import math
from dataclasses import asdict, dataclass
from uuid import uuid4

from PIL import Image, ImageOps

from tank_backend.agents.subagent import SubAgentContext, SubAgentStopped
from tank_backend.agents.task_runtime import TaskOperation
from tank_backend.llm.decision_model import BoxResult, ChoiceResult
from tank_backend.llm.model_call import model_purpose
from tank_backend.llm.model_data import ModelImageAsset

from .contracts import Snapshot
from .visual_selector import VisualFrame, VisualSource


@dataclass(frozen=True)
class JevImage:
    source: VisualFrame
    asset: ModelImageAsset
    size: tuple[int, int]
    content: tuple[int, int, int, int]
    orientation: int

    def metadata(self) -> dict[str, object]:
        return {
            "source": asdict(self.source.frame),
            "observation_id": self.source.observation_id,
            "image_sha256": hashlib.sha256(self.asset.data).hexdigest(),
            "size": self.size,
            "content": self.content,
            "orientation": self.orientation,
        }

    def map_box(self, box: tuple[float, float, float, float]) -> tuple[int, int]:
        if (
            not all(math.isfinite(v) and 0 <= v <= 1 for v in box)
            or not box[0] < box[2]
            or not box[1] < box[3]
        ):
            raise ValueError("invalid normalized box")
        width, height = self.size
        left, top, right, bottom = self.content
        if not (
            left <= box[0] * width < box[2] * width <= right
            and top <= box[1] * height < box[3] * height <= bottom
        ):
            raise ValueError("box intersects image padding")
        raw_width, raw_height = self.source.frame.image_size
        rotated_width, rotated_height = (
            (raw_height, raw_width)
            if self.orientation >= 5
            else (raw_width, raw_height)
        )
        x = ((box[0] + box[2]) * width / 2 - left) * rotated_width / (right - left)
        y = ((box[1] + box[3]) * height / 2 - top) * rotated_height / (bottom - top)
        point = {
            1: (x, y),
            2: (raw_width - x, y),
            3: (raw_width - x, raw_height - y),
            4: (x, raw_height - y),
            5: (y, x),
            6: (y, raw_height - x),
            7: (raw_width - y, raw_height - x),
            8: (raw_width - y, x),
        }[self.orientation]
        return self.source.frame.map_point(*point)


def normalize_frame(source: VisualFrame) -> JevImage:
    frame, data = source.frame, source.png
    if (
        not data
        or len(data) > 16 * 1024 * 1024
        or hashlib.sha256(data).hexdigest() != frame.image_sha256
    ):
        raise ValueError("image does not match source frame")
    with Image.open(io.BytesIO(data)) as original:
        if (
            original.format not in {"PNG", "JPEG"}
            or original.size != frame.image_size
            or getattr(original, "n_frames", 1) != 1
            or original.width * original.height > 16_000_000
        ):
            raise ValueError("unsupported source image")
        orientation = original.getexif().get(274, 1)
        if type(orientation) is not int or orientation not in range(1, 9):
            raise ValueError("unsupported image orientation")
        upright = ImageOps.exif_transpose(original).convert("RGB")
        factor = min(1568 / max(upright.size), max(1.0, 280 / min(upright.size)))
        resized = upright.resize(
            (
                max(1, round(upright.width * factor)),
                max(1, round(upright.height * factor)),
            ),
            Image.Resampling.LANCZOS,
        )
        size = (max(280, resized.width), max(280, resized.height))
        canvas = Image.new("RGB", size, "white")
        left, top = (size[0] - resized.width) // 2, (size[1] - resized.height) // 2
        canvas.paste(resized, (left, top))
        output = io.BytesIO()
        canvas.save(output, "PNG")
    asset = ModelImageAsset(
        "tank-image-" + uuid4().hex, "asset-0", "image/png", output.getvalue()
    )
    return JevImage(
        source,
        asset,
        size,
        (left, top, left + resized.width, top + resized.height),
        orientation,
    )


class JevImageProbe:
    """Capability research only: no executor, action proposals or factory selector registration."""

    def __init__(self, source: VisualSource, context: SubAgentContext) -> None:
        self.context = context
        self.capture: TaskOperation[Snapshot, VisualFrame] = TaskOperation(
            "jev_image.capture",
            frozenset({"desktop"}),
            "read",
            lambda snapshot: source.capture(snapshot, context),
        )
        context.runtime.register(self.capture)

    async def assess(
        self,
        snapshot: Snapshot,
        *,
        state: dict[str, object],
        instructions: str,
        options: dict[str, object] | None = None,
    ) -> tuple[JevImage, ChoiceResult | BoxResult]:
        context = self.context
        context.check("desktop")
        context.check("network")
        if context.budget.unknown_calls:
            raise SubAgentStopped("unknown_usage")
        model = context.runtime.decision_model
        if model is None or "image" not in context.model_data_scope.allowed_types:
            raise SubAgentStopped("decision_images_denied")
        # Check recipient opt-in before capture, not just the generic task allowance.
        if not model.images_enabled:
            raise SubAgentStopped("decision_images_denied")
        captured = await context.runtime.execute(self.capture, snapshot)
        if (
            captured.observation_id != snapshot.observation_id
            or captured.frame.session_id != context.runtime.task_id
        ):
            raise SubAgentStopped("stale_visual_frame")
        prepared = normalize_frame(captured)
        payload = {**state, "image_metadata": prepared.metadata()}
        with model_purpose(
            "computer_use.jev_image_choice"
            if options is not None
            else "computer_use.jev_box"
        ):
            result = (
                await model.choose_image(
                    state=payload,
                    image=prepared.asset,
                    instructions=instructions,
                    options=options,
                )
                if options is not None
                else await model.locate_image(
                    state=payload, image=prepared.asset, target=instructions
                )
            )
        context.check("desktop")
        if context.budget.unknown_calls:
            raise SubAgentStopped("unknown_usage")
        after = await context.runtime.execute(self.capture, snapshot)
        # A read-only second capture reuses native/DOM window and reference checks.
        before_frame, after_frame = captured.frame, after.frame
        if after.observation_id != snapshot.observation_id or (
            after_frame.session_id,
            after_frame.window_id,
            after_frame.window_bounds,
            after_frame.display_geometry,
            after_frame.image_sha256,
            after_frame.image_size,
            after_frame.crop,
        ) != (
            before_frame.session_id,
            before_frame.window_id,
            before_frame.window_bounds,
            before_frame.display_geometry,
            before_frame.image_sha256,
            before_frame.image_size,
            before_frame.crop,
        ):
            raise SubAgentStopped("stale_visual_frame")
        return prepared, result
