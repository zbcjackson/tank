"""SDK public callbacks and completions accounting, including compaction."""

from __future__ import annotations

import asyncio
import base64
import re
import time
import uuid
from typing import Any

from tank_backend.agents.base import AgentOutput, AgentOutputType
from tank_backend.agents.subagent import SubAgentContext, SubAgentStopped


class MeteredCompletions:
    def __init__(
        self,
        inner: Any,
        context: SubAgentContext,
        queue: asyncio.Queue[AgentOutput | None],
    ) -> None:
        self.inner, self.context, self.queue = inner, context, queue
        self.next_call_type = "compaction"

    async def create(self, messages: Any, *, model: str = "n2", **kwargs: Any) -> Any:
        kwargs.update(messages=messages, model=model)
        self.context.check("network")
        call_type, self.next_call_type = self.next_call_type, "compaction"
        call_id = uuid.uuid4().hex
        started = time.monotonic()
        self.context.observe(
            "api_start",
            call_id=call_id,
            model=kwargs.get("model"),
            retry_scope="logical_call",
            call_type=call_type,
        )
        try:
            response = await self.inner.create(**kwargs)
        except BaseException as exc:
            self.context.budget.record_unknown(call_id)
            self.context.observe(
                "api_end",
                call_id=call_id,
                elapsed_s=time.monotonic() - started,
                usage="unknown",
                error=type(exc).__name__,
            )
            raise
        data = response if isinstance(response, dict) else response.model_dump()
        usage = data.get("usage") or {}
        prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
        elapsed = time.monotonic() - started
        if (
            type(prompt) is not int
            or type(completion) is not int
            or prompt < 0
            or completion < 0
        ):
            self.context.budget.record_unknown(call_id)
            self.context.observe(
                "api_end", call_id=call_id, elapsed_s=elapsed, usage="unknown"
            )
            raise SubAgentStopped("budget", "response missing trustworthy usage")
        self.context.budget.record(call_id, prompt, completion)
        metadata = {
            "call_id": call_id,
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
            "elapsed_s": elapsed,
            "retry_scope": "logical_call",
            "streaming": False,
            "call_type": call_type,
        }
        self.context.observe("api_end", **metadata)
        await self.queue.put(AgentOutput(AgentOutputType.USAGE, metadata=metadata))
        self.context.check("network")
        return response


class Callbacks:
    def __init__(
        self, queue: asyncio.Queue[AgentOutput | None], context: SubAgentContext
    ) -> None:
        self.queue, self.context = queue, context
        self.completions: MeteredCompletions | None = None
        self.steps = 0
        self.primitives = 0
        self.model_turns = 0

    async def on_run_continue(self, *args: Any) -> bool:
        self.context.check()
        return True

    async def on_api_start(self, *args: Any) -> None:
        if self.completions is not None:
            self.completions.next_call_type = "actor"

    async def on_api_end(self, *args: Any) -> None:
        self.model_turns += 1

    async def on_text(self, item: dict[str, Any]) -> None:
        content = item.get("content", "")
        if isinstance(content, list):
            content = "".join(str(part.get("text", "")) for part in content)
        if item.get("reasoning"):
            await self.queue.put(
                AgentOutput(AgentOutputType.THOUGHT, str(item["reasoning"]))
            )
        if content:
            await self.queue.put(AgentOutput(AgentOutputType.TOKEN, str(content)))

    async def on_computer_call_start(self, item: dict[str, Any]) -> None:
        self.context.check()
        if self.context.max_steps is not None and self.steps >= self.context.max_steps:
            raise SubAgentStopped(
                "max_steps", "tool call limit reached before execution"
            )
        self.steps += 1
        count = len(item.get("_batch_actions") or [])
        metadata = {
            "name": item.get("name"),
            "tool_call_id": item.get("call_id"),
            "arguments": item.get("arguments"),
            "status": "executing",
            "primitives": count,
        }
        self.context.observe("tool_start", **metadata)
        await self.queue.put(
            AgentOutput(AgentOutputType.TOOL_EXECUTING, metadata=metadata)
        )

    async def on_computer_call_end(
        self, item: dict[str, Any], results: list[dict[str, Any]]
    ) -> None:
        # Images belong to the screenshot observer, not multi-megabyte UI
        # activity text. Keep the SDK trajectory untouched.
        texts = []
        for result in results:
            value = result.get("output", "")
            if isinstance(value, dict):
                value = (
                    value.get("result") or value.get("text") or "screenshot captured"
                )
            texts.append(str(value))
        text = "\n".join(texts)
        completed = (
            len(re.findall(r"^\[\d+:[^\]]+\]", text, re.MULTILINE))
            if item.get("name") == "computer_batch"
            else 0
        )
        self.primitives += completed
        metadata = {
            "name": item.get("name"),
            "tool_call_id": item.get("call_id"),
            "completed_primitives": completed,
            "status": "error"
            if (
                "[ERROR]" in text
                or text.startswith("ERROR")
                or "batch stopped at actions[" in text
                or "Failed to release held" in text
            )
            else "success",
        }
        self.context.observe("tool_end", **metadata)
        await self.queue.put(AgentOutput(AgentOutputType.TOOL_RESULT, text, metadata))

    async def on_screenshot(self, raw_base64: str, label: str) -> None:
        raw = base64.b64decode(raw_base64)
        mime = (
            "image/png"
            if raw.startswith(b"\x89PNG")
            else "image/webp"
            if raw[8:12] == b"WEBP"
            else "image/jpeg"
        )
        self.context.observe(
            "screenshot", data_url=f"data:{mime};base64,{raw_base64}", label=label
        )

    async def on_compaction(self, metadata: dict[str, Any]) -> None:
        self.context.observe("compaction", **metadata)
