"""Task-scoped split planning/grounding tools, using the M2 execution path."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from typing import Any

from ..agents.subagent import SubAgentContext, SubAgentStopped
from ..core.content import ImageBlock, TextBlock
from ..llm.llm import LLM
from .base import BaseTool, ToolContext, ToolInfo, ToolMetadata, ToolParameter, ToolResult
from .computer_frame import FrameState, FrameTool
from .computer_grounding import GroundingAdapter, GroundingResponseError, grounding_call_id
from .computer_native import join_on_cancel
from .computer_observation import Observation

SPLIT_PROMPT = """Desktop planning uses split grounding.
For this run, this tool contract replaces earlier coordinate and tool-call-format
instructions. All other task-specific instructions remain applicable.
Observe with screenshot, then call locate(frame_id, target, window_id if bound).
Describe the unique target in words. Never calculate or supply coordinates.
Use only returned location_id references for click, mouse_move, scroll or drag
(drag also requires end_location_id). Missing/ambiguous/error means no action;
clarify the target, observe again, or stop. At most two re-locations per action
step; at most one switch to the configured fallback per step. Re-observation
does not reset these limits. A dispatched action is not proof of success.
Inspect the returned screenshot and verify the expected effect. Report execution
failure separately from no visible effect. Never blindly replay a failed batch.
Use computer_batch only for short predictable sequences; each located target is
revalidated before input. Observe and locate again after page/menu changes.
Keyboard shortcuts and type_text remain available when advertised.
"""


@dataclass(frozen=True)
class LocatedTarget:
    observation: Observation
    point: tuple[float, float]


class LocateSession:
    """Owned by one Runner invocation, never stored on the shared ToolManager."""

    def __init__(
        self,
        tools: dict[str, BaseTool],
        llms: dict[str, LLM],
        adapter: GroundingAdapter | None,
        context: SubAgentContext,
        session_id: str,
    ) -> None:
        self.context, self.session_id = context, session_id
        self.llms, self.adapter = llms, adapter
        self.state = FrameState()
        self.tools = {
            name: FrameTool(
                tool.legacy if isinstance(tool, FrameTool) else tool,
                self.state,
                lambda: context.check("desktop"),
            )
            if name in {"screenshot", "click", "mouse_move", "scroll", "drag"}
            else tool
            for name, tool in tools.items()
            if name != "computer_batch"
        }
        screenshot = self.tools.get("screenshot")
        if not isinstance(screenshot, FrameTool):
            raise ValueError("Split grounding requires macOS screenshot tools")
        self.screenshot = screenshot
        self.locations: dict[str, LocatedTarget] = {}
        self.attempts = 0
        self.backend = "primary"
        self.switched = False
        self.failed_batches: set[str] = set()

    async def locate(
        self,
        frame_id: str,
        target: str,
        window_id: int | None = None,
        backend: str = "primary",
    ) -> ToolResult:
        evidence: dict[str, Any] = {
            "call_id": "locate:" + uuid.uuid4().hex, "frame_id": frame_id,
            "target": target, "backend": backend, "protocol": self._protocol_name(),
            "stage": "preflight",
        }
        self.context.observe("grounding_attempt", **evidence)
        try:
            result = await self._locate(frame_id, target, window_id, backend, evidence)
        except BaseException as exc:
            outcome = "error"
            reason = "stage_failed"
            if isinstance(exc, GroundingResponseError):
                reason = exc.reason
            elif isinstance(exc, asyncio.CancelledError):
                outcome, reason = "cancelled", "cancelled"
            elif isinstance(exc, SubAgentStopped):
                outcome, reason = "stopped", exc.reason
            self.context.observe("grounding_outcome", **evidence, outcome=outcome,
                                 reason=reason, error_type=type(exc).__name__)
            raise
        self.context.observe("grounding_outcome", **evidence,
                             outcome=evidence["reported_status"])
        return result

    def _protocol_name(self) -> str:
        return "ax" if self.adapter is None else self.adapter.protocol

    def _clear_locations(self) -> None:
        self.locations.clear()

    def _prepare_locate(self, target: object, backend: str) -> None:
        if not isinstance(target, str) or not target.strip():
            raise ValueError("target must be a nonempty description")
        if self.attempts >= 3:
            raise ValueError("Two re-locations exhausted; stop this step")
        if backend not in self.llms:
            raise ValueError("Grounding backend is not configured")
        if backend != self.backend:
            if self.switched:
                raise ValueError("Only one grounding backend switch is allowed per step")
            self.backend, self.switched = backend, True
        self.attempts += 1

    async def _locate(
        self, frame_id: str, target: str, window_id: int | None, backend: str,
        evidence: dict[str, Any],
    ) -> ToolResult:
        self.context.check()
        self._prepare_locate(target, backend)
        evidence.update(stage="observation_before")
        observation = await self.screenshot.validate(self.session_id, frame_id, window_id)
        png = self.state.png
        self.context.check()
        evidence.update(image_sha256=observation.image_sha256,
                        image_size=observation.image_size, model=self.llms[backend].model,
                        stage="request")
        call_id = evidence["call_id"]
        if self.adapter is None:
            raise ValueError("Split grounding requires an adapter")
        token = grounding_call_id.set(call_id)
        try:
            response = await self.adapter.request(self.llms[backend], observation, png, target)
        except BaseException:
            self._clear_locations()
            self.context.budget.record_unknown(call_id)
            raise
        finally:
            grounding_call_id.reset(token)
        evidence.update(stage="accounting", usage_known=response.usage is not None,
                        response_model=response.model, response_id=response.id,
                        finish_reason=response.choices[0].finish_reason
                        if len(response.choices) == 1 else None)
        if response.usage is None:
            self.context.budget.record_unknown(call_id)
        else:
            self.context.budget.record(
                call_id, response.usage.prompt_tokens, response.usage.completion_tokens
            )
        self.context.observe(
            "grounding_usage",
            call_id=call_id,
            frame_id=frame_id,
            backend=backend,
            model=response.model,
            total_tokens=self.context.budget.total_tokens,
            usage_known=response.usage is not None,
        )
        self.context.check()
        evidence["stage"] = "parse"
        location = self.adapter.parse_response(response, observation.image_size)
        evidence.update(stage="observation_after", reported_status=location.status,
                        point=location.point, box=location.box)
        await self.screenshot.validate(self.session_id, frame_id, window_id)
        evidence["stage"] = "postcheck"
        self.context.check()
        result: dict[str, Any] = {"status": location.status, "frame_id": frame_id}
        if location.point is not None:
            location_id = uuid.uuid4().hex
            self.locations[location_id] = LocatedTarget(observation, location.point)
            result["location_id"] = location_id
        else:
            self._clear_locations()
        evidence["stage"] = "resolved"
        return ToolResult(content=json.dumps(result))

    def target(self, location_id: str) -> LocatedTarget:
        target = self.locations.get(location_id)
        if target is None or target.observation is not self.state.observation:
            raise ValueError("Missing or stale location; observe and locate again")
        return target

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        feedback: bool = True,
    ) -> ToolResult | str:
        self.context.check("desktop")
        allowed = {p.name for p in LocateTool(self, name).get_info().parameters}
        if arguments.keys() - allowed:
            raise ValueError("Unknown split-mode arguments; coordinates are not accepted")
        if name == "computer_batch":
            return await self.batch(arguments["actions"])
        if name == "locate":
            return await self.locate(**arguments)
        ctx = ToolContext(session_id=self.session_id)
        tool = self.tools[name]
        if name == "screenshot":
            self._clear_locations()
            result = await tool.execute(coordinate_space="image", ctx=ctx, **arguments)
            self.observe_screenshot(result)
            return result
        if name in {"click", "mouse_move", "scroll", "drag"}:
            result = await self._dispatch_pointer(name, tool, arguments, ctx)
        else:
            # Legacy keyboard/launch tools use to_thread. Cancelling their await
            # cannot stop native input; join it before Runner releases the desktop.
            native = asyncio.create_task(tool.execute(**arguments))
            try:
                result = await asyncio.shield(native)
            except asyncio.CancelledError:
                try:
                    await join_on_cancel(native)
                finally:
                    raise
        failed = isinstance(result, ToolResult) and result.error
        self.context.observe("desktop_dispatch", name=name, succeeded=not failed,
                             in_batch=not feedback)
        self.context.check()
        if failed or name not in {"click", "mouse_move", "scroll", "drag"}:
            self._clear_locations()
            self.state.observation = None
        if not failed:
            self.attempts, self.backend, self.switched = 0, "primary", False
        detail = {
            "dispatch": "error" if failed else "dispatched",
            "effect": "unknown",
            "detail": result
            if isinstance(result, str)
            else result.display or (result.content if isinstance(result.content, str) else ""),
        }
        return (
            await self.feedback(detail, failed)
            if feedback
            else ToolResult(content=json.dumps(detail), error=failed)
        )

    def observe_screenshot(self, result: ToolResult | str) -> None:
        if isinstance(result, ToolResult):
            for block in result.to_blocks():
                if isinstance(block, ImageBlock):
                    self.context.observe("screenshot", data_url=block.source)

    async def _dispatch_pointer(
        self, name: str, tool: BaseTool, arguments: dict[str, Any], ctx: ToolContext,
    ) -> ToolResult | str:
        target = self.target(arguments.pop("location_id"))
        arguments.update(
            coordinate_space="image",
            frame_id=target.observation.frame_id,
            window_id=target.observation.window_id,
        )
        if name == "drag":
            end = self.target(arguments.pop("end_location_id"))
            arguments.update(
                x1=target.point[0], y1=target.point[1], x2=end.point[0], y2=end.point[1]
            )
        else:
            arguments.update(x=target.point[0], y=target.point[1])
        return await tool.execute(ctx=ctx, **arguments)

    async def feedback(self, detail: dict[str, Any], failed: bool) -> ToolResult:
        self.context.check()
        self._clear_locations()
        shot = await self.screenshot.execute(
            coordinate_space="image",
            ctx=ToolContext(session_id=self.session_id),
        )
        self.observe_screenshot(shot)
        return ToolResult(
            content=[
                TextBlock(text=json.dumps(detail)),
                *(shot.to_blocks() if isinstance(shot, ToolResult) else [TextBlock(text=shot)]),
            ],
            error=failed,
        )

    async def batch(self, actions: Any) -> ToolResult:
        if not isinstance(actions, list) or not 1 <= len(actions) <= 8:
            raise ValueError("Batch requires 1..8 actions")
        fingerprint = json.dumps(actions, sort_keys=True)
        if fingerprint in self.failed_batches:
            raise ValueError("Do not replay a failed batch; inspect the new observation")
        for action in actions:
            if (
                not isinstance(action, dict)
                or action.get("action") not in self.tools
                or action.get("action")
                not in {
                    "click",
                    "mouse_move",
                    "scroll",
                    "drag",
                    "type_text",
                    "key_press",
                    "hold_key",
                }
            ):
                raise ValueError("Unsupported split batch action")
        steps = []
        for index, action in enumerate(actions):
            name = action["action"]
            try:
                result = await self.execute(
                    name, {k: v for k, v in action.items() if k != "action"}, feedback=False
                )
            except (ValueError, KeyError, TypeError) as exc:
                result = ToolResult(content=str(exc), error=True)
            failed = isinstance(result, ToolResult) and result.error
            steps.append(
                {
                    "action": name,
                    "dispatch": "error" if failed else "dispatched",
                    "detail": result if isinstance(result, str) else result.content,
                }
            )
            if failed:
                self.failed_batches.add(fingerprint)
                return await self.feedback(
                    {"steps": steps, "effect": "unknown", "skipped": len(actions) - index - 1}, True
                )
        return await self.feedback({"steps": steps, "effect": "unknown", "skipped": 0}, False)


class LocateTool(BaseTool):
    """Schema wrapper: planning sees targets/references, never image coordinates."""

    def __init__(self, session: LocateSession, name: str) -> None:
        self.session, self.name = session, name

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(category="computer", requires_network=self.name == "locate")

    def get_info(self) -> ToolInfo:
        if self.name == "computer_batch":
            params = [
                ToolParameter(
                    name="actions",
                    type="array",
                    description="1..8 actions using location_id, never coordinates",
                )
            ]
        elif self.name == "locate":
            params = [
                ToolParameter(name=n, type=t, description=d, required=r)
                for n, t, d, r in [
                    ("frame_id", "string", "Current screenshot frame", True),
                    ("target", "string", "Unique target description, without coordinates", True),
                    ("window_id", "integer", "Window bound to screenshot, if any", False),
                    ("backend", "string", "primary (default) or configured fallback", False),
                ]
            ]
        else:
            tool = self.session.tools[self.name]
            info = (tool.legacy if isinstance(tool, FrameTool) else tool).get_info()
            params = [
                p
                for p in info.parameters
                if p.name
                not in {
                    "x",
                    "y",
                    "x1",
                    "y1",
                    "x2",
                    "y2",
                    "bbox",
                    "coordinate_space",
                    "frame_id",
                }
            ]
            if self.name == "screenshot":
                params.append(
                    ToolParameter(
                        name="window_id",
                        type="integer",
                        required=False,
                        description="Main-display window to bind",
                    )
                )
            elif self.name in {"click", "scroll", "mouse_move", "drag"}:
                params.append(
                    ToolParameter(
                        name="location_id",
                        type="string",
                        description="Host reference returned by locate",
                    )
                )
                if self.name == "drag":
                    params.append(
                        ToolParameter(
                            name="end_location_id",
                            type="string",
                            description="Located drag destination",
                        )
                    )
        return ToolInfo(
            name=self.name,
            description=(
                "Locate a target in the bound current frame; does not execute input."
                if self.name == "locate"
                else f"{self.name}: use located references; returns a new observation after input."
            ),
            parameters=params,
        )

    def get_raw_schema(self) -> dict[str, Any]:
        info = self.get_info()
        properties: dict[str, Any] = {
            p.name: {"type": p.type, "description": p.description} for p in info.parameters
        }
        if "region" in properties:
            properties["region"]["items"] = {"type": "integer"}
        if self.name == "computer_batch":
            choices = []
            for name in (
                "click",
                "mouse_move",
                "scroll",
                "drag",
                "type_text",
                "key_press",
                "hold_key",
            ):
                if name in self.session.tools:
                    schema = type(self)(self.session, name).get_raw_schema()
                    schema["properties"]["action"] = {"const": name}
                    schema["required"].append("action")
                    choices.append(schema)
            properties["actions"].update(items={"oneOf": choices}, minItems=1, maxItems=8)
        return {
            "type": "object",
            "properties": properties,
            "required": [p.name for p in info.parameters if p.required],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> ToolResult | str:
        allowed = {p.name for p in self.get_info().parameters}
        unknown = kwargs.keys() - allowed
        if unknown:
            return ToolResult(
                content=f"Unknown tool arguments: {', '.join(sorted(unknown))}", error=True
            )
        self.session.context.check("desktop")
        operation = asyncio.create_task(self.session.execute(self.name, kwargs))
        cancelled = asyncio.create_task(self.session.context.cancel.wait())
        try:
            async with asyncio.timeout_at(self.session.context.deadline):
                await asyncio.wait({operation, cancelled}, return_when=asyncio.FIRST_COMPLETED)
                self.session.context.check("desktop")
                return await operation
        except (ValueError, KeyError, TypeError) as exc:
            self.session.locations.clear()
            return ToolResult(content=f"{exc}; observe again or stop", error=True)
        finally:
            operation.cancel()
            cancelled.cancel()
            await asyncio.gather(operation, cancelled, return_exceptions=True)
