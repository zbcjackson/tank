"""Immutable screenshot identity and image-pixel → main-display point mapping."""

from __future__ import annotations

import hashlib
import io
import math
import time
import uuid
from dataclasses import dataclass

from PIL import Image

from .computer_use_common import crop_pixels_and_upscale


@dataclass(frozen=True)
class Observation:
    frame_id: str
    session_id: str
    display_id: int
    screen_size: tuple[int, int]
    image_size: tuple[int, int]
    crop: tuple[int, int, int, int]
    image_sha256: str
    captured_at: float
    display_geometry: tuple[int, ...] = ()
    window_id: int | None = None
    window_bounds: tuple[int, int, int, int] | None = None
    scene_sha256: str = ""

    @classmethod
    def capture(
        cls,
        png: bytes,
        *,
        session_id: str,
        display_id: int,
        region: tuple[int, int, int, int] | None = None,
        window_id: int | None = None,
        window_bounds: tuple[int, int, int, int] | None = None,
        display_geometry: tuple[int, ...] = (),
    ) -> tuple[Observation, bytes]:
        with Image.open(io.BytesIO(png)) as image:
            width, height = image.size
        crop = window_bounds or (0, 0, width, height)
        origin_x, origin_y, right, bottom = crop
        area_width, area_height = right - origin_x, bottom - origin_y
        if region is not None:
            x1, y1, x2, y2 = region
            left = origin_x + round(x1 * area_width / 1000)
            top = origin_y + round(y1 * area_height / 1000)
            crop = (
                left,
                top,
                max(left + 1, origin_x + round(x2 * area_width / 1000)),
                max(top + 1, origin_y + round(y2 * area_height / 1000)),
            )
        left, top, right, bottom = crop
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise ValueError("Crop/window must lie inside the main display image")
        with Image.open(io.BytesIO(png)) as image:
            scene_hash = hashlib.sha256(image.convert("RGB").crop(crop).tobytes()).hexdigest()
        if crop != (0, 0, width, height):
            png = crop_pixels_and_upscale(png, crop)
        with Image.open(io.BytesIO(png)) as image:
            image_size = image.size
        return cls(
            frame_id=uuid.uuid4().hex,
            session_id=session_id,
            display_id=display_id,
            screen_size=(width, height),
            image_size=image_size,
            crop=crop,
            image_sha256=hashlib.sha256(png).hexdigest(),
            captured_at=time.time(),
            display_geometry=display_geometry,
            window_id=window_id,
            window_bounds=window_bounds,
            scene_sha256=scene_hash,
        ), png

    def map_point(self, x: object, y: object) -> tuple[int, int]:
        """Zero-based image pixels; round half up once, at the OS boundary."""
        width, height = self.image_size
        if (isinstance(x, bool) or not isinstance(x, (int, float))
                or isinstance(y, bool) or not isinstance(y, (int, float))):
            raise ValueError("point must be numeric image coordinates")
        if not (math.isfinite(x) and math.isfinite(y) and 0 <= x < width and 0 <= y < height):
            raise ValueError("point must be finite coordinates inside the observed image")
        left, top, right, bottom = self.crop
        return (
            min(right - 1, math.floor(left + x * (right - left) / width + 0.5)),
            min(bottom - 1, math.floor(top + y * (bottom - top) / height + 0.5)),
        )
