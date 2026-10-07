"""Native AX channel tests replace OS boundaries, not host execution or verification."""

import asyncio
from dataclasses import replace

import pytest

from agent_computer_use.contracts import DecisionResult, GoalContract
from tank_backend.agents.subagent import (
    SubAgentAuthorization, SubAgentBudget, SubAgentContext, SubAgentRequest,
)
from tank_backend.tools.computer_ax import AXCandidate, AXElementRef


def native_config(mode: str = "ax_press") -> dict[str, object]:
    return {"scope": "counter", "bundle_id": "test.counter", "pid": 42,
            "process_start": "1:0", "window_id": 7, "dispatch": mode,
            "readouts": [{"name": "result", "role": "AXStaticText", "identifier": "result"}]}


def goal() -> GoalContract:
    return GoalContract.from_input({
        "schema_version": 2, "goal_id": "increment", "intent": "Increment once",
        "objective": "Increment once", "scope": "counter", "authorization_ref": "current_task",
        "allowed_operations": ["click"],
        "completion": [{"key": "ax:value:result", "value": "1"}],
    })


class Select:
    async def choose(self, goal, snapshot, actions, ctx):
        assert len(actions.actions) == 1
        return DecisionResult(actions.binding, "candidate", actions.actions[0].id)


@pytest.fixture
def world(monkeypatch):
    from agent_computer_use.channels import native

    class World:
        window = native.NativeWindow(42, "1:0", "test.counter", 7, (0, 0, 100, 80),
                                     (5, 0, 0, 100, 80, 200, 160))
        def __init__(self):
            self.value = "0"
            self.reads, self.sent = [], []
            self.incomplete = False
            self.button = AXCandidate(1, "AXButton", "Increment", "", "", "increment",
                ("AXPress",), True, (10, 10, 20, 20), AXElementRef(object(), False, 80),
                pid=42, window_id=7)
            self.output = AXCandidate(2, "AXStaticText", "Result", "0", "", "result", (), True,
                (40, 10, 20, 20), AXElementRef(object(), False, 80), pid=42, window_id=7)
            self.buttons = [self.button]
            self.exposed = True

        def read(self, window, display, **kwargs):
            self.reads.append(window)
            return [*self.buttons, replace(self.output, value=self.value)], self.incomplete

        def press(self, ref):
            self.sent.append(("press", ref))
            self.value = str(int(self.value) + 1)

        def click(self, x, y, **kwargs):
            assert kwargs == {"clear_modifiers": True}
            self.sent.append(("click", (x, y)))
            self.value = str(int(self.value) + 1)

        def fill(self, ref, value):
            self.sent.append(("fill", value))
            self.value = value

    world = World()
    monkeypatch.setattr(native, "read_window", lambda config: world.window)
    monkeypatch.setattr("agent_computer_use.observation.ax_window_candidates", world.read)
    monkeypatch.setattr(native, "ax_press", world.press)
    monkeypatch.setattr(native, "ax_set_value", world.fill)
    monkeypatch.setattr(native.macos, "_click_macos", world.click)
    monkeypatch.setattr(native, "pointer_target_is_exposed", lambda *args: world.exposed)
    monkeypatch.setattr(native, "inputs_idle", lambda: True)
    return world


def context() -> SubAgentContext:
    return SubAgentContext(SubAgentAuthorization(frozenset({"desktop"})),
                           SubAgentBudget(), asyncio.Event())


async def test_native_click_uses_current_ax_evidence_and_verifies_readout(world) -> None:
    from agent_computer_use.factory import create_subagent

    agent = create_subagent({"macos": native_config()})
    agent.controller.selector = Select()
    ctx = context()
    try:
        outputs = [o async for o in agent.run(
            SubAgentRequest("Increment", "", "task", goal().model_dump(mode="json")), ctx)]
        result = outputs[-1].metadata["task_result"]
        assert (result["status"], result["reason"]) == ("completed", "goal_verified")
        assert len(world.sent) == 1 and len(world.reads) >= 3
        assert len(result["details"]["progress"]["verified_actions"]) == 1
    finally:
        await agent.aclose()
        await ctx.runtime.aclose()


