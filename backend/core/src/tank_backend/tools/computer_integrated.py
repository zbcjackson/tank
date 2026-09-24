"""M5 integrated planner tools with independent protocol and restoration factors."""

from __future__ import annotations

import json
import uuid
from dataclasses import replace
from typing import Any

from ..agents.definition import GroundingConfig
from ..core.content import ImageBlock, TextBlock
from .base import ToolInfo, ToolParameter, ToolResult
from .computer_locate import LocatedTarget, LocateSession, LocateTool
from .computer_use_common import normalize_point
from .computer_use_macos import ClickTool

POINTER_TOOLS = {"click", "mouse_move", "scroll", "drag"}


def _int_from_numeric_string(value: Any) -> Any:
    """Read a string-typed integer, or pass the value through unchanged."""
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip("+-").isdigit():
            return int(text)
    return value


def _tolerant_location(raw: Any) -> Any:
    """Accept string-typed coordinates, as the legacy location branch already does.

    Recorded single-frame answers all typed coordinates as strings ("x": "539"),
    which the adapted decoders reject outright; correct points were discarded and
    the model had to answer again. Integrated mode is never strict, so read them
    here instead of loosening the decoders used by the strict split/static tracks.
    """
    if not isinstance(raw, dict):
        return raw
    fixed = dict(raw)
    for key in ("x", "y"):
        if key in fixed:
            fixed[key] = _int_from_numeric_string(fixed[key])
    box = fixed.get("bbox")
    if isinstance(box, list):
        fixed["bbox"] = [_int_from_numeric_string(value) for value in box]
    return fixed


def integrated_prompt(config: GroundingConfig) -> str:
    space = "CURRENT IMAGE" if config.host_restore else "FULL MAIN DISPLAY"
    units = "zero-based pixels" if config.protocol == "pixels" else "0..1000 normalized coordinates"
    sentinel = "0" if config.nullable_style == "integer" else "null"
    restoration = (
        "The host restores crop/zoom to the display."
        if config.host_restore
        else "For a cropped image, restore crop/zoom to full-display coordinates yourself using "
        "the returned crop, image_size and screen_size."
    )
    protocol = (
        "Use legacy x/y or bbox coordinates inside location."
        if config.protocol == "legacy"
        else f"Use the advertised {config.protocol} location schema. "
        + (
            "Set status=found only for a unique target; otherwise use not_found/ambiguous."
            if config.status_field
            else "Set found=true only for a unique target, otherwise false."
        )
        + f" On abstention all coordinates must be {sentinel}."
    )
    return f"""Desktop planning and grounding use one model in this run.
This contract replaces earlier coordinate and tool-call-format instructions;
all other task requirements remain applicable. No locate tool is available.
Observe with screenshot, then pass its frame_id and location to pointer tools.
computer_batch accepts only actions; omit the earlier screenshot option.
It returns the final observation automatically. Each pointer action uses the
same frame_id/location fields as its standalone tool, plus action for the tool name.
screenshot creates a new frame; omit frame_id. Its optional region contains four
integers in 0..1000. actions and region must be JSON arrays, never JSON-encoded strings.
After a failed screenshot, observe successfully again before any pointer action.
Coordinates are {units} relative to the {space}. {protocol}
For drag, also provide end_location. Never invent a frame or location_id.
{restoration}
Use only the current frame and uniquely identified targets. Missing or ambiguous
means no action. Inspect the returned observation to verify the expected effect;
dispatched is not proof of success. Never replay a failed batch blindly.
"""


