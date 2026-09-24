"""Benchmark drivers: run a task against a measured seam.

Today one driver exists — ``SubAgentDriver`` drives a single sub-agent
(AgentRunner + agent definition + its toolset) directly in-process, which
is the right seam for "how good is this agent at these tasks". Future
drivers can measure other seams (supervisor dispatch, full voice stack)
without touching the suite/runner — see the benchmarks README.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import re
import sys
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from statistics import median
from typing import TYPE_CHECKING, Any, Protocol, cast

import httpx
from openai.types.chat import ChatCompletion

from ..agents.approval import PendingToolCallStore
from ..agents.base import Agent, AgentOutput, AgentOutputType, AgentState
from ..agents.definition import AgentDefinition, load_agent_definitions
from ..agents.runner import AgentRunner
from ..agents.subagent import (
    SubAgent,
    SubAgentAuthorization,
    SubAgentCleanupError,
    SubAgentStopped,
)
from ..config.app_config import AppConfig, find_config_yaml
from ..core.content import ImageBlock
from ..core.events import UpdateType
from ..llm.llm import LLM
from ..pipeline.bus import Bus
from ..plugin.registry import ExtensionRegistry
from ..policy.verdict import AlwaysApproveResolver
from ..tools.base import BaseTool, ToolInfo, ToolMetadata, ToolResult
from ..tools.computer_grounding import grounding_call_id
from ..tools.computer_use_common import BATCH_ACTIONS
from ..tools.manager import ToolManager
from .comparison_contract import ComparisonContract
from .desktop_cleanup import MacOSInputCleanup
from .request_budget import (
    RequestBudget,
    RequestLimitExceeded,
    RequestLimits,
    active_request_budget,
)
from .spend_http import SpendControl, active_spend_session
from .spend_ledger import SpendLimitExceeded
from .trace import TraceSink

if TYPE_CHECKING:
    from ..llm.profile import LLMProfile

logger = logging.getLogger(__name__)
GUI_TOOLS = BATCH_ACTIONS | {"screenshot", "launch_app", "computer_batch", "locate"}


@dataclass(frozen=True)
class DriverResult:
    final_text: str
    steps: int
    wall_s: float
    tokens: int
    screenshots: int
    timed_out: bool
    error: str | None = None
    # LLM latency (trial level): API call (model round-trip) count,
    # median time-to-first-token, median per-call total, and total
    # seconds spent in LLM calls.
    llm_calls: int = 0
    llm_ttft_s: float | None = None
    llm_call_s: float = 0.0
    llm_total_s: float = 0.0
    llm_rtt_s: float = 0.0
    stop_reason: str | None = None
    cleanup: str = "unknown"
    primitives: int = 0
    model_turns: int = 0
    unknown_calls: int = 0
    non_gui_tools: tuple[str, ...] = ()


class BenchmarkDriver(Protocol):
    """Anything that can attempt a task instruction once."""

    async def run(
        self, instruction: str, trace: TraceSink, *, timeout_s: int, max_steps: int,
    ) -> DriverResult:
        ...


class CountingLLM:
    """Transparent LLM wrapper that accumulates token usage and API latency.

    AgentRunner consumes USAGE outputs internally (budget enforcement)
    without forwarding them, so token totals are captured here at the
    transport seam instead. Profile-created clients share the same counter
    through the Runner factory; non-streaming locator calls are measured too.

    Timing unit = one model round-trip (API call), not one chat_stream:
    ``LLM.chat_stream`` runs the whole tool loop internally, so a single
    call spans N model round-trips delimited by USAGE updates. Each
    round-trip is timed from the previous boundary to its USAGE update;
    a stream cancelled mid-round (task timeout) still records the
    in-flight round so timeout trials retain elapsed time. Nested locator time
    is excluded from planner intervals; other local tool overhead may remain.
    """

    def __init__(self, inner: LLM, counter: CountingLLM | None = None) -> None:
        self._inner = inner
        self._counter = counter if counter is not None else self
        self.nonstream_s = 0.0
        self.unknown_calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        # (ttft_s, total_s) per model round-trip, in order.
        self.call_stats: list[tuple[float | None, float]] = []
        # Optional per-call hook (index, ttft_s, total_s) — the driver
        # wires this to TraceSink so latency lands in trace.jsonl.
        self.on_call: Callable[[int, float | None, float], None] | None = None

    def reset(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.call_stats = []
        self.nonstream_s = 0.0
        self.unknown_calls = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def _record(self, ttft: float | None, total: float) -> None:
        self.call_stats.append((ttft, total))
        logger.info(
            "LLM call %d: ttft=%s total=%.2fs", len(self.call_stats), ttft, total
        )
        if self.on_call is not None:
            self.on_call(len(self.call_stats), ttft, total)

    @staticmethod
    def _is_model_output(update: tuple[UpdateType, str, dict[str, Any]]) -> bool:
        """True for model-generated updates (skips local tool echoes).

        TOOL "calling" deltas are streamed model output; "success"/
        "error" results and TOOL_EXECUTING come from the local executor
        microseconds after the round boundary — counting those as ttft
        reports 0.0 for every round.
        """
        kind, _, metadata = update
        return kind in (UpdateType.TEXT, UpdateType.THOUGHT) or (
            kind == UpdateType.TOOL and metadata.get("status") == "calling"
        )

    async def chat_stream(
        self, *args: Any, **kwargs: Any
    ) -> AsyncIterator[tuple[UpdateType, str, dict[str, Any]]]:
        counter = self._counter
        round_start = time.monotonic()
        nested_start = counter.nonstream_s
        ttft: float | None = None
        try:
            async for update in self._inner.chat_stream(*args, **kwargs):
                if ttft is None and self._is_model_output(update):
                    ttft = max(
                        0.0, time.monotonic() - round_start - counter.nonstream_s + nested_start,
                    )
                if update[0] == UpdateType.USAGE:
                    meta = update[2]
                    counter.prompt_tokens += int(meta.get("prompt_tokens", 0))
                    counter.completion_tokens += int(meta.get("completion_tokens", 0))
                    counter._record(ttft or 0.0, max(
                        0.0, time.monotonic() - round_start - counter.nonstream_s + nested_start,
                    ))
                    round_start = time.monotonic()
                    nested_start = counter.nonstream_s
                    ttft = None
                yield update
        except BaseException:
            # Cancellation (task timeout / max-steps abort) or a stream
            # error: the in-flight round still consumed wall time.
            if ttft is not None or time.monotonic() - round_start > 0.01:
                counter._record(ttft or 0.0, max(
                    0.0, time.monotonic() - round_start - counter.nonstream_s + nested_start,
                ))
            raise

    async def complete_response(self, *args: Any, **kwargs: Any) -> ChatCompletion:
        """Measure a locator response, including failures and missing usage."""
        counter = self._counter
        start = time.monotonic()
        response = None
        try:
            response = await self._inner.complete_response(*args, **kwargs)
            return response
        finally:
            elapsed = time.monotonic() - start
            counter.nonstream_s += elapsed
            if response is None or response.usage is None:
                counter.unknown_calls += 1
            else:
                counter.prompt_tokens += response.usage.prompt_tokens
                counter.completion_tokens += response.usage.completion_tokens
            counter._record(None, elapsed)


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


def disable_langfuse_tracing() -> list[str]:
    """Drop LANGFUSE_* env vars so benchmark runs stay hermetic.

    Tracing is an async side channel (never affects tool execution or
    verdicts), but a benchmark process shouldn't spray spans at a Langfuse
    server that may not be running — the retry noise only obscures real
    output. Returns the names removed.
    """
    import os

    removed = [
        name for name in list(os.environ)
        if name.startswith("LANGFUSE_")
    ]
    for name in removed:
        os.environ.pop(name, None)
    return removed


class RepinImeAfterLaunchTool(BaseTool):
    """Wrap launch_app so the ASCII input source is re-pinned after launch.

    macOS remembers the last input source PER APP — focusing a freshly
    launched app can flip the keyboard back to a Chinese IME even though
    we pinned before the trial. The pin must target the now-frontmost
    app, hence the short settle delay after ``open`` returns.
    """

    def __init__(self, inner: BaseTool) -> None:
        self._inner = inner

    def get_info(self) -> ToolInfo:
        return self._inner.get_info()

    def get_metadata(self) -> ToolMetadata:
        return self._inner.get_metadata()

    def get_raw_schema(self) -> Any:
        return self._inner.get_raw_schema()

    async def execute(self, **kwargs: Any) -> ToolResult | str:
        result = await self._inner.execute(**kwargs)
        from .ime import _REPIN_AFTER_LAUNCH_S, pin_ascii_input_source

        await asyncio.sleep(_REPIN_AFTER_LAUNCH_S)
        if isinstance(result, ToolResult) and not result.error:
            pin_ascii_input_source()
        return result


class _MeasuredEngine(Agent):
    """Record engine usage without involving the shared LLM transport."""

    def __init__(self, inner: Agent, llm: CountingLLM) -> None:
        super().__init__(inner.name)
        self.inner = inner
        self.llm = llm

    async def run(self, state: AgentState) -> AsyncIterator[AgentOutput]:
        outputs = self.inner.run(state)
        try:
            async for output in outputs:
                if output.type == AgentOutputType.USAGE:
                    self.llm.prompt_tokens += int(output.metadata.get("prompt_tokens", 0))
                    self.llm.completion_tokens += int(output.metadata.get("completion_tokens", 0))
                    elapsed = float(output.metadata.get("elapsed_s", 0))
                    self.llm._record(0.0, elapsed)  # Non-streaming engine: no streamed TTFT.
                yield output
        finally:
            close = getattr(outputs, "aclose", None)
            if close is not None:
                await close()


class _MeasuredRegistry(ExtensionRegistry):
    def __init__(self, llm: CountingLLM, trace: Callable[[], TraceSink | None]) -> None:
        super().__init__()
        self.llm = llm
        self.trace = trace

    def instantiate(self, full_name: str, config: dict) -> object:
        executor = config.get("desktop_executor")
        if executor is not None:
            capture = executor.screenshot

            async def screenshot(region: Any = None) -> Any:
                shot = await capture(region)
                trace = self.trace()
                if trace is not None:
                    encoded = base64.b64encode(shot.png).decode("ascii")
                    trace.save_screenshot(f"data:image/png;base64,{encoded}")
                return shot

            executor.screenshot = screenshot
        inner = super().instantiate(full_name, config)
        if isinstance(inner, SubAgent):
            return inner
        if not isinstance(inner, Agent):
            raise TypeError("benchmark extension must implement Agent or SubAgent")
        return _MeasuredEngine(inner, self.llm)


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
        *, input_cleanup: bool = False,
    ) -> None:
        if input_cleanup and (agent_def.engine or agent_def.extension):
            raise ValueError("Input cleanup requires a built-in benchmark agent")
        self._input_cleanup = MacOSInputCleanup() if input_cleanup else None
        self._runner = runner
        self._agent_def = agent_def
        self._llm = llm
        self._tool_manager = tool_manager
        self._trace: TraceSink | None = None
        self._runtime_metadata: dict[str, Any] = {"input_cleanup": input_cleanup}
        self._request_limits: RequestLimits | None = None
        self._request_budget: RequestBudget | None = None
        self._spend: SpendControl | None = None

    @classmethod
    def create(
        cls, agent_name: str, config_path: Path | None = None, *,
        request_limits: RequestLimits | None = None,
        spend: SpendControl | None = None,
        comparison: ComparisonContract | None = None,
        input_cleanup: bool = False,
        enforce_agent_budget: bool = False,
    ) -> SubAgentDriver:
        """Assemble the stack from repo config (config.yaml + agents/*.md)."""
        from dotenv import load_dotenv

        if spend is not None and request_limits is None:
            raise ValueError("Spend control requires request limits and disabled retries")

        cfg_path = config_path or find_config_yaml()
        # Same bootstrap the API server does: .env next to config.yaml
        # provides ${LLM_API_KEY} etc. before any config loading.
        load_dotenv(cfg_path.parent / ".env")
        disable_langfuse_tracing()
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
        if request_limits is not None and (agent_def.engine or agent_def.extension):
            raise ValueError("Request limits require the built-in benchmark transport")
        if input_cleanup and (sys.platform != "darwin" or agent_def.engine or agent_def.extension):
            raise ValueError("Input cleanup requires the built-in macOS benchmark driver")
        if comparison is not None:
            comparison.verify(app_config, agent_def)
        configured_token_budget = agent_def.token_budget
        if spend is not None and spend.ledger.record_only and not enforce_agent_budget:
            agent_def = replace(agent_def, token_budget=0)

        profile_name = agent_def.model or app_config.agents.llm_profile
        profile: LLMProfile = app_config.get_llm_profile(profile_name)
        from ..llm.profile import create_llm_from_profile

        llm = CountingLLM(create_llm_from_profile(profile))
        if request_limits is not None:
            llm.disable_retries()

        bus = Bus()
        tool_manager = ToolManager(app_config, bus=bus)

        driver = cls.__new__(cls)
        driver._input_cleanup = MacOSInputCleanup() if input_cleanup else None
        driver._trace = None
        driver._request_limits = request_limits
        driver._request_budget = None
        driver._spend = spend

        def observe_usage(usage: object) -> None:
            session = active_spend_session.get()
            if session is None or session.control is not spend:
                raise SpendLimitExceeded("usage outside active spend trial")
            session.settle(usage)

        if spend is not None:
            llm._inner.on_response_usage = observe_usage

        async def capture_request(request: httpx.Request) -> None:
            if request_limits is not None:
                budget = active_request_budget.get()
                if budget is None or budget is not driver._request_budget or not budget.active:
                    raise RequestLimitExceeded("request outside active trial")
                role = "locator" if grounding_call_id.get() is not None else "planner"
                try:
                    budget.reserve(role)
                except RequestLimitExceeded:
                    if spend is not None:
                        spend.ledger.stop("request_limit")
                    if driver._trace is not None:
                        driver._trace.event("request_blocked", role=role, **budget.snapshot())
                    raise
            request_id = None
            if spend is not None:
                session = active_spend_session.get()
                if session is None or session.control is not spend:
                    raise SpendLimitExceeded("request outside active spend trial")
                request_id = session.reserve(request)
            if driver._trace is not None:
                await driver._trace.capture_request(request, request_id=request_id)

        async def capture_response(response: httpx.Response) -> None:
            # Bind to the requesting trial, not whichever trial is current now.
            binding = response.request.extensions.get("tank_benchmark_trace")
            if binding is not None:
                owner, _ = binding
                if isinstance(owner, TraceSink):
                    await owner.capture_response(response)
            spend_binding = response.request.extensions.get("tank_spend")
            if spend_binding is not None:
                session, _ = spend_binding
                await session.capture_response(response)

        def measured_llm(profile: LLMProfile) -> LLM:
            inner = create_llm_from_profile(profile)
            if spend is not None:
                inner.on_response_usage = observe_usage
            if request_limits is not None:
                inner.disable_retries()
            if capture_request not in inner.client._client.event_hooks["request"]:
                inner.client._client.event_hooks["request"].append(capture_request)
            if capture_response not in inner.client._client.event_hooks["response"]:
                inner.client._client.event_hooks["response"].append(capture_response)
            return cast(LLM, CountingLLM(inner, counter=llm))

        registry = None
        if agent_def.engine or agent_def.extension:
            from ..plugin.manager import PluginManager

            registry = _MeasuredRegistry(llm, lambda: driver._trace)
            ref = agent_def.engine or agent_def.extension
            assert ref is not None
            plugin_name = ref.split(":", 1)[0]
            manifest = PluginManager().discover_plugins().get(plugin_name)
            if manifest is None:
                raise ValueError(f"benchmark engine plugin '{plugin_name}' not found")
            for extension in manifest.extensions:
                registry.register(plugin_name, extension)
        driver._runner = AgentRunner(
            llm=cast(LLM, llm),
            tool_manager=tool_manager,
            bus=bus,
            approval_policy=tool_manager.approval_policy,
            pending_store=PendingToolCallStore(),
            definitions=definitions,
            toolsets_config=app_config.toolsets,
            app_config=app_config if (
                agent_def.engine or agent_def.extension or agent_def.grounding is not None
            ) else None,
            llm_factory=measured_llm,
            registry=registry,
            resolver=AlwaysApproveResolver(),  # benchmarks are autonomous
        )
        driver._agent_def = agent_def
        driver._llm = llm
        driver._tool_manager = tool_manager
        driver._trace = None
        driver._runtime_metadata = ({"comparison_contract": {
            "variant": comparison.variant, "freeze_dir": str(comparison.freeze_dir.resolve()),
        }} if comparison is not None else {})

        driver._runtime_metadata.update(
            input_cleanup=input_cleanup,
            budget_record_only=bool(spend is not None and spend.ledger.record_only),
            agent_budget_enforced=bool(
                spend is not None and spend.ledger.record_only and enforce_agent_budget),
            configured_token_budget=configured_token_budget,
        )

        # Built-in agents use this exact SDK client. Plugin engines own their
        # transport and must not be labelled HTTP-verified by this hook.
        if (
            not agent_def.engine and not agent_def.extension
            and capture_request not in llm.client._client.event_hooks["request"]
        ):
            llm.client._client.event_hooks["request"].append(capture_request)
        if (
            not agent_def.engine and not agent_def.extension
            and capture_response not in llm.client._client.event_hooks["response"]
        ):
            llm.client._client.event_hooks["response"].append(capture_response)

        # Archive every screenshot the agent takes for offline diagnosis.
        for name in ("screenshot", "computer_batch"):
            if name in tool_manager.tools and agent_def.grounding is None:
                tool_manager.tools[name] = TracedScreenshotTool(
                    tool_manager.tools[name], lambda: driver._trace
                )
        # Re-pin the ASCII input source after each app launch (per-app IME
        # memory flips the keyboard back when a launched app takes focus).
        if "launch_app" in tool_manager.tools:
            tool_manager.tools["launch_app"] = RepinImeAfterLaunchTool(
                tool_manager.tools["launch_app"]
            )
        return driver

    def describe(self) -> dict[str, Any]:
        definition = self._agent_def
        config = self._runner._app_config
        summary = {}
        if definition.extension and config is not None:
            raw = config.subagents.get(definition.extension, {})
            summary = {k: raw[k] for k in ("model", "tool_set", "reasoning_effort", "max_steps",
                                          "environment") if k in raw}
        elif definition.engine and config is not None:
            raw = config.get_section("agent_engines").get(definition.engine, {})
            summary = {k: raw[k] for k in ("tool_set", "reasoning_effort", "max_steps") if k in raw}
            profile_name = raw.get("llm_profile", definition.engine.split(":", 1)[0])
            profile = config.llm_profiles.get(profile_name)
            if profile is not None:
                summary.update(model=profile.model, llm_profile=profile_name)
        else:
            summary = {"model": self._llm.model}
        return {"agent_name": definition.name, "engine": definition.engine,
                "extension": definition.extension, "config": summary,
                "prompt_revision": hashlib.sha256(definition.system_prompt.encode()).hexdigest(),
                **self._runtime_metadata,
                "request_limits": asdict(self._request_limits) if self._request_limits else None,
                "grounding": asdict(definition.grounding) if definition.grounding else None,
                "token_budget": definition.token_budget}

    async def run(
        self, instruction: str, trace: TraceSink, *, timeout_s: int, max_steps: int,
    ) -> DriverResult:
        try:
            return await self._run_bounded(instruction, trace, timeout_s=timeout_s,
                                           max_steps=max_steps)
        finally:
            self._trace = None
            self._llm.on_call = None

    async def _run_bounded(
        self, instruction: str, trace: TraceSink, *, timeout_s: int, max_steps: int,
    ) -> DriverResult:
        if self._request_limits is None:
            return await self._run(instruction, trace, timeout_s=timeout_s, max_steps=max_steps)
        if self._request_budget is not None and self._request_budget.active:
            raise RuntimeError("Bounded benchmark trials must run serially")
        budget = RequestBudget(self._request_limits)
        self._request_budget = budget
        token = active_request_budget.set(budget)
        session = None
        spend_token = None
        try:
            if self._spend is not None:
                session = self._spend.start(trace)
                spend_token = active_spend_session.set(session)
            return await self._run(instruction, trace, timeout_s=timeout_s, max_steps=max_steps)
        finally:
            try:
                if session is not None and self._spend is not None:
                    try:
                        self._spend.finish(session)
                    finally:
                        self._runtime_metadata["spend_budget"] = self._spend.ledger.snapshot()
            finally:
                if spend_token is not None:
                    active_spend_session.reset(spend_token)
                budget.active = False
                active_request_budget.reset(token)
                summary = budget.snapshot()
                self._runtime_metadata["request_budget"] = summary
                trace.event("request_budget", **summary)

    async def _run(
        self, instruction: str, trace: TraceSink, *, timeout_s: int, max_steps: int,
    ) -> DriverResult:
        self._trace = trace
        self._llm.reset()
        # Per-call latency lands in the trace next to the actions it delays.
        self._llm.on_call = lambda call, ttft, total: trace.event(
            "llm_call", call=call,
            ttft_s=None if self._agent_def.engine or self._agent_def.extension else ttft,
            total_s=total,
        )
        messages: list[dict[str, Any]] = [{"role": "user", "content": instruction}]
        steps = 0
        token_parts: list[str] = []
        stopped_reason: str | None = None
        terminal: dict[str, Any] = {}
        rtts: list[float] = []
        unknown_calls = 0
        primitives = 0
        non_gui_tools: set[str] = set()

        class Observer:
            def on_event(_self, kind: str, metadata: dict[str, Any]) -> None:
                nonlocal unknown_calls, primitives
                if kind == "desktop_cleanup":
                    terminal["cleanup"] = ("confirmed" if metadata.get("confirmed") is True
                                           else "unconfirmed")
                if kind == "desktop_dispatch" and metadata.get("in_batch"):
                    primitives += int(metadata.get("succeeded", False))
                if kind == "dimensions":
                    self._runtime_metadata["display"] = dict(metadata)
                if "sdk_version" in metadata:
                    self._runtime_metadata["sdk_version"] = metadata["sdk_version"]
                if kind == "screenshot":
                    trace.save_screenshot(metadata["data_url"])
                elif kind == "api_end":
                    elapsed = float(metadata["elapsed_s"])
                    rtts.append(elapsed)
                    if metadata.get("usage") == "unknown":
                        unknown_calls += 1
                    else:
                        self._llm.prompt_tokens += int(metadata["prompt_tokens"])
                        self._llm.completion_tokens += int(metadata["completion_tokens"])
                    self._llm._record(0.0, elapsed)
                    trace.event(kind, **metadata)
                else:
                    trace.event(kind, **metadata)

        async def consume() -> None:
            nonlocal steps, stopped_reason, primitives
            run_kwargs: dict[str, Any] = {}
            if self._input_cleanup is not None:
                run_kwargs.update(desktop_cleanup=self._input_cleanup, observer=Observer())
            if self._agent_def.extension:
                permissions = self._runner.extension_permissions(self._agent_def)
                run_kwargs.update(authorization=SubAgentAuthorization(permissions),
                                  deadline=time.monotonic() + timeout_s, observer=Observer(),
                                  max_steps=max_steps)
            elif self._agent_def.grounding is not None:
                run_kwargs.update(deadline=time.monotonic() + timeout_s, observer=Observer(),
                                  max_steps=max_steps)
            outputs = self._runner.run_agent(self._agent_def, messages, **run_kwargs)
            try:
                async for output in outputs:
                    # Count executed calls, rather than streamed argument deltas.
                    if output.type == AgentOutputType.TOOL_EXECUTING:
                        if steps >= max_steps:
                            stopped_reason = f"max_steps({max_steps}) reached"
                            break
                        steps += 1
                        name = str(output.metadata.get("name", ""))
                        if name not in GUI_TOOLS:
                            non_gui_tools.add(name)
                    elif output.type == AgentOutputType.TOOL_RESULT:
                        name = output.metadata.get("name")
                        if not name and output.metadata.get("status") == "error":
                            stopped_reason = output.content
                            terminal["stop_reason"] = "error"
                        if name == "computer_batch":
                            completed = output.metadata.get("completed_primitives")
                            if completed is None:
                                match = re.match(r"Batch: (\d+) of \d+ actions", output.content)
                                completed = int(match[1]) if match else 0
                            primitives += int(completed)
                        elif (
                            name in GUI_TOOLS - {"locate"}
                            and output.metadata.get("status") == "success"
                        ):
                            primitives += 1
                    elif output.type == AgentOutputType.TOKEN and output.content:
                        token_parts.append(output.content)
                        reason = output.metadata.get("stop_reason")
                        if reason:
                            # Controlled termination (e.g. shared token budget)
                            # reported by the runner; keep it distinguishable
                            # from generic agent errors in reports.
                            terminal["stop_reason"] = reason
                            stopped_reason = output.content.strip()
                    if output.type == AgentOutputType.DONE:
                        terminal.update(output.metadata)
                    if output.type != AgentOutputType.USAGE:
                        trace.output(output)
            finally:
                close = getattr(outputs, "aclose", None)
                if close is not None:
                    await close()

        timed_out = False
        start = time.monotonic()
        try:
            await asyncio.wait_for(consume(), timeout=timeout_s)
        except TimeoutError:
            timed_out = True
            stopped_reason = f"timeout({timeout_s}s)"
        except SubAgentCleanupError as exc:
            terminal.update(cleanup="unconfirmed", stop_reason="error")
            stopped_reason = str(exc)
        except SubAgentStopped as exc:
            terminal.update(exc.metadata)
            terminal["stop_reason"] = exc.reason
            terminal["cleanup"] = "confirmed"
            stopped_reason = str(exc)
        except Exception as exc:
            stopped_reason = f"{type(exc).__name__}: {exc}"
            terminal["stop_reason"] = "error"

        if self._agent_def.extension and terminal.get("cleanup") != "unconfirmed":
            terminal["cleanup"] = "confirmed"
        if timed_out:
            terminal["stop_reason"] = "timeout"
        if self._request_budget is not None and self._request_budget.blocked:
            terminal["stop_reason"] = "request_limit"
        if "sdk_version" in terminal:
            self._runtime_metadata["sdk_version"] = terminal["sdk_version"]
        wall_s = time.monotonic() - start
        call_stats = self._llm.call_stats
        ttfts = [t for t, _ in call_stats if t is not None]
        unknown_calls += self._llm.unknown_calls
        totals = [t for _, t in call_stats]
        llm_calls = len(call_stats)
        llm_ttft_s = (median(ttfts) if ttfts else None) if not (
            self._agent_def.engine or self._agent_def.extension
        ) else None
        llm_call_s = median(totals) if totals else 0.0
        llm_total_s = sum(totals)
        trace.event(
            "driver_done",
            steps=steps,
            tokens=self._llm.total_tokens,
            wall_s=wall_s,
            timed_out=timed_out,
            stopped_reason=stopped_reason,
            llm_calls=llm_calls,
            llm_ttft_s=llm_ttft_s,
            llm_call_s=llm_call_s,
            llm_total_s=llm_total_s,
            stop_reason=terminal.get("stop_reason"), cleanup=terminal.get("cleanup", "unknown"),
            unknown_calls=unknown_calls,
        )
        self._llm.on_call = None
        self._trace = None
        return DriverResult(
            final_text="".join(token_parts),
            steps=steps,
            wall_s=wall_s,
            tokens=self._llm.total_tokens,
            screenshots=trace.screenshot_count,
            timed_out=timed_out,
            error=stopped_reason,
            llm_calls=llm_calls,
            llm_ttft_s=llm_ttft_s,
            llm_call_s=llm_call_s,
            llm_total_s=llm_total_s,
            llm_rtt_s=median(rtts) if rtts else (llm_call_s if self._agent_def.engine else 0.0),
            stop_reason=terminal.get("stop_reason"), cleanup=terminal.get("cleanup", "unknown"),
            primitives=primitives,
            model_turns=int(terminal.get("model_turns", llm_calls)), unknown_calls=unknown_calls,
            non_gui_tools=tuple(sorted(non_gui_tools)),
        )