async def test_native_scope_offers_all_scientific_controls_without_shortlisting(world) -> None:
    from agent_computer_use.action_builder import ActionBuilder
    from agent_computer_use.factory import create_subagent

    world.buttons = [replace(world.button, index=i, title=str(i), identifier=str(i),
                             element=AXElementRef(object(), False, 80)) for i in range(54)]
    agent = create_subagent({"macos": native_config()})
    class FullSet:
        async def choose(self, goal, snapshot, actions, ctx):
            assert len(actions.actions) == 54 and not actions.truncated
            return DecisionResult(actions.binding, "candidate", actions.actions[0].id)
    agent.controller.selector = FullSet()
    ctx = context()
    ctx.runtime.bind("task")
    try:
        snapshot = await agent.controller.source.observe("counter", ctx)
        # Other channels keep their existing ceiling and reject incomplete choices.
        assert ActionBuilder().build("goal", 1, goal(), snapshot).truncated
        outputs = [o async for o in agent.run(
            SubAgentRequest("Increment", "", "task", goal().model_dump(mode="json")), ctx)]
        assert outputs[-1].metadata["task_result"]["status"] == "completed"
    finally:
        await agent.aclose()
        await ctx.runtime.aclose()


async def test_identifier_bound_textarea_preserves_unicode_without_enabled_attribute(world) -> None:
    from agent_computer_use.factory import create_subagent

    text = "Ada\n测试  "
    world.buttons = []
    world.value = ""
    world.output = replace(world.output, role="AXTextArea", identifier="First Text View",
                           title="", enabled=None, value_settable=True)
    config = {**native_config(), "labels": "identifier",
              "readouts": [{"name": "document", "role": "AXTextArea",
                            "identifier": "First Text View"}]}
    task = goal().model_dump(mode="json")
    task.update(objective="Replace the document body", allowed_operations=["fill"],
                inputs=[{"key": "body", "purpose": "document body", "value": text}],
                completion=[{"key": "ax:value:document", "value": text}])
    agent = create_subagent({"macos": config})
    agent.controller.selector = Select()
    ctx = context()
    try:
        outputs = [o async for o in agent.run(SubAgentRequest("Write", "", "task", task), ctx)]
        assert outputs[-1].metadata["task_result"]["status"] == "completed"
        assert world.sent == [("fill", text)] and world.value == text
    finally:
        await agent.aclose()
        await ctx.runtime.aclose()


async def test_display_readout_tracks_expression_and_result_as_bound_regions(world, monkeypatch):
    from agent_computer_use.channels import native
    from agent_computer_use.factory import create_subagent

    expression = replace(world.output, element=AXElementRef(object(), False, 80),
                         frame=(40, 5, 20, 10), ancestor_identifiers=("StandardResultView",))
    def read(window, display, **kwargs):
        outputs = [replace(world.output, value="\u200e56" if world.sent else "\u200e0",
                           ancestor_identifiers=("StandardInputView",))]
        if world.sent:
            outputs.append(replace(expression, value="\u200e7 × 8"))
        return [world.button, *outputs], False
    monkeypatch.setattr("agent_computer_use.observation.ax_window_candidates", read)
    config = {**native_config(), "readouts": [
        {"name": "expression", "role": "AXStaticText", "aggregation": "compact_text",
         "ancestor_identifier": "StandardResultView", "allow_empty": True},
        {"name": "result", "role": "AXStaticText", "aggregation": "compact_text",
         "ancestor_identifier": "StandardInputView"}]}
    task = goal().model_dump(mode="json")
    task["completion"] = [{"key": "ax:value:expression", "value": "7×8"},
                          {"key": "ax:value:result", "value": "56"}]
    agent = create_subagent({"macos": config})
    agent.controller.selector = Select()
    ctx = context()
    try:
        outputs = [o async for o in agent.run(SubAgentRequest("Compute", "", "task", task), ctx)]
        assert outputs[-1].metadata["task_result"]["status"] == "completed"
        assert len(world.sent) == 1
        assert isinstance(agent.controller.source, native.NativeAXChannel)
        assert agent.controller.source.previous is not None
        assert {f.key: f.value for f in agent.controller.source.previous.facts} == {
            "ax:value:expression": "7×8", "ax:value:result": "56"}
    finally:
        await agent.aclose()
        await ctx.runtime.aclose()


