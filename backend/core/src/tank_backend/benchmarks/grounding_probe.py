"""Synthetic-only diagnostic; never execute model actions or capture the desktop."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageDraw

from ..tools.computer_grounding import GroundingAdapter


@dataclass
class HoldoutBudget:
    """Count every attempt; unknown usage retains its full reservation and stops."""

    max_requests: int = 384
    max_tokens: int = 3000000
    reservation: int = 18000
    input_limit: int = 10000
    requests: int = 0
    known_tokens: int = 0
    unknown_reservation: int = 0
    stop_reason: str | None = None

    def can_start(self) -> bool:
        return (
            self.stop_reason is None and self.requests < self.max_requests
            and self.known_tokens + self.unknown_reservation + self.reservation <= self.max_tokens
        )

    def record(self, prompt_tokens: int | None, total_tokens: int | None) -> str | None:
        self.requests += 1
        if prompt_tokens is None or total_tokens is None:
            self.unknown_reservation += self.reservation
            self.stop_reason = "unknown_usage"
        else:
            self.known_tokens += total_tokens
            if prompt_tokens > self.input_limit:
                self.stop_reason = "input_reservation_exceeded"
            elif self.known_tokens + self.unknown_reservation > self.max_tokens:
                self.stop_reason = "token_budget_exceeded"
        return self.stop_reason


def score_holdout_location(
    expected: str, point: tuple[float, float] | None, valid: bool,
    mask: Image.Image, center: tuple[float, float] | None,
) -> dict[str, float | bool | None]:
    """Score a parsed attempt against isolated visible pixels, never a bounding box."""
    hit = False
    distance = None
    if valid and point is not None:
        x, y = (math.floor(value + 0.5) for value in point)
        hit = expected == "found" and 0 <= x < mask.width and 0 <= y < mask.height and bool(
            mask.getpixel((x, y)),
        )
        if expected == "found" and center is not None:
            distance = math.dist(point, center)
    return {
        "success": valid and (hit if expected == "found" else point is None),
        "hit": hit,
        "false_positive": valid and expected != "found" and point is not None,
        "distance": distance,
    }


def qwen_native_request(request: dict[str, Any]) -> dict[str, Any]:
    """Translate the diagnostic Chat request to DashScope's native multimodal API."""
    messages = []
    for message in request["messages"]:
        content = message["content"]
        parts: list[dict[str, Any]] = (
            [{"type": "text", "text": content}] if isinstance(content, str) else content
        )
        converted = []
        for part in parts:
            if part["type"] == "text":
                converted.append({"text": part["text"]})
            elif part["type"] == "image_url" and part["image_url"].get("detail", "auto") == "auto":
                converted.append({"image": part["image_url"]["url"]})
            else:
                raise ValueError("Native probe supports only text and auto-detail images")
        messages.append({"role": message["role"], "content": converted})
    parameters = {key: value for key, value in request.items()
                  if key not in {"model", "messages", "stream", "extra_body"}}
    parameters.update(request.get("extra_body", {}))
    return {"model": request["model"], "input": {"messages": messages}, "parameters": parameters}


def score_location(
    point: tuple[float, float], bounds: tuple[int, int, int, int], radius: int,
) -> dict[str, float | bool]:
    """Score against the rendered rounded button, not its enclosing rectangle."""
    left, top, right, bottom = bounds
    mask = Image.new("1", (right - left + 1, bottom - top + 1))
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, right - left, bottom - top), radius=radius, fill=1,
    )
    x, y = point
    hit = left <= x <= right and top <= y <= bottom and bool(
        mask.getpixel((int(x) - left, int(y) - top)),
    )
    dx, dy = x - (left + right) / 2, y - (top + bottom) / 2
    return {"hit": hit, "dx": dx, "dy": dy, "distance": math.hypot(dx, dy)}


