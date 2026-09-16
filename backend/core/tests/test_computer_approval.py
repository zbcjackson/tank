"""A5: computer-control approval gate — dispatch-level, one ask per task.

Flow under test:
  agent(prompt, subagent_type=computer_use)
    → AgentTool parks a pending approval (token inside)
    → user confirms via ConfirmActionTool → re-enters AgentTool WITH token
    → dispatch proceeds with allowed_categories={"computer"} (ScopedPolicy
      lets every action inside the run pass; other categories unchanged).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from tank_backend.agents.agent_tool import AgentTool
from tank_backend.agents.approval import (
    PendingToolCallStore,
    ScopedPolicy,
    ToolApprovalPolicy,
)
from tank_backend.agents.definition import AgentDefinition
from tank_backend.agents.runner import AgentRunner
from tank_backend.tools.confirm_action import ConfirmActionTool


def _policy(computer_mode: str = "require") -> ToolApprovalPolicy:
    """Policy whose metadata routes click/type as computer tools."""
    meta = {"click": MagicMock(category="computer"),
            "type_text": MagicMock(category="computer")}
    return ToolApprovalPolicy(tool_metadata=meta, computer_mode=computer_mode)


def _completed_run(output: str):
    from types import SimpleNamespace

    return SimpleNamespace(
        status="completed", output=output, task_id="task_1",
        error=None, started_at=0.0, finished_at=1.0,
    )


def _computer_toolset_policy() -> ToolApprovalPolicy:
    return _policy()


def test_engine_desktop_capability_requires_approval_even_with_empty_toolset():
    from tank_backend.plugin.manifest import ExtensionManifest
    from tank_backend.plugin.registry import ExtensionRegistry

    runner = _runner(_policy())
    registry = ExtensionRegistry()
    registry.register("desktop", ExtensionManifest(
        name="agent", type="agent", factory="unused:create",
        needs=("desktop_executor",),
    ))
    runner._registry = registry
    definition = AgentDefinition(name="desktop", description="", system_prompt="",
                                 engine="desktop:agent", tool_filter=())
    assert AgentTool(runner)._computer_gate_needed(definition)

    
def _runner(policy: ToolApprovalPolicy) -> AgentRunner:
    return AgentRunner(
        llm=MagicMock(),
        tool_manager=MagicMock(),
        bus=MagicMock(),
        approval_policy=policy,
        pending_store=PendingToolCallStore(),
        definitions={
            "computer_use": AgentDefinition(
                name="computer_use", description="gui",
                system_prompt="gui", tool_filter=["click", "type_text"],
                background=False,
            ),
            "researcher": AgentDefinition(
                name="researcher", description="res", system_prompt="res",
                tool_filter=["web_search"], background=False,
            ),
        },
    )


# ── policy ────────────────────────────────────────────────────────────


async def test_computer_category_requires_approval_by_default():
    verdict = _policy().evaluate("click")
    assert verdict.level.name == "REQUIRE_APPROVAL"
    assert verdict.reason.startswith("computer control")


async def test_computer_category_allow_mode():
    verdict = _policy(computer_mode="allow").evaluate("click")
    assert verdict.level.name == "ALLOW"


async def test_computer_category_async_matches_sync():
    verdict = await _policy().evaluate_async("click")
    assert verdict.level.name == "REQUIRE_APPROVAL"


def test_all_computer_tools_carry_computer_category():
    from tank_backend.tools import computer_use as linux_mod
    from tank_backend.tools import computer_use_macos as macos_mod

    expected = {
        "ClickTool", "TypeTextTool", "KeyPressTool", "ScrollTool",
        "MouseMoveTool", "MouseDownTool", "MouseUpTool",
        "HoldKeyTool", "DragTool", "ScreenshotTool", "LaunchAppTool",
    }
    for mod in (linux_mod, macos_mod):
        for name in expected:
            cls = getattr(mod, name, None)
            if cls is None:
                continue  # platform-specific tool (LaunchAppTool is macOS-only)
            try:
                tool = cls()
            except TypeError:
                tool = cls(MagicMock())
            meta = tool.get_metadata()
            assert meta.category == "computer", (mod.__name__, name)


# ── ScopedPolicy ──────────────────────────────────────────────────────


async def test_scoped_policy_allows_computer_delegates_others():
    inner = _policy()
    scoped = ScopedPolicy(inner, {"computer"})
    assert scoped.evaluate("click").level.name == "ALLOW"
    # other categories unchanged: a web tool still routes through inner
    # un-scoped category falls through to the inner policy untouched
    assert scoped.evaluate("weather").level.name == "ALLOW"
    assert scoped.computer_requires_approval() is False


# ── AgentTool dispatch gate ────────────────────────────────────────────


async def test_dispatch_parks_when_computer_toolset():
    policy = _computer_toolset_policy()
    runner = _runner(policy)
    supervisor = MagicMock()
    supervisor.run_foreground = MagicMock(side_effect=AssertionError("must not run"))
    tool = AgentTool(runner, supervisor=supervisor)

    result = await tool.execute(
        prompt="open calculator", subagent_type="computer_use",
        ctx=None,
    )
    assert "APPROVAL REQUIRED" in result.content
    assert runner._pending_store.list_pending(), "one parked approval"
    supervisor.run_foreground.assert_not_called()


async def test_approved_token_reentry_dispatches_with_scope():
    policy = _computer_toolset_policy()
    runner = _runner(policy)
    supervisor = MagicMock()
    supervisor.run_foreground = AsyncMock(
        return_value=_completed_run("done")
    )
    tool = AgentTool(runner, supervisor=supervisor)

    parked = await tool.execute(
        prompt="open calculator", subagent_type="computer_use",
    )
    assert "APPROVAL REQUIRED" in parked.content
    assert runner._pending_store.get_oldest_pending() is not None

    # User approves via ConfirmActionTool → re-executes agent with token args
    tm = MagicMock()

    async def delegate(tool_name: str, **kw):
        return await tool.execute(**kw)

    tm.execute_tool = delegate
    confirm = ConfirmActionTool(runner._pending_store, tm, policy)
    approved = await confirm.execute(approved=True)
    assert not approved.error

    # dispatch happened with the computer scope
    supervisor.run_foreground.assert_called_once()
    kwargs = supervisor.run_foreground.call_args.kwargs
    assert kwargs.get("allowed_categories") == {"computer"}


async def test_rejected_token_never_dispatches():
    policy = _computer_toolset_policy()
    runner = _runner(policy)
    supervisor = MagicMock()
    tool = AgentTool(runner, supervisor=supervisor)

    await tool.execute(prompt="open calculator", subagent_type="computer_use")
    confirm = ConfirmActionTool(runner._pending_store, MagicMock(), policy)
    rejection = await confirm.execute(approved=False)

    assert "rejected" in rejection.content
    supervisor.run_foreground.assert_not_called()
    assert runner._pending_store.list_pending() == []


async def test_non_computer_agent_skips_gate():
    runner = _runner(_computer_toolset_policy())
    supervisor = MagicMock()
    supervisor.run_foreground = AsyncMock(
        return_value=_completed_run("ok")
    )
    tool = AgentTool(runner, supervisor=supervisor)

    await tool.execute(prompt="research x", subagent_type="researcher")
    supervisor.run_foreground.assert_called_once()
    assert supervisor.run_foreground.call_args.kwargs.get(
        "allowed_categories"
    ) is None
    assert runner._pending_store.list_pending() == []


async def test_allow_mode_skips_gate():
    policy = _computer_toolset_policy()
    policy._computer_mode = "allow"
    runner = _runner(policy)
    supervisor = MagicMock()
    supervisor.run_foreground = AsyncMock(
        return_value=_completed_run("ok")
    )
    tool = AgentTool(runner, supervisor=supervisor)
    await tool.execute(prompt="open calculator", subagent_type="computer_use")
    supervisor.run_foreground.assert_called_once()


async def test_policy_sees_late_tool_registrations():
    """The manager registers tools AFTER building the policy, passing its
    live (still-empty) metadata dict — the policy must keep the SAME
    object, not `or {}`-swap it for a fresh one (real bug: every computer
    tool resolved as 'general' and the dispatch gate never fired)."""
    meta: dict = {}
    policy = ToolApprovalPolicy(tool_metadata=meta, computer_mode="require")
    meta["click"] = MagicMock(category="computer")  # registered later
    assert policy.category_for("click") == "computer"