@pytest.mark.parametrize("mode", ["ax_press", "quartz"])
@pytest.mark.parametrize("change", ["replacement", "move", "process", "disabled", "incomplete"])
async def test_native_stale_state_never_dispatches(world, mode, change):
    from agent_computer_use.factory import create_subagent

    class Mutate(Select):
        async def choose(self, goal, snapshot, actions, ctx):
            result = await super().choose(goal, snapshot, actions, ctx)
            if change == "replacement":
                world.buttons[0] = replace(world.button, element=AXElementRef(object(), False, 80))
            elif change == "move":
                world.window = replace(world.window, bounds=(1, 0, 99, 80))
            elif change == "process":
                world.window = replace(world.window, process_start="2:0")
            elif change == "disabled":
                world.buttons[0] = replace(world.button, enabled=False)
            else:
                world.incomplete = True
            return result

    agent = create_subagent({"macos": native_config(mode)})
    agent.controller.selector = Mutate()
    ctx = context()
    try:
        outputs = [o async for o in agent.run(
            SubAgentRequest("Increment", "", "task", goal().model_dump(mode="json")), ctx)]
        assert outputs[-1].metadata["task_result"]["reason"] == "stale_reference"
        assert not world.sent
    finally:
        await agent.aclose()
        await ctx.runtime.aclose()


@pytest.mark.parametrize("case", ["unknown", "lost_reply", "occluded"])
async def test_native_uncertain_effects_are_read_back_never_replayed(world, monkeypatch, case):
    from agent_computer_use.channels import native
    from agent_computer_use.factory import create_subagent

    def press(ref):
        world.sent.append(("press", ref))
        if case == "lost_reply":
            world.value = "1"
        else:
            world.buttons[0] = replace(world.button, title="Unrelated UI changed")
        raise RuntimeError("lost native reply")
    monkeypatch.setattr(native, "ax_press", press)
    world.exposed = case != "occluded"
    agent = create_subagent({"macos": native_config("quartz" if case == "occluded" else "ax_press")})
    agent.controller.selector = Select()
    ctx = context()
    try:
        outputs = [o async for o in agent.run(
            SubAgentRequest("Increment", "", "task", goal().model_dump(mode="json")), ctx)]
        result = outputs[-1].metadata["task_result"]
        assert result["status"] == {"unknown": "unknown", "lost_reply": "completed",
                                    "occluded": "stopped"}[case]
        assert len(world.sent) == (0 if case == "occluded" else 1)
    finally:
        await agent.aclose()
        await ctx.runtime.aclose()


async def test_window_move_during_pointer_exposure_check_prevents_send(world, monkeypatch):
    from agent_computer_use.channels import native
    from agent_computer_use.factory import create_subagent

    def exposed(*args):
        world.window = replace(world.window, bounds=(5, 0, 95, 80))
        return True
    monkeypatch.setattr(native, "pointer_target_is_exposed", exposed)
    agent = create_subagent({"macos": native_config("quartz")})
    agent.controller.selector = Select()
    ctx = context()
    try:
        outputs = [o async for o in agent.run(
            SubAgentRequest("Increment", "", "task", goal().model_dump(mode="json")), ctx)]
        assert outputs[-1].metadata["task_result"]["reason"] == "not_sent"
        assert not world.sent
    finally:
        await agent.aclose()
        await ctx.runtime.aclose()


async def test_active_user_input_prevents_native_send(world, monkeypatch):
    from agent_computer_use.channels import native
    from agent_computer_use.factory import create_subagent

    monkeypatch.setattr(native, "inputs_idle", lambda: False)
    agent = create_subagent({"macos": native_config()})
    agent.controller.selector = Select()
    ctx = context()
    try:
        outputs = [o async for o in agent.run(
            SubAgentRequest("Increment", "", "task", goal().model_dump(mode="json")), ctx)]
        assert outputs[-1].metadata["task_result"]["reason"] == "not_sent"
        assert agent.controller.receipts[0].reason == "user_input_active"
        assert not world.sent
    finally:
        await agent.aclose()
        await ctx.runtime.aclose()


