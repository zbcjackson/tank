"""n2 owns the conversation; injected executor owns every host action."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from tank_backend.agents.base import Agent, AgentOutput, AgentOutputType, AgentState
from tank_backend.computer.executor import DesktopExecutor
from tank_backend.llm.profile import LLMProfile

from .protocol import TOOL_SET, image_part, key_name, tool_result


class N2Agent(Agent):
    def __init__(
        self, executor: DesktopExecutor, profile: LLMProfile,
        *, max_steps: int = 100, reasoning_effort: str = "medium",
        tool_set: str = TOOL_SET, client: Any = None,
    ) -> None:
        super().__init__("computer_use_n2")
        if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 1:
            raise ValueError("max_steps must be a positive integer")
        if reasoning_effort not in {"none", "low", "medium", "xhigh"}:
            raise ValueError("invalid reasoning_effort")
        if tool_set != TOOL_SET:
            raise ValueError(f"supported tool_set: {TOOL_SET}")
        self.executor = executor
        self.profile = profile
        self.max_steps = max_steps
        self.reasoning_effort = reasoning_effort
        self.tool_set = tool_set
        self._client = client
        self._known_files: set[str] = set()

    async def run(self, state: AgentState) -> AsyncIterator[AgentOutput]:
        client: Any = self._client or AsyncOpenAI(
            api_key=self.profile.api_key, base_url=self.profile.base_url,
            default_headers=self.profile.extra_headers, max_retries=0,
        )
        self._known_files.clear()
        try:
            # Task-specific instructions belong in the first user message.
            tasks = [m.get("content", "") for m in state.messages if m.get("role") == "user"]
            task = "\n".join(t if isinstance(t, str) else json.dumps(t) for t in tasks)
            shot = await self.executor.screenshot()
            history: list[dict[str, Any]] = [{"role": "user", "content": [
                {"type": "text", "text": task}, image_part(shot.png),
            ]}]
            for _ in range(self.max_steps):
                await asyncio.sleep(0)
                if len(json.dumps(history).encode()) > 9_500_000:
                    yield AgentOutput(AgentOutputType.TOKEN, "Stopped: n2 request size limit reached.")
                    break
                started = time.monotonic()
                response = await client.chat.completions.create(
                    model=self.profile.model, messages=history,
                    extra_body={"tool_set": self.tool_set,
                                "reasoning_effort": self.reasoning_effort},
                )
                usage = response.usage
                if usage is None:
                    raise RuntimeError("n2 response missing usage; cannot enforce token budget")
                yield AgentOutput(AgentOutputType.USAGE, metadata={
                    "total_tokens": usage.total_tokens,
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "elapsed_s": time.monotonic() - started,
                })
                message = response.choices[0].message
                history.append(message.model_dump(exclude_none=True))
                # Yield before actions, so runner can stop on the usage budget.
                yield AgentOutput(AgentOutputType.TOKEN, message.content or "")
                if not message.tool_calls:
                    break
                for call in message.tool_calls:
                    metadata = {"name": call.function.name, "tool_name": call.function.name,
                                "tool_call_id": call.id, "status": "executing",
                                "arguments": call.function.arguments}
                    yield AgentOutput(AgentOutputType.TOOL_EXECUTING, metadata=metadata)
                    try:
                        arguments = json.loads(call.function.arguments)
                        if not isinstance(arguments, dict):
                            raise ValueError("tool arguments must be an object")
                        text, png = await self.execute(call.function.name, arguments)
                    except Exception as error:
                        text, png = f"ERROR: {error}", None
                    history.append(tool_result(call.id, text, png))
                    yield AgentOutput(AgentOutputType.TOOL_RESULT, text,
                                      {**metadata, "status": "error" if text.startswith("ERROR:") else "success"})
            else:
                yield AgentOutput(AgentOutputType.TOKEN, "Stopped: n2 max_steps reached; task may be incomplete.")
            yield AgentOutput(AgentOutputType.DONE)
        finally:
            if self._client is None:
                await client.close()

    async def execute(self, name: str, args: dict[str, Any]) -> tuple[str, bytes | None]:
        if name == "computer_batch":
            return await self._batch(args["actions"])
        if name == "bash":
            if args.get("run_in_background"):
                raise ValueError("background shell execution is not supported")
            result = await self.executor.bash(args["command"],
                                             timeout_s=max(1, min(600, int(args.get("timeout", 120)))))
            # Relative file observations no longer identify the same file after cd.
            self._known_files.clear()
            return f"exit_code: {result.exit_code}\n{result.stdout}\n{result.stderr}", None
        path = args.get("file_path", "")
        if name == "read":
            content = await self.executor.read_file(path)
            self._known_files.add(path)
            offset, limit = int(args.get("offset", 1)), int(args.get("limit", 2000))
            if offset < 1 or limit < 1:
                raise ValueError("read offset/limit must be positive")
            lines = content.splitlines()[offset - 1:offset - 1 + limit]
            return "\n".join(f"{i:6}\t{line}" for i, line in enumerate(lines, offset)), None
        if name == "write":
            if len(args["content"]) > 256_000:
                raise ValueError("write content exceeds 256000 characters")
            await self.executor.write_file(path, args["content"])
            self._known_files.add(path)
            return "File written.", None
        if name == "edit":
            if path not in self._known_files:
                raise ValueError("read or write the file before editing")
            if args.get("replace_all"):
                raise ValueError("replace_all is not supported; use read and write")
            await self.executor.edit_file(path, args["old_string"], args["new_string"])
            return "File edited.", None
        raise ValueError(f"unknown n2 tool: {name}")

    async def _batch(self, actions: list[dict[str, Any]]) -> tuple[str, bytes]:
        if not isinstance(actions, list) or not 1 <= len(actions) <= 20:
            raise ValueError("batch must contain 1-20 actions")
        completed = 0
        failure = ""
        held = False
        try:
            for index, raw in enumerate(actions):
                try:
                    name, args = raw["name"], raw["arguments"]
                    modifier = args.get("modifier")
                    if modifier and modifier not in {"ctrl", "shift", "alt", "meta", "command", "super"}:
                        raise ValueError("invalid modifier")
                    try:
                        if modifier:
                            await self.executor.key_down(key_name(modifier))
                        if name in {"mouse_down", "mouse_up"}:
                            if "coordinates" in args:
                                await self.executor.mouse_move(*args["coordinates"])
                            if name == "mouse_down":
                                held = True
                            await getattr(self.executor, name)()
                            if name == "mouse_up":
                                held = False
                        elif name == "screenshot":
                            pass  # The batch returns exactly one final screenshot.
                        elif name == "key_press":
                            for key in args["key"].split():
                                await self.executor.key_press(key_name(key))
                        else:
                            converted = self._action(name, args)
                            result = await self.executor.batch([converted], screenshot_after=False)
                            if result.failed_at is not None:
                                raise ValueError(result.steps[-1].detail)
                    finally:
                        if modifier:
                            await self.executor.key_up(key_name(modifier))
                    completed += 1
                except Exception as error:
                    failure = f" Action {index} failed: {error}; skipped {len(actions)-index-1}."
                    break
        finally:
            if held:
                await self.executor.mouse_up()
        shot = await self.executor.screenshot()
        prefix = "ERROR: " if failure else ""
        return f"{prefix}Executed {completed} of {len(actions)} actions.{failure}", shot.png

    @staticmethod
    def _action(name: str, args: dict[str, Any]) -> dict[str, Any]:
        clicks = {"left_click": ("left", 1), "double_click": ("left", 2),
                  "triple_click": ("left", 3), "right_click": ("right", 1),
                  "middle_click": ("middle", 1)}
        if name in clicks:
            button, count = clicks[name]
            x, y = args["coordinates"]
            return {"action": "click", "x": x, "y": y, "button": button, "clicks": count}
        if name == "mouse_move":
            x, y = args["coordinates"]
            return {"action": name, "x": x, "y": y}
        if name == "drag":
            x1, y1 = args["start_coordinates"]
            x2, y2 = args["coordinates"]
            return {"action": name, "x1": x1, "y1": y1, "x2": x2, "y2": y2}
        if name == "scroll":
            direction, amount = args["direction"], int(args["amount"])
            if direction not in {"up", "down"} or not 1 <= amount <= 50:
                raise ValueError("invalid scroll direction/amount")
            x, y = args["coordinates"]
            return {"action": name, "amount": amount if direction == "up" else -amount,
                    "x": x, "y": y}
        if name == "type":
            return {"action": "type_text", "text": args["text"]}
        if name == "hold_key":
            return {"action": name, "keys": key_name(args["key"]),
                    "duration_s": args.get("duration", 1)}
        if name == "wait":
            return {"action": name, "delay_s": args.get("duration", 1)}
        raise ValueError(f"unknown batch action: {name}")
