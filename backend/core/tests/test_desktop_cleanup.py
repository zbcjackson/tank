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