async def test_native_explicit_scope_exclusions_are_not_executable(world):
    from agent_computer_use.factory import create_subagent

    config = {**native_config(), "blocked_identifiers": ["increment"]}
    agent = create_subagent({"macos": config})
    agent.controller.selector = Select()
    ctx = context()
    try:
        outputs = [o async for o in agent.run(
            SubAgentRequest("Increment", "", "task", goal().model_dump(mode="json")), ctx)]
        assert outputs[-1].metadata["task_result"]["reason"] == "no_viable_actions"
        assert not world.sent
    finally:
        await agent.aclose()
        await ctx.runtime.aclose()


def test_native_pilot_prepares_bounded_cases_without_desktop_or_credentials(tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s4_ax

    frozen = s4_ax.prepare(tmp_path / "pilot")
    assert len(frozen["cases"]) == 9
    assert frozen["request_limit"] == 78
    assert frozen["nano_usd_limit"] == 250_000_000
    assert s4_ax.load_freeze(tmp_path / "pilot", frozen["sha256"]) == frozen
    with pytest.raises(ValueError, match="freeze"):
        s4_ax.load_freeze(tmp_path / "pilot", "wrong")
    for case in frozen["cases"]:
        contract = GoalContract.from_input(s4_ax.task_goal(case))
        assert "milestones" not in contract.model_dump()
        assert all(f.key.startswith("ax:value:") for f in contract.completion)


def test_pilot_places_only_owned_offscreen_windows_on_primary(monkeypatch):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use.s4_ax import setup_position

    geometry = (2, 0, 0, 1920, 1080, 3840, 2160)
    bounds = {"X": 2200.0, "Y": -200.0, "Width": 674.0, "Height": 408.0}
    assert setup_position(bounds, geometry, False) == (240.0, 160.0)
    bounds.update(X=500.0, Y=100.0)
    assert setup_position(bounds, geometry, False) is None
    assert setup_position(bounds, geometry, True) == (280.0, 180.0)


async def test_standalone_fake_transport_intercepts_sdk_without_pytest_bridge(monkeypatch):
    from pathlib import Path
    import httpx2
    import socket
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use.s4_ax import fake_model_http
    from tank_backend.llm.decision_model import DecisionModel
    from tank_backend.llm.decision_profile import DecisionModelProfile

    seen = []
    async def respond(request):
        seen.append(str(request.url))
        return httpx2.Response(200, json={"model": "jev-1.13.0", "answers": {"next_action": {
            "type": "choice", "choice": "button", "confidence": 1,
            "probabilities": {"button": 1}}}, "usage": {"input_tokens": 12, "output_tokens": 0}})
    def no_dns(*args):
        raise AssertionError("A fake SDK request attempted real DNS")
    monkeypatch.setattr(socket, "getaddrinfo", no_dns)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    model = DecisionModel(DecisionModelProfile("https://s4-ax.invalid/v1/systemone", "jev-1.13.0", "FAKE"),
                          credential="fixture-only")
    with fake_model_http(respond):
        try:
            result = await model.choose(state={}, instructions="Choose", options={"button": "Press"})
            assert result.choice == "button" and len(seen) == 1
        finally:
            await model.aclose()


@pytest.mark.parametrize("reused", [False, True])
def test_kernel_process_identity_rejects_pid_reuse(tmp_path, monkeypatch, reused):
    import ctypes
    import plistlib
    from unittest.mock import MagicMock
    from agent_computer_use.channels import native
    from tank_backend.agents.subagent import SubAgentStopped

    bundle = tmp_path / "Counter.app"
    (bundle / "Contents/MacOS").mkdir(parents=True)
    (bundle / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "test.counter"}))
    executable = str(bundle / "Contents/MacOS/Counter").encode()
    calls = []
    def info(pid, flavor, arg, pointer, size):
        assert pid == 42 and flavor == 3 and size == 136
        record = ctypes.cast(pointer, ctypes.POINTER(native.ProcessInfo)).contents
        record.pid = 42
        record.started_seconds = 100 + int(reused and bool(calls))
        record.started_microseconds = 321
        calls.append(pid)
        return size
    def path(pid, buffer, size):
        buffer.value = executable
        return len(executable)
    library = MagicMock()
    library.proc_pidinfo.side_effect = info
    library.proc_pidpath.side_effect = path
    monkeypatch.setattr(native.ctypes, "CDLL", lambda *args, **kwargs: library)
    if reused:
        with pytest.raises(SubAgentStopped, match="process_changed"):
            native.process_identity(42)
    else:
        assert native.process_identity(42) == native.ProcessIdentity("100:321", "test.counter")