class IntegratedSession(LocateSession):
    """Reuse M4 lifetime, batch, cancellation and feedback without a locator call."""

    config: GroundingConfig

    def _reference(self, raw: Any, frame_id: str) -> str | None:
        observation = self.state.observation
        if observation is None or frame_id != observation.frame_id:
            raise ValueError("Missing or stale frame; observe again")
        size = observation.image_size if self.config.host_restore else observation.screen_size
        if self.config.protocol == "legacy":
            if not isinstance(raw, dict) or set(raw) - {"x", "y", "bbox"}:
                raise ValueError("Invalid legacy location")
            if "bbox" in raw:
                if (
                    set(raw) != {"bbox"}
                    or not isinstance(raw["bbox"], list)
                    or len(raw["bbox"]) != 4
                ):
                    raise ValueError("Pass either x/y or bbox")
                point = normalize_point(raw["bbox"], None, strict=True)
            else:
                point = normalize_point(raw.get("x"), raw.get("y"), strict=True)
            if point is None:
                raise ValueError("Invalid legacy coordinates")
            x, y = (
                min(axis - 1, value * axis / 1000) for value, axis in zip(point, size, strict=True)
            )
        else:
            location = self.adapter.parse(json.dumps(_tolerant_location(raw)), size)
            if location.point is None:
                self.locations.clear()
                return None
            x, y = location.point
        if not self.config.host_restore:
            # Coordinates already refer to the screen; remove the crop transform
            # before passing through the SAME frame validation and dispatch path.
            left, top, right, bottom = observation.crop
            x = (x - left) * observation.image_size[0] / (right - left)
            y = (y - top) * observation.image_size[1] / (bottom - top)
        observation.map_point(x, y)  # reject out-of-observation positions before any input
        ref = uuid.uuid4().hex
        self.locations[ref] = LocatedTarget(observation, (x, y))
        return ref

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        feedback: bool = True,
    ) -> ToolResult | str:
        if name in POINTER_TOOLS:
            arguments = dict(arguments)
            frame_id = arguments.pop("frame_id")
            window_id = arguments.pop("window_id", None)
            await self.screenshot.validate(self.session_id, frame_id, window_id)
            self.context.check("desktop")
            ref = self._reference(arguments.pop("location"), frame_id)
            end = (
                self._reference(arguments.pop("end_location"), frame_id) if name == "drag" else ref
            )
            if ref is None or end is None:
                self.locations.clear()
                return ToolResult(
                    content=json.dumps(
                        {"dispatch": "not_dispatched", "effect": "unknown", "reason": "abstained"}
                    ),
                    error=True,
                )
            arguments["location_id"] = ref
            if name == "drag":
                arguments["end_location_id"] = end
        result = await super().execute(name, arguments, feedback=feedback)
        if isinstance(result, ToolResult) and isinstance(result.content, list):
            result = replace(
                result,
                content=[
                    replace(block, detail=self.config.detail)
                    if isinstance(block, ImageBlock)
                    else replace(
                        block,
                        text=block.text.replace(
                            "Image coordinates (zero-based pixels). ",
                            "Observation geometry; follow the integrated coordinate contract. ",
                        ),
                    )
                    if isinstance(block, TextBlock)
                    else block
                    for block in result.content
                ],
            )
        return result


class IntegratedTool(LocateTool):
    session: IntegratedSession

    def get_info(self) -> ToolInfo:
        info = super().get_info()
        if self.name == "computer_batch":
            return info.model_copy(update={
                "description": "Execute 1..8 actions; automatically capture the final observation.",
                "parameters": [
                    p.model_copy(update={
                        "description": "JSON array of actions; pointer actions use frame_id and "
                        "location as in the corresponding tool schema",
                    })
                    for p in info.parameters
                ],
            })
        if self.name not in POINTER_TOOLS:
            return info.model_copy(update={
                "description": f"{self.name}: integrated mode; returns an observation.",
            })
        return info.model_copy(
            update={
                "description": f"{self.name}: use the current frame and a predicted location.",
                "parameters": [
                    *[
                        p
                        for p in info.parameters
                        if p.name not in {"location_id", "end_location_id"}
                    ],
                    ToolParameter(
                        name="frame_id", type="string", description="Current screenshot frame"
                    ),
                    ToolParameter(
                        name="location", type="object", description="Predicted target location"
                    ),
                    ToolParameter(
                        name="window_id",
                        type="integer",
                        required=False,
                        description="Bound window ID, if used by screenshot",
                    ),
                    *(
                        [
                            ToolParameter(
                                name="end_location", type="object", description="Drag destination"
                            )
                        ]
                        if self.name == "drag"
                        else []
                    ),
                ],
            }
        )

    def get_raw_schema(self) -> dict[str, Any]:
        schema = super().get_raw_schema()
        if self.name not in POINTER_TOOLS:
            return schema
        if self.session.config.protocol == "legacy":
            legacy = ClickTool().get_raw_schema()
            assert legacy is not None
            location_schema = {
                **legacy,
                "properties": {
                    k: v for k, v in legacy["properties"].items() if k in {"x", "y", "bbox"}
                },
            }
        else:
            location_schema = self.session.adapter.schema()
        schema["properties"]["location"] = location_schema
        if self.name == "drag":
            schema["properties"]["end_location"] = location_schema
        return schema
