"""S2 acceptance with real ephemeral Chromium and controlled loopback pages."""

import asyncio
import html as html_module
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from agent_computer_use.contracts import GoalContract
from agent_computer_use.action_builder import ActionBuilder
from tank_backend.agents.subagent import (
    SubAgentAuthorization, SubAgentBudget, SubAgentContext, SubAgentRequest,
)


@pytest.fixture
async def site() -> AsyncIterator[str]:
    html = b'''<label>Name <input id="name"></label>
        <button onclick="document.querySelector('[role=status]').textContent =
        document.querySelector('input').value">Save</button>
        <div role="status" aria-label="Result">empty</div>'''

    async def respond(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = await reader.readuntil(b"\r\n\r\n")
        body = html
        if request.startswith(b"GET /frame"):
            child = html.decode()
            if b"/frame-nested" in request.splitlines()[0]:
                child += '<iframe></iframe>'
            body = ('<iframe name="bound" srcdoc="' + html_module.escape(child, quote=True)
                    + '"></iframe>').encode()
            if b"/frame-duplicate" in request.splitlines()[0]:
                body += body
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                     + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(respond, "127.0.0.1", 0)
    try:
        yield f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/"
    finally:
        server.close()
        await server.wait_closed()


@pytest.fixture
async def chromium_required() -> None:
    if os.environ.get("TANK_REQUIRE_CHROMIUM") == "1":
        __import__("playwright.async_api")
    else:
        pytest.importorskip("playwright.async_api")
    from playwright.async_api import async_playwright
    async with async_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            if os.environ.get("TANK_REQUIRE_CHROMIUM") == "1":
                pytest.fail("Required Chromium is not installed")
            pytest.skip("Optional Chromium is not installed")


def context() -> SubAgentContext:
    ctx = SubAgentContext(SubAgentAuthorization(frozenset({"desktop", "network"})),
                          SubAgentBudget(), asyncio.Event())
    ctx.runtime.bind("dom-task")
    return ctx


def goal() -> GoalContract:
    return GoalContract.from_input({
        "schema_version": 1, "objective": "Save name", "scope": "managed-page",
        "inputs": [{"key": "name", "value": "小明"}],
        "milestones": [
            {"id": "fill", "operation": "fill", "role": "textbox", "label": "Name",
             "input_key": "name", "postcondition": {"key": "textbox:Name", "value": "小明"}},
            {"id": "save", "operation": "click", "role": "button", "label": "Save",
             "postcondition": {"key": "status:Result", "value": "小明"}},
        ], "completion": [{"key": "status:Result", "value": "小明"}],
    })


async def test_managed_chromium_fill_click_readback(site: str, chromium_required: None) -> None:
    from agent_computer_use.factory import create_subagent

    agent = create_subagent({"browser": {"scope": "managed-page", "url": site}})
    ctx = context()
    try:
        outputs = [output async for output in agent.run(
            SubAgentRequest("Save name", "", "dom-task", goal().model_dump(mode="json")), ctx)]
        assert outputs[-1].metadata["task_result"]["status"] == "completed", outputs[-1]
        assert len(agent.controller.receipts) == 2
        assert all(receipt.status == "sent" for receipt in agent.controller.receipts)
        assert ctx.budget.total_tokens == 0
    finally:
        await agent.aclose()
        await ctx.runtime.aclose()


@pytest.fixture
async def channel(site: str, chromium_required: None):
    from agent_computer_use.channels.dom import BrowserConfig, ManagedChromiumChannel

    channel = ManagedChromiumChannel(BrowserConfig(scope="managed-page", url=site))
    ctx = context()
    try:
        await channel.observe("managed-page", ctx)
        yield channel, ctx
    finally:
        await channel.aclose()
        await ctx.runtime.aclose()


async def actions(channel, ctx, index=1):
    snapshot = await channel.observe("managed-page", ctx)
    contract = goal()
    return ActionBuilder().build("goal", 1, contract, contract.milestones[index], snapshot)


@pytest.mark.parametrize("change", ["replace", "navigate", "disabled", "label", "new_observation"])
async def test_old_reference_never_dispatches(channel, change: str) -> None:
    browser, ctx = channel
    selected = await actions(browser, ctx)
    page = browser.page
    assert page is not None
    if change == "navigate":
        await page.reload()
    elif change == "new_observation":
        await browser.observe("managed-page", ctx)
    else:
        await page.locator("button").evaluate({
            "replace": "el => el.replaceWith(el.cloneNode(true))",
            "disabled": "el => el.disabled = true",
            "label": "el => el.textContent = 'Other'",
        }[change])
    assert not await browser.is_current(selected.binding, selected.actions[0], ctx)
    receipt = await browser.dispatch(selected.binding, selected.actions[0], ctx)
    assert receipt.status == "not_sent"
    assert await page.get_by_role("status").text_content() == "empty"


@pytest.mark.parametrize("operation", [0, 1])
async def test_overlay_blocks_fill_and_click(channel, operation: int) -> None:
    browser, ctx = channel
    page = browser.page
    assert page is not None
    await page.evaluate("""() => { const el = document.createElement('div');
        el.style = 'position:fixed;inset:0;z-index:99;background:white';
        document.body.append(el); }""")
    selected = await actions(browser, ctx, operation)
    receipt = await browser.dispatch(selected.binding, selected.actions[0], ctx)
    assert receipt.status == "not_sent"
    assert await page.locator("input").input_value() == ""
    assert await page.get_by_role("status").text_content() == "empty"


async def test_duplicate_disabled_and_bounded_dom(channel) -> None:
    browser, ctx = channel
    page = browser.page
    assert page is not None
    await page.locator("button").evaluate("el => el.after(el.cloneNode(true))")
    assert (await actions(browser, ctx)).reason == "ambiguous_target"
    await page.locator("button").evaluate_all("els => els.forEach(el => el.disabled = true)")
    assert not (await actions(browser, ctx)).actions
    await page.evaluate("""() => { for(let i=0;i<300;i++) {
        const el=document.createElement('button'); el.textContent='Save';
        document.body.append(el); } }""")
    selected = await actions(browser, ctx)
    assert selected.reason == "scope_incomplete" and not selected.actions


async def test_same_url_tab_is_not_selected_and_disconnect_does_not_reattach(channel) -> None:
    from tank_backend.agents.subagent import SubAgentStopped

    browser, ctx = channel
    original = browser.page
    assert original is not None
    second = await original.context.new_page()
    await second.route("**/*", lambda route: route.fulfill(
        content_type="text/html", body='<button>Save</button><div role="status">second</div>'))
    await second.goto(original.url)
    assert second.url == original.url
    selected = await actions(browser, ctx)
    assert (await browser.dispatch(selected.binding, selected.actions[0], ctx)).status == "sent"
    assert browser.page is original
    assert await original.get_by_role("status").text_content() == ""
    assert await second.get_by_role("status").text_content() == "second"
    await original.close()
    with pytest.raises(SubAgentStopped, match="page_closed"):
        await browser.observe("managed-page", ctx)
    assert browser.page is original


@pytest.mark.parametrize("case", ["frame", "frame-nested", "frame-duplicate", "unbound"])
async def test_frame_scope_and_real_iframe_closed_loop(site, chromium_required, case) -> None:
    from agent_computer_use.factory import create_subagent

    config = {"scope": "managed-page", "url": site + ("frame" if case == "unbound" else case)}
    if case != "unbound":
        config["frame_name"] = "bound"
    agent = create_subagent({"browser": config})
    ctx = context()
    try:
        outputs = [output async for output in agent.run(
            SubAgentRequest("Save", "", "dom-task", goal().model_dump(mode="json")), ctx)]
        result = outputs[-1].metadata["task_result"]
        if case == "frame":
            assert result["status"] == "completed", result
            assert len(agent.controller.receipts) == 2
        else:
            assert result["reason"] == "frame_ambiguous", result
            assert not agent.controller.receipts
    finally:
        await agent.aclose()
        await ctx.runtime.aclose()


@pytest.mark.parametrize("stop", ["revoke", "cancel", "deadline", "budget"])
async def test_stop_during_pending_native_click_has_no_late_input(channel, monkeypatch, stop) -> None:
    from playwright.async_api import Locator
    from tank_backend.agents.subagent import SubAgentStopped

    browser, ctx = channel
    page = browser.page
    assert page is not None
    inputs = []
    await page.expose_function("recordInput", lambda: inputs.append("click"))
    await page.locator("button").evaluate("el => el.onclick = () => window.recordInput()")
    selected = await actions(browser, ctx)
    started = asyncio.Event()
    real_click = Locator.click

    async def click(locator, **kwargs):
        if not kwargs.get("trial"):
            await page.evaluate("""() => { const el = document.createElement('div');
                el.id='cover'; el.style='position:fixed;inset:0;z-index:999';
                document.body.append(el); setTimeout(() => el.remove(), 100); }""")
            started.set()
        return await real_click(locator, **kwargs)

    monkeypatch.setattr(Locator, "click", click)
    task = asyncio.create_task(browser.dispatch(selected.binding, selected.actions[0], ctx))
    await asyncio.wait_for(started.wait(), 3)
    if stop == "revoke":
        ctx.authorization.revoke()
    elif stop == "cancel":
        ctx.cancel.set()
    elif stop == "deadline":
        ctx.runtime.restrict_deadline(0)
    else:
        ctx.budget.limit = 1
        ctx.budget.record("stop-call", prompt_tokens=1, completion_tokens=0)
    with pytest.raises((SubAgentStopped, asyncio.CancelledError, TimeoutError)):
        await task
    assert inputs == []
    assert page.is_closed()


@pytest.mark.parametrize("gate", ["actions", "observations", "revoke", "cancel", "budget", "deadline"])
async def test_controller_native_dispatch_uses_shared_runtime(site, chromium_required, gate) -> None:
    from agent_computer_use.channels.dom import ManagedChromiumChannel
    from agent_computer_use.factory import create_subagent
    from tank_backend.agents.subagent import SubAgentCancelled

    ctx = context()
    if gate == "actions":
        ctx.runtime.restrict_operations(actions=0)
    elif gate == "observations":
        ctx.runtime.restrict_operations(observations=0)

    def on_event(kind, metadata):
        if kind == "computer_use_route":
            if gate == "revoke":
                ctx.authorization.revoke()
            elif gate == "cancel":
                ctx.cancel.set()
            elif gate == "budget":
                ctx.budget.limit = 1
                ctx.budget.record("other-call", prompt_tokens=1, completion_tokens=0)
            elif gate == "deadline":
                ctx.runtime.restrict_deadline(0)

    from unittest.mock import Mock
    object.__setattr__(ctx, "observer", Mock(on_event=on_event))
    agent = create_subagent({"browser": {"scope": "managed-page", "url": site}})
    try:
        try:
            outputs = [output async for output in agent.run(
                SubAgentRequest("Save", "", "dom-task", goal().model_dump(mode="json")), ctx)]
            assert outputs[-1].metadata["task_result"]["status"] == "stopped"
        except SubAgentCancelled:
            assert gate == "cancel"
        assert agent.controller.receipts == []
        browser = agent.controller.source
        assert isinstance(browser, ManagedChromiumChannel)
        if gate == "observations":
            assert browser.page is None
        else:
            assert browser.page is not None
            assert await browser.page.locator("input").input_value() == ""
    finally:
        await agent.aclose()
        await ctx.runtime.aclose()


async def test_lost_reply_readback_confirms_effect_without_replay(site, chromium_required, monkeypatch):
    from playwright.async_api import Error, Locator
    from agent_computer_use.factory import create_subagent

    real_click = Locator.click
    sent = []

    async def lose_reply(locator, **kwargs):
        await real_click(locator, **kwargs)
        if not kwargs.get("trial"):
            sent.append(True)
            raise Error("simulated lost response after actual click")

    monkeypatch.setattr(Locator, "click", lose_reply)
    agent = create_subagent({"browser": {"scope": "managed-page", "url": site}})
    ctx = context()
    try:
        outputs = [output async for output in agent.run(
            SubAgentRequest("Save", "", "dom-task", goal().model_dump(mode="json")), ctx)]
        assert outputs[-1].metadata["task_result"]["status"] == "completed", outputs[-1]
        assert len(sent) == 1
        assert [r.status for r in agent.controller.receipts] == ["sent", "unknown"]
    finally:
        await agent.aclose()
        await ctx.runtime.aclose()


async def test_browser_config_through_real_runner(site, chromium_required) -> None:
    from unittest.mock import MagicMock
    from tank_backend.agents.approval import PendingToolCallStore, ToolApprovalPolicy
    from tank_backend.agents.definition import AgentDefinition
    from tank_backend.agents.resources import DesktopResource
    from tank_backend.agents.runner import AgentRunner
    from tank_backend.config.app_config import AppConfig
    from tank_backend.pipeline.bus import Bus
    from tank_backend.plugin.manifest import read_manifest_from_yaml
    from tank_backend.plugin.registry import ExtensionRegistry

    manifest = read_manifest_from_yaml(Path(__file__).parents[1] / "plugin.yaml")
    registry = ExtensionRegistry()
    registry.register(manifest.plugin_name, manifest.extensions[0])
    definition = AgentDefinition("ladder", "test", "Save name", extension="agent-computer-use:agent")
    runner = AgentRunner(MagicMock(), MagicMock(), Bus(), ToolApprovalPolicy(computer_mode="allow"),
                        PendingToolCallStore(), {"ladder": definition}, registry=registry,
                        app_config=AppConfig(subagents={"agent-computer-use:agent": {
                            "browser": {"scope": "managed-page", "url": site}}}),
                        desktop_resource=DesktopResource())
    assert runner.extension_permissions(definition) == frozenset({"desktop", "network"})
    outputs = [output async for output in runner.run_agent(
        definition, [], task_id="dom-task", task_input=goal().model_dump(mode="json"),
        authorization=SubAgentAuthorization(frozenset({"desktop", "network"})),
    )]
    results = [output.metadata["task_result"] for output in outputs if "task_result" in output.metadata]
    assert len(results) == 1 and results[0]["status"] == "completed", outputs
    assert results[0]["cleanup"] == "confirmed"


@pytest.mark.parametrize("shutdown", ["close", "cancel"])
async def test_close_during_driver_creation_releases_late_resource(
    site, chromium_required, monkeypatch, shutdown,
):
    from playwright.async_api import async_playwright
    from agent_computer_use.channels.dom import BrowserConfig, ManagedChromiumChannel
    from tank_backend.agents.subagent import SubAgentStopped

    browser = ManagedChromiumChannel(BrowserConfig(scope="managed-page", url=site))
    started, release = asyncio.Event(), asyncio.Event()
    manager_type = type(async_playwright())
    real_start = manager_type.start
    acquired, stopped, releases = [], [], []

    async def start(manager):
        driver = await real_start(manager)
        acquired.append(driver)
        real_stop = driver.stop
        releases.append(real_stop)

        async def stop():
            stopped.append(driver)
            await real_stop()

        monkeypatch.setattr(driver, "stop", stop)
        started.set()
        await release.wait()
        return driver

    monkeypatch.setattr(manager_type, "start", start)
    ctx = context()
    task = asyncio.create_task(browser.observe("managed-page", ctx))
    try:
        await asyncio.wait_for(started.wait(), 3)
        if shutdown == "cancel":
            task.cancel()
            await asyncio.sleep(0)
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            closing = asyncio.create_task(browser.aclose())
            await asyncio.sleep(0)
            release.set()
            with pytest.raises(SubAgentStopped, match="channel_closed"):
                await task
            await closing
        assert stopped == acquired
        assert browser.browser is None
    finally:
        for cleanup in releases:
            await cleanup()
        await ctx.runtime.aclose()