@pytest.mark.parametrize("case", ["reused_pid", "restore_failed"])
def test_pilot_cleanup_never_kills_reused_pid_or_claims_failed_restoration(tmp_path, monkeypatch, case):
    from pathlib import Path
    from types import SimpleNamespace
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s4_ax
    from agent_computer_use.channels import native

    owner = s4_ax.OwnedApplication(s4_ax.CASES[0])
    owner.pid, owner.window_id = 42, 7
    owner.identity = native.ProcessIdentity("1:0", "com.apple.calculator")
    owner.original_front = SimpleNamespace(processIdentifier=lambda: 9, activateWithOptions_=lambda x: None)
    alive, focused, signals = [True], [42], []
    def kill(pid, sig):
        signals.append(pid)
        alive[0], focused[0] = False, 0
    monkeypatch.setattr(s4_ax, "process_alive", lambda pid: alive[0])
    monkeypatch.setattr(s4_ax, "pump", lambda *args: None)
    monkeypatch.setattr(owner, "windows", lambda: [{"kCGWindowNumber": 7}])
    monkeypatch.setattr(s4_ax.os, "kill", kill)
    monkeypatch.setattr(s4_ax.computer_ax, "_load_ax", lambda: {})
    monkeypatch.setattr(s4_ax.computer_ax, "ax_focused_pid", lambda: focused[0])
    monkeypatch.setattr(native, "process_identity", lambda pid: native.ProcessIdentity(
        "2:0" if case == "reused_pid" else "1:0", "com.apple.calculator"))
    if case == "reused_pid":
        with pytest.raises(RuntimeError, match="identity"):
            owner.close()
        assert not signals
    else:
        result = owner.close()
        assert signals == [42] and not alive[0]
        assert not result["confirmed"] and not result["frontmost_restored"]


@pytest.mark.parametrize("recovers", [False, True])
def test_independent_native_readback_has_bounded_read_only_retries(monkeypatch, recovers):
    from pathlib import Path
    from unittest.mock import Mock
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s4_ax

    owner = s4_ax.OwnedApplication(s4_ax.CASES[0])
    values = {"expression": "7×8", "result": "56"}
    read = Mock(side_effect=[RuntimeError("AX temporarily unavailable"),
                            RuntimeError("AX temporarily unavailable"),
                            values if recovers else RuntimeError("still unavailable")])
    monkeypatch.setattr(owner, "read_values_once", read)
    monkeypatch.setattr(s4_ax, "pump", lambda *args: None)
    if recovers:
        assert owner.read_values() == values
    else:
        with pytest.raises(RuntimeError, match="still unavailable"):
            owner.read_values()
    assert read.call_count == 3


def test_independent_validator_ignores_other_ax_windows_only_after_geometry_binding(monkeypatch):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s4_ax

    owner = s4_ax.OwnedApplication(s4_ax.CASES[0])
    owner.pid, owner.window_id = 42, 7
    attrs = {"app": {"AXWindows": ["main", "aux"]},
             "main": {"AXChildren": ["group"]}, "aux": {"AXChildren": []},
             "group": {"AXIdentifier": "StandardInputView", "AXChildren": ["text"]},
             "text": {"AXRole": "AXStaticText", "AXValue": "56"}}
    api = {"AXUIElementCreateApplication": lambda pid: "app",
           "AXUIElementCopyAttributeValue": lambda e, key, out: (0, attrs[e].get(key))}
    monkeypatch.setattr(s4_ax.computer_ax, "_load_ax", lambda: api)
    monkeypatch.setattr(s4_ax.computer_ax, "ax_focused_pid", lambda: 42)
    monkeypatch.setattr(s4_ax.computer_ax, "_top_left_frame", lambda api, e, h:
                        (0, 0, 100, 80) if e == "main" else (50, 50, 10, 10))
    monkeypatch.setattr(s4_ax.computer_ax, "_flipped_frame", lambda *args: None)
    monkeypatch.setattr(s4_ax.computer_use_macos, "_active_displays", lambda: ((5, 0, 0, 100, 80, 200, 160),))
    monkeypatch.setattr(owner, "windows", lambda: [
        {"kCGWindowNumber": 7, "kCGWindowBounds": {"X": 0, "Y": 0, "Width": 100, "Height": 80}}])
    assert owner.read_values_once() == {"result": "56"}


