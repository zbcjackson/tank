"""Input cleanup uses real lifecycle code with only Quartz replaced."""
import asyncio
from unittest.mock import MagicMock

import pytest


@pytest.mark.parametrize("stuck", [False, True])
async def test_cleanup_releases_and_verifies_inputs(monkeypatch, stuck):
    from tank_backend.benchmarks.desktop_cleanup import MacOSInputCleanup
    from tank_backend.tools import computer_use_macos as macos

    keys, buttons = set(), set()
    quartz = MagicMock()
    quartz.CGEventSourceKeyState.side_effect = lambda _, key: key in keys
    quartz.CGEventSourceButtonState.side_effect = lambda _, button: button in buttons
    quartz.CGEventCreateKeyboardEvent.side_effect = lambda _, key, down: ("key", key)
    quartz.CGEventCreateMouseEvent.side_effect = lambda _, kind, pos, button: ("mouse", button)

    def post(_, event):
        if not stuck:
            (keys if event[0] == "key" else buttons).discard(event[1])

    quartz.CGEventPost.side_effect = post
    monkeypatch.setattr(macos, "_load_quartz", lambda: quartz)
    cleanup = MacOSInputCleanup()
    await cleanup.begin()
    keys.update({9, 55})
    buttons.add(0)
    result = await cleanup.finish()
    assert result["confirmed"] is (not stuck)
    assert result["keys_before"] == [9, 55]
    assert result["buttons_before"] == [0]
    assert result["keys_after"] == ([9, 55] if stuck else [])


async def test_cleanup_refuses_initially_held_user_input(monkeypatch):
    from tank_backend.benchmarks.desktop_cleanup import MacOSInputCleanup
    from tank_backend.tools import computer_use_macos as macos

    quartz = MagicMock()
    quartz.CGEventSourceKeyState.side_effect = lambda _, key: key == 55
    quartz.CGEventSourceButtonState.return_value = False
    monkeypatch.setattr(macos, "_load_quartz", lambda: quartz)
    with pytest.raises(RuntimeError, match="already held"):
        await MacOSInputCleanup().begin()
    quartz.CGEventPost.assert_not_called()


async def test_cancel_waits_for_native_work_even_after_second_cancel():
    import threading

    from tank_backend.tools.computer_native import run_native

    entered, release = threading.Event(), threading.Event()
    def work():
        entered.set()
        assert release.wait(5)
    pending = asyncio.create_task(run_native(work))
    assert await asyncio.to_thread(entered.wait, 2)
    pending.cancel()
    await asyncio.sleep(0)
    pending.cancel()
    await asyncio.sleep(0)
    assert not pending.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await pending


@pytest.mark.parametrize(
    "ending", ["normal", "error", "timeout", "cancel", "cleanup_failed", "cleanup_error"],
)
async def test_runner_cleanup_under_lock_and_driver_result(tmp_path, monkeypatch, ending):
    from typing import Any, cast

    from tank_backend.agents.base import AgentOutput, AgentOutputType
    from tank_backend.agents.definition import AgentDefinition
    from tank_backend.agents.resources import DesktopResource
    from tank_backend.agents.runner import AgentRunner
    from tank_backend.benchmarks.desktop_cleanup import MacOSInputCleanup
    from tank_backend.benchmarks.driver import CountingLLM, SubAgentDriver
    from tank_backend.benchmarks.trace import TraceSink

    resource = DesktopResource()
    runner = AgentRunner.__new__(AgentRunner)
    runner._desktop_resource = resource
    monkeypatch.setattr(runner, "_uses_desktop", lambda _: True)
    events = []
    entered = asyncio.Event()

    async def begin(self):
        assert resource.lock.locked()
        events.append("begin")

    async def finish(self):
        assert resource.lock.locked()
        assert events[-1] == "joined"
        events.append("cleanup")
        if ending == "cleanup_error":
            raise RuntimeError("native cleanup failed")
        return {"confirmed": ending != "cleanup_failed", "keys_after": []}

    async def outputs(*args, **kwargs):
        entered.set()
        try:
            if ending in {"timeout", "cancel"}:
                await asyncio.Event().wait()
            if ending == "error":
                raise RuntimeError("model failed")
            yield AgentOutput(AgentOutputType.DONE)
        finally:
            events.append("joined")

    monkeypatch.setattr(runner, "_run_agent", outputs)
    monkeypatch.setattr(MacOSInputCleanup, "begin", begin)
    monkeypatch.setattr(MacOSInputCleanup, "finish", finish)
    driver = SubAgentDriver(runner, AgentDefinition("test", "", ""),
                            CountingLLM(MagicMock()), cast(Any, MagicMock()), input_cleanup=True)
    trace = TraceSink(tmp_path)
    pending = asyncio.create_task(driver.run("test", trace, timeout_s=1, max_steps=2))
    await entered.wait()
    if ending == "cancel":
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    else:
        result = await pending
        failed = ending in {"cleanup_failed", "cleanup_error"}
        assert result.cleanup == ("unconfirmed" if failed else "confirmed")
        assert result.timed_out is (ending == "timeout")
    assert events == ["begin", "joined", "cleanup"]
    assert not resource.lock.locked()
    if ending in {"cleanup_failed", "cleanup_error"}:
        with pytest.raises(RuntimeError, match="quarantined"):
            async with resource.acquire():
                pass
    trace.close()


