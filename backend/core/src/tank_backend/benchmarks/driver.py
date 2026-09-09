"""Benchmark drivers: run a task against a measured seam.

Today one driver exists — ``SubAgentDriver`` drives a single sub-agent
(AgentRunner + agent definition + its toolset) directly in-process, which
is the right seam for "how good is this agent at these tasks". Future
drivers can measure other seams (supervisor dispatch, full voice stack)
without touching the suite/runner — see the benchmarks README.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from ..agents.approval import PendingToolCallStore
from ..agents.base import AgentOutputType
from ..agents.definition import AgentDefinition, load_agent_definitions
from ..agents.runner import AgentRunner
from ..config.app_config import AppConfig, find_config_yaml
from ..core.content import ImageBlock
from ..core.events import UpdateType
from ..llm.llm import LLM
from ..pipeline.bus import Bus
from ..policy.verdict import AlwaysApproveResolver
from ..tools.base import BaseTool, ToolInfo, ToolMetadata, ToolResult
from ..tools.manager import ToolManager
from .trace import TraceSink

if TYPE_CHECKING:
    from ..llm.profile import LLMProfile

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DriverResult:
    final_text: str
    steps: int
    wall_s: float
    tokens: int
    screenshots: int
    timed_out: bool
    error: str | None = None


class BenchmarkDriver(Protocol):
    """Anything that can attempt a task instruction once."""

    async def run(
        self, instruction: str, trace: TraceSink, *, timeout_s: int, max_steps: int,
    ) -> DriverResult:
        ...


class CountingLLM:
    """Transparent LLM wrapper that accumulates token usage per run.

    AgentRunner consumes USAGE outputs internally (budget enforcement)
    without forwarding them, so token totals are captured here at the
    transport seam instead. ``run_agent`` only uses ``self._llm`` when
    ``app_config`` is None — SubAgentDriver relies on exactly that.
    """

    def __init__(self, inner: LLM) -> None:
        self._inner = inner
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def reset(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def chat_stream(
        self, *args: Any, **kwargs: Any
    ) -> AsyncIterator[tuple[UpdateType, str, dict[str, Any]]]:
        async for update in self._inner.chat_stream(*args, **kwargs):
            if update[0] == UpdateType.USAGE:
                meta = update[2]
                self.prompt_tokens += int(meta.get("prompt_tokens", 0))
                self.completion_tokens += int(meta.get("completion_tokens", 0))
            yield update


class TracedScreenshotTool(BaseTool):
    """Wrap the screenshot tool so each capture is archived per-trial.

    Tool results carry images as content blocks that never surface in
    AgentOutput, so the trace hook lives on the tool itself.
    """

    def __init__(self, inner: BaseTool, trace_getter: Any) -> None:
        self._inner = inner
        self._trace_getter = trace_getter  # callable -> TraceSink | None

    def get_info(self) -> ToolInfo:
        return self._inner.get_info()

    def get_metadata(self) -> ToolMetadata:
        return self._inner.get_metadata()

    def get_raw_schema(self) -> Any:
        return self._inner.get_raw_schema()

    async def execute(self, **kwargs: Any) -> ToolResult | str:
        result = await self._inner.execute(**kwargs)
        trace = self._trace_getter()
        if trace is not None and isinstance(result, ToolResult):
            content = result.content
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, ImageBlock) and block.source.startswith("data:"):
                        trace.save_screenshot(block.source)
        return result


class SubAgentDriver:
    """Drive one sub-agent definition in-process (no pipeline, no WS).

    The benchmark measures the agent loop itself — definition prompt ×
    model profile × toolset quality. Supervisor scheduling, approvals
    UI, persistence, and the voice stack are deliberately outside: they
    are constants across the A/B comparisons this suite exists for.
    """

    def __init__(
        self,
        runner: AgentRunner,
        agent_def: AgentDefinition,
        llm: CountingLLM,
        tool_manager: ToolManager,
    ) -> None:
        self._runner = runner
        self._agent_def = agent_def
        self._llm = llm
        self._tool_manager = tool_manager
        self._trace: TraceSink | None = None

    @classmethod
    def create(
        cls, agent_name: str, config_path: Path | None = None
    ) -> SubAgentDriver:
        """Assemble the stack from repo config (config.yaml + agents/*.md)."""
        from dotenv import load_dotenv

        cfg_path = config_path or find_config_yaml()
        # Same bootstrap the API server does: .env next to config.yaml
        # provides ${LLM_API_KEY} etc. before any config loading.
        load_dotenv(cfg_path.parent / ".env")
        app_config = AppConfig.load(cfg_path)

        agent_dirs = [
            (Path(d).expanduser() if Path(d).is_absolute() else (cfg_path.parent / d))
            .resolve()
            for d in app_config.agents.dirs
        ]
        definitions = load_agent_definitions(agent_dirs)
        agent_def = definitions.get(agent_name)
        if agent_def is None:
            raise ValueError(
                f"agent definition '{agent_name}' not found in {agent_dirs}"
            )

        profile_name = agent_def.model or app_config.agents.llm_profile
        profile: LLMProfile = app_config.get_llm_profile(profile_name)
        from ..llm.profile import create_llm_from_profile

        llm = CountingLLM(create_llm_from_profile(profile))

        bus = Bus()
        tool_manager = ToolManager(app_config, bus=bus)

        driver = cls.__new__(cls)
        driver._runner = AgentRunner(
            llm=cast(LLM, llm),
            tool_manager=tool_manager,
            bus=bus,
            approval_policy=tool_manager.approval_policy,
            pending_store=PendingToolCallStore(),
            definitions=definitions,
            toolsets_config=app_config.toolsets,
            app_config=None,  # force the counting LLM path in run_agent
            resolver=AlwaysApproveResolver(),  # benchmarks are autonomous
        )
        driver._agent_def = agent_def
        driver._llm = llm
        driver._tool_manager = tool_manager
        driver._trace = None

        # Archive every screenshot the agent takes for offline diagnosis.
        if "screenshot" in tool_manager.tools:
            tool_manager.tools["screenshot"] = TracedScreenshotTool(
                tool_manager.tools["screenshot"], lambda: driver._trace
            )
        return driver

    async def run(
        self, instruction: str, trace: TraceSink, *, timeout_s: int, max_steps: int,
    ) -> DriverResult:
        self._trace = trace
        self._llm.reset()
        messages: list[dict[str, Any]] = [{"role": "user", "content": instruction}]
        steps = 0
        token_parts: list[str] = []
        stopped_reason: str | None = None

        async def consume() -> None:
            nonlocal steps, stopped_reason
            async for output in self._runner.run_agent(self._agent_def, messages):
                if output.type == AgentOutputType.TOOL_CALLING:
                    steps += 1
                elif output.type == AgentOutputType.TOKEN and output.content:
                    token_parts.append(output.content)
                if output.type != AgentOutputType.USAGE:
                    trace.output(output)
                if steps > max_steps:
                    stopped_reason = f"max_steps({max_steps}) exceeded"
                    break

        timed_out = False
        start = time.monotonic()
        try:
            await asyncio.wait_for(consume(), timeout=timeout_s)
        except TimeoutError:
            timed_out = True
            stopped_reason = f"timeout({timeout_s}s)"

        wall_s = time.monotonic() - start
        trace.event(
            "driver_done",
            steps=steps,
            tokens=self._llm.total_tokens,
            wall_s=wall_s,
            timed_out=timed_out,
            stopped_reason=stopped_reason,
        )
        self._trace = None
        return DriverResult(
            final_text="".join(token_parts),
            steps=min(steps, max_steps + 1),
            wall_s=wall_s,
            tokens=self._llm.total_tokens,
            screenshots=trace.screenshot_count,
            timed_out=timed_out,
            error=stopped_reason,
        )