@pytest.mark.parametrize("stop", [None, "stale", "revoke", "cancel", "budget"])
async def test_native_selector_uses_real_sdk_and_preserves_stop_boundaries(world, monkeypatch, stop):
    import httpx
    from agent_computer_use.factory import create_subagent
    from tank_backend.agents.subagent import SubAgentCancelled
    from .test_jev import setup, reply

    async def respond(request):
        if stop == "stale":
            world.buttons[0] = replace(world.button, enabled=False)
        elif stop == "revoke":
            ctx.authorization.revoke()
        elif stop == "cancel":
            ctx.cancel.set()
        return httpx.Response(200, json=reply(request))
    ctx, _, sent, _ = setup(monkeypatch, respond)
    if stop == "budget":
        ctx.budget.limit = 1
        ctx.budget.record("existing", 1, 0)
    agent = create_subagent({"macos": native_config(), "selector": "jev"})
    try:
        if stop == "cancel":
            with pytest.raises(SubAgentCancelled):
                _ = [o async for o in agent.run(
                    SubAgentRequest("Increment", "", "task", goal().model_dump(mode="json")), ctx)]
        else:
            outputs = [o async for o in agent.run(
                SubAgentRequest("Increment", "", "task", goal().model_dump(mode="json")), ctx)]
            assert outputs[-1].metadata["task_result"]["status"] == ("completed" if stop is None else "stopped")
        assert len(sent) == (0 if stop == "budget" else 1)
        assert len(world.sent) == (1 if stop is None else 0)
        if stop is None:
            assert ctx.budget.total_tokens == 12
    finally:
        await agent.aclose()
        await ctx.runtime.aclose()


async def test_native_cleanup_failure_cannot_claim_success(world, monkeypatch):
    from agent_computer_use.channels import native
    from agent_computer_use.factory import create_subagent
    from tank_backend.agents.subagent import SubAgentCleanupError
    from tank_backend.agents.subagent_adapter import SubAgentAdapter
    from tank_backend.agents.base import AgentState

    def click(*args, **kwargs):
        world.sent.append(("click", args))
        world.value = "1"
        raise RuntimeError("mouseup delivery unknown")
    def cleanup():
        raise RuntimeError("left button still held")
    monkeypatch.setattr(native.macos, "_click_macos", click)
    monkeypatch.setattr(native, "release_uncertain_pointer", cleanup)
    agent = create_subagent({"macos": native_config("quartz")})
    agent.controller.selector = Select()
    ctx = context()
    try:
        adapter = SubAgentAdapter("native", agent, SubAgentRequest(
            "Increment", "", "task", goal().model_dump(mode="json")), ctx)
        with pytest.raises(SubAgentCleanupError) as error:
            _ = [o async for o in adapter.run(AgentState())]
        assert error.value.task_result is not None
        assert error.value.task_result.status == "unknown"
        assert error.value.task_result.cleanup == "unknown"
    finally:
        await ctx.runtime.aclose()