@pytest.mark.parametrize("hard_exit", [False, True])
def test_supervisor_recovers_durable_baseline_after_child_exit(monkeypatch, tmp_path, hard_exit):
    import json
    import sys

    from tank_backend.benchmarks import desktop_recovery

    baseline = {"clipboard": [["kind", "private-data"]], "input_source": "original"}
    calls = []
    monkeypatch.setattr(desktop_recovery, "capture_desktop", lambda: baseline)

    def restore(saved):
        calls.append(saved)
        return {"confirmed": True}

    monkeypatch.setattr(desktop_recovery, "restore_desktop", restore)
    directory = tmp_path / "recovery"
    script = (
        "import json, pathlib, os, signal\n"
        f"p=pathlib.Path({str(directory)!r})\n"
        f"assert json.loads((p/'baseline.json').read_text())=={baseline!r}\n"
        "assert json.loads((p/'child.json').read_text())['pid']==os.getpid()\n"
    )
    if hard_exit:
        script += "os.kill(os.getpid(), signal.SIGKILL)\n"
    result = desktop_recovery.supervise([sys.executable, "-c", script], directory, timeout=5)
    assert result["child_returncode"] == (-9 if hard_exit else 0)
    assert result["recovery"] == {"confirmed": True}
    assert calls == [baseline]
    assert (directory / "baseline.json").stat().st_mode & 0o777 == 0o600
    assert directory.stat().st_mode & 0o777 == 0o700
    assert json.loads((directory / "result.json").read_text()) == result


def test_supervisor_timeout_reaps_child_before_restore(monkeypatch, tmp_path):
    import json
    import os
    import sys

    from tank_backend.benchmarks import desktop_recovery

    directory = tmp_path / "recovery"
    monkeypatch.setattr(desktop_recovery, "capture_desktop", lambda: {})

    def restore(_):
        pid = json.loads((directory / "child.json").read_text())["pid"]
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
        return {"confirmed": True}

    monkeypatch.setattr(desktop_recovery, "restore_desktop", restore)
    result = desktop_recovery.supervise(
        [sys.executable, "-c", "import time; time.sleep(30)"], directory, timeout=0.2,
    )
    assert result["timed_out"] is True
    assert result["child_returncode"] == -9


def test_supervisor_refuses_mutation_without_durable_baseline(monkeypatch, tmp_path):
    import sys

    from tank_backend.benchmarks import desktop_recovery

    monkeypatch.setattr(desktop_recovery, "capture_desktop", lambda: {})
    def fail_sync(_):
        raise OSError("disk")

    monkeypatch.setattr(desktop_recovery.os, "fsync", fail_sync)
    marker = tmp_path / "launched"
    with pytest.raises(OSError, match="disk"):
        desktop_recovery.supervise(
            [sys.executable, "-c", f"open({str(marker)!r},'w').close()"],
            tmp_path / "recovery", timeout=5,
        )
    assert not marker.exists()


def test_supervisor_records_recovery_failure_without_claiming_success(monkeypatch, tmp_path):
    import json
    import sys

    from tank_backend.benchmarks import desktop_recovery

    monkeypatch.setattr(desktop_recovery, "capture_desktop", lambda: {})

    def restore(_):
        raise RuntimeError("native unavailable")

    monkeypatch.setattr(desktop_recovery, "restore_desktop", restore)
    directory = tmp_path / "recovery"
    result = desktop_recovery.supervise([sys.executable, "-c", "pass"], directory, timeout=5)
    assert result["recovery"] == {"confirmed": False, "error": "RuntimeError"}
    assert json.loads((directory / "result.json").read_text()) == result