def location_request(
    provider: str, model: str, png: bytes, size: tuple[int, int], target: str,
    protocol: str, *, strict: bool = False, previous: bytes | None = None,
    system: str = "Locate the requested UI element in the current image.",
    marked: bool = False, detail: str = "auto", thinking: bool = True,
    nullable_style: str = "type-array", max_tokens: int = 4000,
) -> dict[str, Any]:
    """Compatibility probe API using the production location protocol builder."""
    request = GroundingAdapter(protocol, nullable_style, strict, detail).build_request(
        png, size, target, previous=previous, system=system, marked=marked,
    )
    request.update(model=model, stream=False)
    if provider == "qwen":
        request.update(temperature=0.1, max_tokens=max_tokens,
                       extra_body={"enable_thinking": thinking})
    elif provider == "deepseek":
        request.update(temperature=0.1, max_tokens=max_tokens,
                       extra_body={"thinking": {"type": "enabled" if thinking else "disabled"}})
    elif provider == "openai":
        request.update(max_completion_tokens=max_tokens,
                       reasoning_effort="low" if thinking else "none")
    elif provider == "openrouter":
        request.update(max_tokens=max_tokens, extra_body={
            "reasoning": {"effort": "low" if thinking else "none"},
            "provider": {"only": ["openai"], "allow_fallbacks": False,
                         "require_parameters": True},
        })
    else:
        raise ValueError("Unknown provider")
    return request


def decode_location(
    raw: str, protocol: str, size: tuple[int, int],
    crop: tuple[int, int, int, int] | None = None,
    *, abstention_zero: bool = False,
) -> tuple[float, float] | None:
    """Compatibility scorer: shared image parsing, then benchmark-only crop mapping."""
    location = GroundingAdapter(
        protocol, "integer" if abstention_zero else "type-array",
    ).parse(raw, size)
    if location.point is None:
        return None
    x, y = location.point
    w, h = size
    ox, oy, cw, ch = crop or (0, 0, w, h)
    if cw <= 0 or ch <= 0:
        raise ValueError("Invalid crop extent")
    return ox + x * cw / w, oy + y * ch / h


def response_point(arguments: dict) -> tuple[float, float] | None:
    """Decode a diagnostic response without assuming a coordinate range."""
    values = arguments.get("bbox", arguments.get("x"))
    if "bbox" in arguments and ("x" in arguments or "y" in arguments):
        return None
    if not isinstance(values, list):
        if "bbox" in arguments:
            return None
        values = [values, arguments.get("y")]
    if len(values) not in (2, 4):
        return None
    nums: list[float] = []
    try:
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                return None
            nums.append(float(value))
    except (ValueError, OverflowError):
        return None
    if not all(math.isfinite(v) for v in nums):
        return None
    if len(nums) == 4:
        return (nums[0] + nums[2]) / 2, (nums[1] + nums[3]) / 2
    return nums[0], nums[1]


def text_response_point(text: str, *, native_bbox: bool = False) -> tuple[float, float] | None:
    """Score a whole JSON answer, optionally fenced; never repair broken JSON."""
    text = text.strip()
    if text.startswith("```json\n") and text.endswith("\n```"):
        text = text[len("```json\n"):-len("\n```")]
    try:
        arguments = json.loads(text)
    except json.JSONDecodeError:
        return None
    if native_bbox:
        if not isinstance(arguments, list) or len(arguments) != 1:
            return None
        item = arguments[0]
        box = item.get("bbox_2d") if isinstance(item, dict) else None
        if not isinstance(box, list) or len(box) != 4:
            return None
        return response_point({"bbox": box})
    return response_point(arguments) if isinstance(arguments, dict) else None


def score_point(
    point: tuple[float, float], size: tuple[int, int], target: tuple[float, float],
) -> dict[str, float]:
    """Distance in original-image pixels under three explicit hypotheses."""
    x, y = point
    w, h = size
    scale = min(1, 1280 / max(size))
    candidates = {
        "normalized": (x * w / 1000, y * h / 1000),
        "pixels": (x, y),
        "long_edge_1280": (x / scale, y / scale),
    }
    return {name: math.dist(candidate, target) for name, candidate in candidates.items()}