async def test_native_cancel_joins_inflight_action_before_cleanup(world, monkeypatch):
    import threading
    from agent_computer_use.channels import native
    from agent_computer_use.factory import create_subagent
    from tank_backend.agents.subagent import SubAgentCancelled
    from tank_backend.agents.subagent_adapter import SubAgentAdapter
    from tank_backend.agents.base import AgentState

    entered, release = threading.Event(), threading.Event()
    def press(ref):
        entered.set()
        assert release.wait(3)
        world.sent.append(("press", ref))
        world.value = "1"
    monkeypatch.setattr(native, "ax_press", press)
    agent = create_subagent({"macos": native_config()})
    agent.controller.selector = Select()
    ctx = context()
    adapter = SubAgentAdapter("native", agent, SubAgentRequest(
        "Increment", "", "task", goal().model_dump(mode="json")), ctx)
    async def run():
        return [o async for o in adapter.run(AgentState())]
    running = asyncio.create_task(run())
    assert await asyncio.to_thread(entered.wait, 2)
    running.cancel()
    try:
        await asyncio.sleep(0.01)
        assert not running.done()
    finally:
        release.set()
        with pytest.raises(SubAgentCancelled) as error:
            await running
        assert error.value.task_result is not None and error.value.task_result.status == "unknown"
        assert error.value.task_result.cleanup == "confirmed"
        await ctx.runtime.aclose()
    assert len(world.sent) == 1


@pytest.mark.parametrize("kind", ["actions", "observations"])
async def test_native_channel_cannot_reset_existing_operation_limits(world, kind):
    from agent_computer_use.factory import create_subagent

    agent = create_subagent({"macos": native_config()})
    agent.controller.selector = Select()
    ctx = context()
    ctx.runtime.restrict_operations(**{kind: 0})
    try:
        outputs = [o async for o in agent.run(
            SubAgentRequest("Increment", "", "task", goal().model_dump(mode="json")), ctx)]
        assert outputs[-1].metadata["task_result"]["status"] == "stopped"
        assert not world.sent
        if kind == "observations":
            assert not world.reads
    finally:
        await agent.aclose()
        await ctx.runtime.aclose()


@pytest.mark.parametrize("window_ids", [[], [7], [7, 8]])
def test_pilot_cleanup_closes_verified_launch_before_window_binding(monkeypatch, window_ids):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s4_ax
    from agent_computer_use.channels import native

    owner = s4_ax.OwnedApplication(s4_ax.CASES[0])
    owner.pid = 42
    owner.identity = native.ProcessIdentity("1:0", "com.apple.calculator")
    alive, signals = [True], []
    monkeypatch.setattr(s4_ax, "process_alive", lambda pid: alive[0])
    monkeypatch.setattr(native, "process_identity", lambda pid: owner.identity)
    monkeypatch.setattr(s4_ax.computer_ax, "ax_focused_pid", lambda: 42)
    monkeypatch.setattr(s4_ax.computer_ax, "_load_ax", lambda: {})
    monkeypatch.setattr(owner, "windows", lambda: [{"kCGWindowNumber": w} for w in window_ids])
    monkeypatch.setattr(s4_ax, "pump", lambda *args: None)
    def kill(pid, sig):
        signals.append(pid)
        alive[0] = False
    monkeypatch.setattr(s4_ax.os, "kill", kill)
    # The launch callback established process ownership, but setup/timeout failed
    # before assigning window_id. That one new window must not leak its process.
    if len(window_ids) > 1:
        with pytest.raises(RuntimeError, match="Unowned window"):
            owner.close()
        assert not signals
    else:
        assert owner.close()["confirmed"]
        assert signals == [42]


async def test_native_foreground_lost_at_dispatch_is_known_not_sent(world, monkeypatch):
    from agent_computer_use.channels import native
    from agent_computer_use.factory import create_subagent
    from tank_backend.agents.subagent import SubAgentStopped

    agent = create_subagent({"macos": native_config()})
    agent.controller.selector = Select()
    original = agent.controller.executor.is_current
    async def preflight(*args):
        result = await original(*args)
        def lost(config):
            raise SubAgentStopped("foreground_changed")
        monkeypatch.setattr(native, "read_window", lost)
        return result
    monkeypatch.setattr(agent.controller.executor, "is_current", preflight)
    ctx = context()
    try:
        outputs = [o async for o in agent.run(
            SubAgentRequest("Increment", "", "task", goal().model_dump(mode="json")), ctx)]
        result = outputs[-1].metadata["task_result"]
        assert result["status"] == "stopped"
        assert result["details"]["receipts"][0]["status"] == "not_sent"
        assert not world.sent
    finally:
        await agent.aclose()
        await ctx.runtime.aclose()