def test_recovery_captures_accessory_front_app(monkeypatch):
    """A menu-bar/accessory front app also needs a durable identity."""
    from tank_backend.benchmarks import desktop_recovery

    kit, quartz, front = MagicMock(), MagicMock(), MagicMock()
    kit.NSApplicationActivationPolicyRegular = 0
    front.activationPolicy.return_value = 1
    front.processIdentifier.return_value = 123
    front.bundleIdentifier.return_value = "test.accessory"
    front.launchDate.return_value.timeIntervalSince1970.return_value = 42.0
    front.isHidden.return_value = False
    workspace = kit.NSWorkspace.sharedWorkspace.return_value
    workspace.frontmostApplication.return_value = front
    workspace.runningApplications.return_value = [front]
    monkeypatch.setattr(desktop_recovery, "_appkit", lambda: kit)
    monkeypatch.setattr(desktop_recovery.importlib, "import_module", lambda _: quartz)
    monkeypatch.setattr(desktop_recovery.MacOSInputCleanup, "_state", lambda: ([], []))
    monkeypatch.setattr(desktop_recovery, "_request", lambda _: "original")
    monkeypatch.setattr(desktop_recovery, "_clipboard", lambda _: [])
    baseline = desktop_recovery.capture_desktop()
    assert baseline["apps"] == [
        {"pid": 123, "bundle": "test.accessory", "launched": 42.0, "hidden": False},
    ]
    assert baseline["front_pid"] == 123


def test_recovery_refuses_unrestorable_front_before_launch(monkeypatch):
    from tank_backend.benchmarks import desktop_recovery

    kit = MagicMock()
    workspace = kit.NSWorkspace.sharedWorkspace.return_value
    front = workspace.frontmostApplication.return_value
    front.bundleIdentifier.return_value = "com.apple.loginwindow"
    monkeypatch.setattr(desktop_recovery, "_appkit", lambda: kit)
    monkeypatch.setattr(desktop_recovery.importlib, "import_module", lambda _: MagicMock())
    monkeypatch.setattr(desktop_recovery.MacOSInputCleanup, "_state", lambda: ([], []))
    monkeypatch.setattr(desktop_recovery, "_request", lambda _: "original")
    with pytest.raises(RuntimeError, match="restorable front app"):
        desktop_recovery.capture_desktop()


def test_recovery_refreshes_cached_front_before_capture(monkeypatch):
    from tank_backend.benchmarks import desktop_recovery

    kit, quartz, foundation, app, stale = [MagicMock() for _ in range(5)]
    kit.NSApplicationActivationPolicyRegular = 0
    app.activationPolicy.return_value = 0
    app.processIdentifier.return_value = 123
    app.bundleIdentifier.return_value = "test.front"
    app.launchDate.return_value.timeIntervalSince1970.return_value = 42.0
    app.isHidden.return_value = False
    stale.bundleIdentifier.return_value = "com.apple.loginwindow"
    refreshed = False

    def pump(_):
        nonlocal refreshed
        refreshed = True

    foundation.NSRunLoop.currentRunLoop.return_value.runUntilDate_.side_effect = pump
    workspace = kit.NSWorkspace.sharedWorkspace.return_value
    workspace.frontmostApplication.side_effect = lambda: app if refreshed else stale
    workspace.runningApplications.return_value = [app]
    monkeypatch.setattr(desktop_recovery, "_appkit", lambda: kit)
    monkeypatch.setattr(desktop_recovery.importlib, "import_module",
                        lambda name: foundation if name == "Foundation" else quartz)
    monkeypatch.setattr(desktop_recovery.MacOSInputCleanup, "_state", lambda: ([], []))
    monkeypatch.setattr(desktop_recovery, "_request", lambda _: "original")
    monkeypatch.setattr(desktop_recovery, "_clipboard", lambda _: [])
    assert desktop_recovery.capture_desktop()["front_pid"] == 123


