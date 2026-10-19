"""Immutable screenshot identity and image-pixel → global Quartz point mapping."""

from __future__ import annotations

import hashlib
import io
import math
import time
import uuid
from dataclasses import dataclass

from PIL import Image


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
            pixel_width, pixel_height = image.size
        width, height = pixel_width, pixel_height
        if len(display_geometry) == 7:
            width, height = display_geometry[3:5]
            if (width <= 0 or height <= 0
                    or (pixel_width, pixel_height) not in (
                        (width, height), display_geometry[5:7])):
                raise ValueError("Screenshot dimensions do not match the bound display")
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
            raise ValueError("Crop/window must lie inside the captured display image")
        with Image.open(io.BytesIO(png)) as image:
            # Crop backing pixels before any filtering can mix in pixels outside the window.
            pixels = image.crop((round(left * pixel_width / width),
                                 round(top * pixel_height / height),
                                 round(right * pixel_width / width),
                                 round(bottom * pixel_height / height)))
            scene_hash = hashlib.sha256(pixels.convert("RGB").tobytes()).hexdigest()
            if crop != (0, 0, width, height) or image.size != (width, height):
                scale = min(max(width, height) / max(right - left, bottom - top), 3.0)
                scale = scale if scale > 1.01 else 1.0
                size = (round((right - left) * scale), round((bottom - top) * scale))
                if pixels.size != size:
                    pixels = pixels.resize(size, Image.Resampling.LANCZOS)
                buffer = io.BytesIO()
                pixels.save(buffer, format="PNG")
                png = buffer.getvalue()
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
        """Zero-based image pixels → GLOBAL Quartz points; round half up once.

        The image is one display's screenshot; the crop maps into that
        display's local point space, then the bound display origin
        (``display_geometry[1:3]``, (0,0) for the main display) translates it
        into the global CGEvent coordinate space.
        """
        width, height = self.image_size
        if (isinstance(x, bool) or not isinstance(x, (int, float))
                or isinstance(y, bool) or not isinstance(y, (int, float))):
            raise ValueError("point must be numeric image coordinates")
        if not (math.isfinite(x) and math.isfinite(y) and 0 <= x < width and 0 <= y < height):
            raise ValueError("point must be finite coordinates inside the observed image")
        left, top, right, bottom = self.crop
        ox, oy = self.display_geometry[1:3] if len(self.display_geometry) >= 3 else (0, 0)
        return (
            min(right - 1, math.floor(left + x * (right - left) / width + 0.5)) + ox,
            min(bottom - 1, math.floor(top + y * (bottom - top) / height + 0.5)) + oy,
        )