async def test_pilot_records_sdk_failure_before_unknown_usage_stop(world, monkeypatch, tmp_path):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    import json
    import httpx2
    from benchmarks.computer_use import s4_ax
    from agent_computer_use.channels.native import NativeConfig
    from tank_backend.benchmarks.desktop_cleanup import MacOSInputCleanup

    class Owner:
        setup_actions = []
        def __init__(self, case):
            pass
        def start(self):
            return NativeConfig.model_validate_json(json.dumps(native_config()))
        def read_values(self):
            return {"result": world.value}
        def close(self):
            return {"confirmed": True}
    monkeypatch.setattr(s4_ax, "OwnedApplication", Owner)
    monkeypatch.setattr(s4_ax, "task_goal", lambda case: goal().model_dump(mode="json"))
    monkeypatch.setattr(MacOSInputCleanup, "_state", staticmethod(lambda: ([], [])))
    monkeypatch.setattr(MacOSInputCleanup, "_release", lambda self: {"errors": []})
    original_http = s4_ax.fake_model_http
    requests = []
    async def fail(request):
        requests.append(request)
        return httpx2.Response(503, json={"error": "private-error-body"})
    monkeypatch.setattr(s4_ax, "fake_model_http", lambda respond: original_http(fail))
    output = tmp_path / "pilot"
    frozen = s4_ax.prepare(output)
    result = await s4_ax.run_batch(output, frozen["sha256"], mode="fake")
    row = result["rows"][0]
    errors = [e for e in row["events"] if e["kind"] == "decision_error"]
    assert len(errors) == 1 and errors[0]["http_status"] == 503
    assert errors[0]["error_type"] == "TypeSafeInternalServerError"
    assert errors[0]["call_id"] in result["spend"]["requests"]
    assert result["spend"]["stop_reason"] == "unknown_usage"
    assert len(requests) == 1 and not world.sent
    assert not row["passed"] and row["application_cleanup"]["confirmed"]
    assert all(r["status"] == "not_run" for r in result["rows"][1:])
    assert "private-error-body" not in (output / "result.json").read_text()


async def test_native_model_view_compacts_references_without_dropping_candidates(world):
    import json
    from dataclasses import asdict
    from agent_computer_use.action_builder import ActionBuilder
    from agent_computer_use.channels.native import NativeAXChannel, NativeConfig
    from agent_computer_use.contracts import snapshot_json
    from agent_computer_use.jev import decision_question

    world.buttons = [replace(world.button, index=i, title=str(i), identifier=str(i),
                             element=AXElementRef(object(), False, 80)) for i in range(54)]
    channel = NativeAXChannel(NativeConfig.model_validate_json(json.dumps(native_config())))
    ctx = context()
    ctx.runtime.bind("task")
    try:
        snapshot = await channel.observe("counter", ctx)
        original = snapshot_json(snapshot)
        actions = ActionBuilder(max_candidates=64).build("increment", 1, goal(), snapshot)
        question = json.loads(json.dumps(decision_question(goal(), snapshot, actions)))
        state = question["state"]
        criteria = question["questions"]["next_action"]["criteria"]
        assert set(criteria) == {a.id for a in actions.actions} | {
            "none", "ambiguous", "need_more_context", "escalate"}
        elements = {e["ref"]: {**state["snapshot"]["element_defaults"], **e}
                    for e in state["snapshot"]["elements"]}
        for action in actions.actions:
            candidate = criteria[action.id]
            element = elements[candidate["target_ref"]]
            old = next(e for e in snapshot.elements if e.ref == action.target_ref)
            assert (element["label"], element["role"], element["enabled"], element["value"]) == (
                old.label, old.role, old.enabled, old.value)
            assert candidate["operation"] == action.operation
            for change in candidate["changes"]:
                assert elements[change["source_ref"]]["value"] == change["before"]
        assert snapshot_json(snapshot) == original  # execution keeps original references
        old_bytes = len(json.dumps({"snapshot": original, "criteria": [
            {**asdict(a), **asdict(d)} for a, d in zip(actions.actions, actions.details)]}))
        new_bytes = len(json.dumps({"snapshot": state["snapshot"], "criteria": criteria}))
        assert new_bytes < old_bytes * 0.7
    finally:
        await channel.aclose()
        await ctx.runtime.aclose()