@pytest.mark.parametrize("updates_delivered", [True, False])
def test_recovery_verifies_visibility_after_runloop(monkeypatch, updates_delivered):
    from tank_backend.benchmarks import desktop_recovery

    kit, quartz, foundation, app = [MagicMock() for _ in range(4)]
    app.processIdentifier.return_value = 123
    app.bundleIdentifier.return_value = "test.front"
    app.launchDate.return_value.timeIntervalSince1970.return_value = 42.0
    hidden, requested_hidden = True, True

    def unhide():
        nonlocal requested_hidden
        requested_hidden = False
        return True  # Request acceptance alone is not proof of restored state.

    def pump(_):
        nonlocal hidden
        if updates_delivered:
            hidden = requested_hidden

    app.unhide.side_effect = unhide
    app.isHidden.side_effect = lambda: hidden
    foundation.NSRunLoop.currentRunLoop.return_value.runUntilDate_.side_effect = pump
    workspace = kit.NSWorkspace.sharedWorkspace.return_value
    workspace.runningApplications.return_value = [app]
    kit.NSRunningApplication.runningApplicationWithProcessIdentifier_.return_value = app
    point = quartz.CGEventGetLocation.return_value
    point.x, point.y = 0, 0
    monkeypatch.setattr(desktop_recovery, "_appkit", lambda: kit)
    monkeypatch.setattr(desktop_recovery.importlib, "import_module",
                        lambda name: foundation if name == "Foundation" else quartz)
    monkeypatch.setattr(desktop_recovery.MacOSInputCleanup, "_state", lambda: ([], []))
    monkeypatch.setattr(desktop_recovery.MacOSInputCleanup, "_release", lambda _: {"errors": []})
    monkeypatch.setattr(desktop_recovery, "_request", lambda *args: "original")
    monkeypatch.setattr(desktop_recovery, "_clipboard", lambda _: [])
    baseline = {"apps": [{"pid": 123, "bundle": "test.front", "launched": 42.0,
                          "hidden": False}], "front_pid": None,
                "clipboard": [], "mouse": [0, 0], "input_source": "original"}
    result = desktop_recovery.restore_desktop(baseline)
    assert result["applications_restored"] is updates_delivered
    assert result["confirmed"] is updates_delivered
    assert result["input_source_restored"] is True


@pytest.mark.parametrize("same_process", [True, False])
def test_recovery_preserves_front_without_appkit_launch_date(monkeypatch, same_process):
    from tank_backend.benchmarks import desktop_recovery

    kit, quartz, app = [MagicMock() for _ in range(3)]
    kit.NSApplicationActivationPolicyRegular = 0
    app.activationPolicy.return_value = 0
    app.processIdentifier.return_value = 123
    app.bundleIdentifier.return_value = "com.apple.finder"
    app.launchDate.return_value = None
    app.isHidden.return_value = False
    workspace = kit.NSWorkspace.sharedWorkspace.return_value
    workspace.frontmostApplication.return_value = app
    workspace.runningApplications.return_value = [app]
    monkeypatch.setattr(desktop_recovery, "_appkit", lambda: kit)
    monkeypatch.setattr(desktop_recovery.importlib, "import_module", lambda _: quartz)
    monkeypatch.setattr(desktop_recovery.MacOSInputCleanup, "_state", lambda: ([], []))
    monkeypatch.setattr(desktop_recovery, "_request", lambda *args: "original")
    monkeypatch.setattr(desktop_recovery, "_clipboard", lambda _: [])
    stamp = "Thu Sep 24 09:00:00 2026\n"
    monkeypatch.setattr(desktop_recovery.subprocess, "run",
                        lambda *args, **kwargs: MagicMock(stdout=stamp))
    baseline = desktop_recovery.capture_desktop()
    assert baseline["front_pid"] == 123
    assert baseline["apps"] == [{"pid": 123, "bundle": "com.apple.finder",
                                  "launched": "ps:Thu Sep 24 09:00:00 2026", "hidden": False}]
    if not same_process:
        stamp = "Thu Sep 24 10:00:00 2026\n"
    kit.NSRunningApplication.runningApplicationWithProcessIdentifier_.return_value = app
    quartz.CGEventGetLocation.return_value.x = 0
    quartz.CGEventGetLocation.return_value.y = 0
    baseline["mouse"] = [0, 0]
    monkeypatch.setattr(desktop_recovery.MacOSInputCleanup, "_release", lambda _: {"errors": []})
    restored = desktop_recovery.restore_desktop(baseline)
    assert restored["front_restored"] is same_process
    assert restored["confirmed"] is same_process
    if not same_process:
        app.activateWithOptions_.assert_not_called()
        app.hide.assert_not_called()
        app.unhide.assert_not_called()


