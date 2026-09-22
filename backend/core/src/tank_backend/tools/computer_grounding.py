"""Computer-use location protocols shared by production calls and offline probes.

Provider/model parameters belong to LLMProfile. This module never dispatches input
or converts an uploaded-image position to desktop coordinates.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Literal

from openai.types.chat import ChatCompletion
from PIL import Image, UnidentifiedImageError

from ..llm.llm import LLM
from .computer_observation import Observation

grounding_call_id: ContextVar[str | None] = ContextVar("grounding_call_id", default=None)


class GroundingResponseError(ValueError):
    """Stable rejection code without changing the existing ValueError contract."""

    def __init__(self, reason: str, detail: str) -> None:
        self.reason = reason
        super().__init__(detail)


@dataclass(frozen=True)
class ImageLocation:
    status: Literal["found", "not_found", "ambiguous"]
    point: tuple[float, float] | None = None
    box: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class GroundingAdapter:
    protocol: str = "point"
    nullable_style: str = "integer"
    strict: bool = False
    detail: str = "auto"
    status_field: bool = False

    def __post_init__(self) -> None:
        if self.protocol not in ("point", "pixels", "bbox"):
            raise ValueError("Unknown coordinate protocol")
        if self.nullable_style not in ("integer", "type-array", "anyof"):
            raise ValueError("Unknown nullable schema style")
        if self.detail not in ("auto", "low", "high", "original"):
            raise ValueError("Unknown image detail")
        if type(self.strict) is not bool or type(self.status_field) is not bool:
            raise ValueError("strict/status_field must be booleans")

    def build_request(
        self, png: bytes, size: tuple[int, int], target: str, *,
        previous: bytes | None = None,
        system: str = "Locate the requested UI element in the current image.",
        marked: bool = False,
    ) -> dict[str, Any]:
        _validate_size(size)
        return _location_payload(
            png, size, target, self.protocol, strict=self.strict, previous=previous,
            system=system, marked=marked, detail=self.detail, nullable_style=self.nullable_style,
            status_field=self.status_field,
        )

    def schema(self, size: tuple[int, int] | None = None) -> dict[str, Any]:
        """Location fields; pixel bounds are runtime-only before the first frame."""
        if size is not None:
            _validate_size(size)
        return _location_schema(self.protocol, size, self.nullable_style, self.status_field)

    def parse(self, raw: str, size: tuple[int, int]) -> ImageLocation:
        _validate_size(size)
        return _parse_location(
            raw, self.protocol, size, abstention_zero=self.nullable_style == "integer",
            status_field=self.status_field,
        )

    def parse_response(self, response: ChatCompletion, size: tuple[int, int]) -> ImageLocation:
        if len(response.choices) != 1:
            raise GroundingResponseError("invalid_response", "Expected one location response")
        choice = response.choices[0]
        if choice.finish_reason not in {"tool_calls", "stop"}:
            raise GroundingResponseError(
                "incomplete_response", f"Incomplete location response: {choice.finish_reason}")
        if choice.message.refusal:
            raise GroundingResponseError("refused_response", "Location response was refused")
        calls = choice.message.tool_calls or []
        if len(calls) != 1 or calls[0].type != "function" or calls[0].function.name != "click":
            raise GroundingResponseError(
                "invalid_tool_call", "Expected exactly one click function call")
        try:
            return self.parse(calls[0].function.arguments, size)
        except ValueError as exc:
            raise GroundingResponseError("invalid_location", str(exc)) from exc

    async def request(
        self, llm: LLM, observation: Observation, png: bytes, target: str,
    ) -> ChatCompletion:
        # Return the full response before parsing so callers can retain usage on
        # invalid/truncated results. No tool executor, nested agent or retry loop.
        if hashlib.sha256(png).hexdigest() != observation.image_sha256:
            raise ValueError("Grounding image does not match the bound observation")
        try:
            with Image.open(io.BytesIO(png)) as image:
                if image.format != "PNG" or image.size != observation.image_size:
                    raise ValueError("Grounding image format/size differs from the observation")
                image.verify()
        except (UnidentifiedImageError, OSError, SyntaxError) as exc:
            raise ValueError("Grounding image must be a valid PNG") from exc
        payload = self.build_request(png, observation.image_size, target)
        return await llm.complete_response(**payload, retry=False)


def _validate_size(size: tuple[int, int]) -> None:
    if len(size) != 2 or any(type(axis) is not int or axis <= 0 for axis in size):
        raise ValueError("Invalid image size")


def _location_schema(
    protocol: str, size: tuple[int, int] | None, nullable_style: str, status_field: bool,
) -> dict[str, Any]:
    fields = ("left", "top", "right", "bottom") if protocol == "bbox" else ("x", "y")
    limits = ((size[0] - 1, size[1] - 1) if size is not None else (None, None)) \
        if protocol == "pixels" else (1000,) * len(fields)
    outcome = "status" if status_field else "found"
    properties: dict[str, Any] = {outcome: (
        {"type": "string", "enum": ["found", "not_found", "ambiguous"]} if status_field
        else {"type": "boolean"}
    )}
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
    for value in properties.values():
        if value.get("maximum", 0) is None:
            value.pop("maximum")
        for branch in value.get("anyOf", []):
            if branch.get("maximum", 0) is None:
                branch.pop("maximum")
    return {"type": "object", "properties": properties,
            "required": [outcome, *fields], "additionalProperties": False}

def _location_payload(
    png: bytes, size: tuple[int, int], target: str,
    protocol: str, *, strict: bool = False, previous: bytes | None = None,
    system: str = "Locate the requested UI element in the current image.",
    marked: bool = False, detail: str = "auto",
    nullable_style: str = "type-array", status_field: bool = False,
) -> dict[str, Any]:
    """Build image messages and a location schema, independent of the provider."""
    function: dict[str, Any] = {
        "name": "click", "description": "Report one target location; no action is executed.",
        "parameters": _location_schema(protocol, size, nullable_style, status_field),
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
        "Use only the CURRENT image, not previous positions. "
        "Set found=true only for exactly one unambiguous matching target. "
        "If multiple targets match, or the target is absent or uncertain, "
        "set found=false and ALL coordinates="
        + ("0." if nullable_style == "integer" else "null.")
    )
    if status_field:
        question = (
            f"CURRENT image: {size[0]}x{size[1]}. Locate this target: {target}. "
            + f"Call click once with its {what} in {units}. "
            "The origin is the top-left of THIS input image; each axis spans the full image. "
            "Use only the CURRENT image. Set status=found for one unambiguous target, "
            "status=not_found when absent, or status=ambiguous when uncertain or multiple "
            "targets match. For not_found/ambiguous set ALL coordinates="
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
    return {"messages": messages, "tools": [{"type": "function", "function": function}]}


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate field: {key}")
        result[key] = value
    return result


def _parse_location(
    raw: str, protocol: str, size: tuple[int, int],
    *, abstention_zero: bool = False, status_field: bool = False,
) -> ImageLocation:
    """Strictly decode model coordinates into the uploaded image, never OS space."""
    fields = ("left", "top", "right", "bottom") if protocol == "bbox" else ("x", "y")
    obj = json.loads(raw, object_pairs_hook=_unique_object)
    outcome = "status" if status_field else "found"
    if not isinstance(obj, dict) or set(obj) != {outcome, *fields}:
        raise ValueError("Unexpected location fields")
    if status_field:
        status = obj["status"]
        if status not in ("found", "not_found", "ambiguous"):
            raise ValueError("Invalid location status")
    else:
        if type(obj["found"]) is not bool:
            raise ValueError("found must be boolean")
        # Legacy false combines absence and uncertainty; never claim proven absence.
        status = "found" if obj["found"] else "ambiguous"
    values = [obj[key] for key in fields]
    if status != "found":
        valid = (all(type(value) is int and value == 0 for value in values) if abstention_zero
                 else all(value is None for value in values))
        if not valid:
            raise ValueError("Abstention coordinates do not match the declared protocol")
        return ImageLocation(status="not_found" if status == "not_found" else "ambiguous")
    if any(type(value) is not int for value in values):
        raise ValueError("Coordinates must be integers")
    w, h = size
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
    box = None
    if protocol == "bbox":
        box = (values[0] * w / 1000, values[1] * h / 1000,
               values[2] * w / 1000, values[3] * h / 1000)
    return ImageLocation(status="found", point=(x, y), box=box)
