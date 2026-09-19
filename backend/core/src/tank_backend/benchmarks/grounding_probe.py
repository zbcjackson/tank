"""Synthetic-only diagnostic; never execute model actions or capture the desktop."""

from __future__ import annotations

import base64
import json
import math
from typing import Any

from PIL import Image, ImageDraw


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
    nullable_style: str = "type-array",
) -> dict[str, Any]:
    """Build a synthetic diagnostic request, not a production executor request.

    Provider defaults are deliberately explicit. GPT omits sampling parameters;
    equivalent reasoning budgets across providers are not assumed.
    """
    if protocol not in {"point", "pixels", "bbox"}:
        raise ValueError("Unknown coordinate protocol")
    fields = ("left", "top", "right", "bottom") if protocol == "bbox" else ("x", "y")
    limits = (size[0] - 1, size[1] - 1) if protocol == "pixels" else (1000,) * len(fields)
    properties: dict[str, Any] = {"found": {"type": "boolean"}}
    properties.update({field: {"type": ["integer", "null"], "minimum": 0, "maximum": limit}
                       for field, limit in zip(fields, limits, strict=True)})
    if nullable_style == "anyof":
        for field, limit in zip(fields, limits, strict=True):
            properties[field] = {"anyOf": [
                {"type": "integer", "minimum": 0, "maximum": limit}, {"type": "null"},
            ]}
    elif nullable_style == "integer":
        for field in fields:
            properties[field]["type"] = "integer"
    elif nullable_style != "type-array":
        raise ValueError("Unknown nullable schema style")
    function: dict[str, Any] = {
        "name": "click", "description": "Report one target location; no action is executed.",
        "parameters": {"type": "object", "properties": properties,
                       "required": ["found", *fields], "additionalProperties": False},
    }
    if strict:
        function["strict"] = True
    units = (f"original input image pixels, x=0..{size[0]-1}, y=0..{size[1]-1}"
             if protocol == "pixels" else "normalized coordinates, x=0..1000, y=0..1000")
    what = "tight bounding box of the button" if protocol == "bbox" else "center of the button"
    question = (
        f"CURRENT image: {size[0]}x{size[1]}. Locate the button labeled {target}. "
        + ("It is outlined in cyan. " if marked else "")
        + f"Call click once with its {what} in {units}. "
        "The origin is the top-left of THIS input image; each axis spans the full image. "
        "Use only the CURRENT image, not previous positions. Set found=true when located. "
        "If absent or uncertain, set found=false and ALL coordinates="
        + ("0." if nullable_style == "integer" else "null.")
    )

    def image_message(data: bytes, text: str) -> dict[str, Any]:
        return {"role": "user", "content": [{"type": "text", "text": text}, {
            "type": "image_url", "image_url": {
                "url": "data:image/png;base64," + base64.b64encode(data).decode(),
                "detail": detail,
            },
        }]}

    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    if previous is not None:
        # Image-only history isolates stale visual positions, without fabricated CoT.
        messages.append(image_message(previous, "PREVIOUS image, superseded by the next image."))
    messages.append(image_message(png, question))
    request: dict[str, Any] = {
        "model": model, "messages": messages, "tools": [{"type": "function", "function": function}],
        "stream": False,
    }
    if provider == "qwen":
        request.update(temperature=0.1, max_tokens=4000,
                       extra_body={"enable_thinking": thinking})
    elif provider == "deepseek":
        request.update(temperature=0.1, max_tokens=4000,
                       extra_body={"thinking": {"type": "enabled" if thinking else "disabled"}})
    elif provider == "openai":
        request.update(max_completion_tokens=4000, reasoning_effort="low" if thinking else "none")
    elif provider == "openrouter":
        request.update(max_tokens=4000, extra_body={
            "reasoning": {"effort": "low" if thinking else "none"},
            "provider": {"only": ["openai"], "allow_fallbacks": False,
                         "require_parameters": True},
        })
    else:
        raise ValueError("Unknown provider")
    return request


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate field: {key}")
        result[key] = value
    return result


def decode_location(
    raw: str, protocol: str, size: tuple[int, int],
    crop: tuple[int, int, int, int] | None = None,
    *, abstention_zero: bool = False,
) -> tuple[float, float] | None:
    """Validate one protocol, then map image coordinates to the source frame.

    crop is (left, top, source_width, source_height) before image resizing.
    None means an explicit abstention; invalid output raises, never repairs.
    """
    if protocol not in {"point", "pixels", "bbox"}:
        raise ValueError("Unknown coordinate protocol")
    fields = ("left", "top", "right", "bottom") if protocol == "bbox" else ("x", "y")
    obj = json.loads(raw, object_pairs_hook=_unique_object)
    if not isinstance(obj, dict) or set(obj) != {"found", *fields}:
        raise ValueError("Unexpected location fields")
    if type(obj["found"]) is not bool:
        raise ValueError("found must be boolean")
    values = [obj[key] for key in fields]
    if not obj["found"]:
        valid = (all(type(value) is int and value == 0 for value in values) if abstention_zero
                 else all(value is None for value in values))
        if not valid:
            raise ValueError("Abstention coordinates do not match the declared protocol")
        return None
    if any(type(value) is not int for value in values):
        raise ValueError("Coordinates must be integers")
    w, h = size
    if w <= 0 or h <= 0:
        raise ValueError("Invalid image size")
    limits = [w - 1, h - 1] if protocol == "pixels" else [1000] * len(fields)
    if any(not 0 <= value <= limit for value, limit in zip(values, limits, strict=True)):
        raise ValueError("Coordinates outside declared range")
    if protocol == "bbox":
        left, top, right, bottom = values
        if left >= right or top >= bottom:
            raise ValueError("Bounding box must have positive area")
        x, y = (left + right) / 2, (top + bottom) / 2
    else:
        x, y = values
    if protocol != "pixels":
        x, y = min(w - 1, x * w / 1000), min(h - 1, y * h / 1000)
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