def test_recovery_reissues_activation_until_the_app_is_front(monkeypatch):
    """A dropped activation request must be retried, not reported as restored."""
    from tank_backend.benchmarks import desktop_recovery

    kit, quartz, foundation = MagicMock(), MagicMock(), MagicMock()
    kit.NSApplicationActivationPolicyRegular = 0
    app = MagicMock()
    other = MagicMock()
    app.processIdentifier.return_value = 123
    app.bundleIdentifier.return_value = "test.front"
    app.launchDate.return_value.timeIntervalSince1970.return_value = 42.0
    app.isHidden.return_value = False
    state = {"front": False, "requests": 0, "dispatched": 0}

    def activate(_):
        state["requests"] += 1

    def pump(_):
        # First activation request is dropped; a re-issued one is dispatched.
        if not state["front"] and state["requests"] > state["dispatched"] + 1:
            state["front"] = True
            state["dispatched"] = state["requests"]

    app.activateWithOptions_.side_effect = activate
    foundation.NSRunLoop.currentRunLoop.return_value.runUntilDate_.side_effect = pump
    workspace = kit.NSWorkspace.sharedWorkspace.return_value
    workspace.runningApplications.return_value = [app]
    workspace.frontmostApplication.side_effect = lambda: app if state["front"] else other
    kit.NSRunningApplication.runningApplicationWithProcessIdentifier_.return_value = app
    point = quartz.CGEventGetLocation.return_value
    point.x, point.y = 0, 0
    monkeypatch.setattr(desktop_recovery, "_appkit", lambda: kit)
    monkeypatch.setattr(desktop_recovery.importlib, "import_module",
                        lambda name: foundation if name == "Foundation" else quartz)
    monkeypatch.setattr(desktop_recovery.MacOSInputCleanup, "_state", lambda: ([], []))
    monkeypatch.setattr(desktop_recovery.MacOSInputCleanup, "_release", lambda _: {"errors": []})
    monkeypatch.setattr(desktop_recovery, "_request", lambda *args: "original")
    monkeypatch.setattr(desktop_recovery, "_clipboard", lambda _: [])
    baseline = {"apps": [{"pid": 123, "bundle": "test.front", "launched": 42.0,
                          "hidden": False}], "front_pid": 123, "clipboard": [],
                "mouse": [0, 0], "input_source": "original"}
    result = desktop_recovery.restore_desktop(baseline)
    assert result["front_restored"] is True
    assert result["confirmed"] is True
    assert app.activateWithOptions_.call_count >= 2


def test_recovery_hides_and_verifies_without_trusting_the_return_value(monkeypatch):
    """hide() returns False on macOS 26 and drops unpumped requests."""
    from tank_backend.benchmarks import desktop_recovery

    app = MagicMock()
    app.processIdentifier.return_value = 123
    app.bundleIdentifier.return_value = "test.front"
    app.launchDate.return_value.timeIntervalSince1970.return_value = 42.0
    state = {"hidden": False, "requests": 0, "dispatched": 0}

    def hide():
        state["requests"] += 1
        return False  # observed on macOS 26 even when hiding succeeds

    def pump(_):
        # First request is dropped; a re-issued request is dispatched.
        if state["requests"] > state["dispatched"] + 1:
            state["hidden"] = True
            state["dispatched"] = state["requests"]

    kit, quartz, foundation = MagicMock(), MagicMock(), MagicMock()
    foundation.NSRunLoop.currentRunLoop.return_value.runUntilDate_.side_effect = pump
    kit.NSRunningApplication.runningApplicationWithProcessIdentifier_.return_value = app
    monkeypatch.setattr(desktop_recovery, "_appkit", lambda: kit)
    monkeypatch.setattr(desktop_recovery.importlib, "import_module",
                        lambda name: foundation if name == "Foundation" else quartz)
    monkeypatch.setattr(desktop_recovery.MacOSInputCleanup, "_release", lambda _: {"errors": []})
    monkeypatch.setattr(desktop_recovery, "_request", lambda *args: "original")
    monkeypatch.setattr(desktop_recovery, "_clipboard", lambda _: [])
    app.hide.side_effect = hide
    app.isHidden.side_effect = lambda: state["hidden"]
    point = quartz.CGEventGetLocation.return_value
    point.x, point.y = 0, 0
    baseline = {"apps": [{"pid": 123, "bundle": "test.front", "launched": 42.0,
                          "hidden": True}], "front_pid": None, "clipboard": [],
                "mouse": [0, 0], "input_source": "original"}
    result = desktop_recovery.restore_desktop(baseline)
    assert result["applications_restored"] is True
    assert state["hidden"] is True
    assert app.hide.call_count >= 2
