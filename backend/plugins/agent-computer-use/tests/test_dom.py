"""S2 acceptance with real ephemeral Chromium and controlled loopback pages."""

import asyncio
import html as html_module
import os
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from agent_computer_use.contracts import GoalContract
from agent_computer_use.action_builder import ActionBuilder
from tank_backend.agents.subagent import (
    SubAgentAuthorization, SubAgentBudget, SubAgentContext, SubAgentRequest,
)


def multilayout_html(layout: str, scenario: str) -> str:
    """Real DOM fixture; page effects are independent of the fake model response."""
    desired_slot = "A" if layout == "table" else "B"
    controls = []
    for slot in ("A", "B"):
        identity = "K7" if slot == desired_slot else "K2"
        effect = f"window.clicks.push('{slot}');"
        if scenario != "no_effect":
            effect += f"document.getElementById('panel{slot}').hidden=false;"
            effect += f"document.querySelector('[aria-label=Result]').textContent='selected:{identity}';"
        button = f'<button aria-controls="panel{slot}" onclick="{effect}">执行 {slot}</button>'
        button += f'<section id="panel{slot}" role="region" aria-label="Effect {slot}" hidden></section>'
        fact = "" if scenario == "missing" else (
            f'<span role="status" aria-label="Identity {slot}">{identity}</span>')
        if layout == "table":
            controls.append(f"<tr><td>{fact}</td><td>{button}</td></tr>")
        else:
            controls.append(f"<section>{fact}{button}</section>")
    report = '<output aria-label="Result">idle</output>'
    if scenario == "conflicting":
        report += f'<output aria-label="Secondary identity {desired_slot}">K2</output>'
    if layout == "toolbar":
        content = '<nav role="toolbar" aria-label="Actions" style="display:flex;gap:60px">' + "".join(controls) + '</nav>' + report
    elif layout == "table":
        content = '<table style="margin:40px;border:1px solid"><tbody>' + "".join(controls) + '</tbody></table>' + report
    else:
        content = '<dialog open style="width:400px">' + "".join(controls) + report + '</dialog>'
    return '<!doctype html><meta charset="utf-8"><script>window.clicks=[];</script>' + content


@pytest.fixture
def profile_store() -> dict[str, str]:
    return {"name": "Bob", "email": "unchanged@example.test", "saves": "0"}


def profile_html(layout: str) -> str:
    entry = "Personal info" if layout == "plain" else "Edit profile"
    destination = "middle" if layout == "middle" else "profile"
    intermediate = '''<section id="middle" role="region" aria-label="Account" hidden>
      <button aria-controls="profile" onclick="middle.hidden=true;profile.hidden=false">Continue</button>
    </section>'''
    return f'''<!doctype html><meta charset="utf-8">
    <section id="home" role="region" aria-label="Home">
      <button aria-controls="{destination}" onclick="home.hidden=true;{destination}.hidden=false">{entry}</button>
      <button aria-controls="notifications" onclick="home.hidden=true;notifications.hidden=false">Notifications</button>
    </section>
    <section id="notifications" role="region" aria-label="Notifications" hidden>Unrelated</section>
    {intermediate if layout == "middle" else ''}
    <form id="profile" aria-label="Profile" hidden style="{'margin:80px;width:400px' if layout != 'plain' else ''}"
      onsubmit="event.preventDefault();saveName()">
      <label>Public name<input id="publicName" value="Bob" oninput="save.disabled=false"></label>
      <button type="button" aria-controls="home" onclick="profile.hidden=true;home.hidden=false">Back</button>
      <button id="save" type="submit" disabled>Save</button>
    </form>
    <output aria-label="Saved name">Bob</output>
    <output aria-label="Saved email">unchanged@example.test</output>
    <script>
    async function saveName() {{
      const result = await (await fetch('/persist?name=' + encodeURIComponent(publicName.value))).json();
      document.querySelector('[aria-label="Saved name"]').textContent=result.name;
      document.querySelector('[aria-label="Saved email"]').textContent=result.email;
      save.disabled=true;
    }}
    </script>'''


@pytest.fixture
async def site(profile_store: dict[str, str]) -> AsyncIterator[str]:
    html = b'''<form onsubmit="event.preventDefault()"><label>Name <input id="name"></label>
        <button onclick="document.querySelector('[role=status]').textContent =
        document.querySelector('input').value">Save</button>
        <div role="status" aria-label="Result">empty</div></form>'''

    async def respond(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = await reader.readuntil(b"\r\n\r\n")
        body = html
        path = urlsplit(request.split(b" ", 2)[1].decode())
        if path.path.startswith("/goal/"):
            body = profile_html(path.path.rsplit("/", 1)[-1]).encode()
        if path.path == "/persist":
            import json

            profile_store["name"] = parse_qs(path.query)["name"][0]
            profile_store["saves"] = str(int(profile_store["saves"]) + 1)
            body = json.dumps(profile_store).encode()
        if request.startswith(b"GET /multilayout/"):
            path = request.split(b" ", 2)[1].decode()
            _, _, layout, scenario = path.split("/")
            body = multilayout_html(layout, scenario).encode()
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
    return GoalContract.from_input({'schema_version': 2, 'objective': 'Save name', 'scope': 'managed-page', 'inputs': [{'key': 'name', 'value': '小明', 'purpose': 'name', 'field_label': 'Name'}], 'completion': [{'key': 'status:Result', 'value': '小明'}], 'goal_id': 'goal', 'intent': 'Save name', 'authorization_ref': 'current_task', 'allowed_operations': ['click', 'fill']})


class SelectOnlyCandidate:
    async def choose(self, goal, snapshot, actions, ctx):
        from agent_computer_use.contracts import DecisionResult

        assert len(actions.actions) == 1
        return DecisionResult(actions.binding, "candidate", actions.actions[0].id)


async def test_managed_chromium_fill_click_readback(site: str, chromium_required: None) -> None:
    from agent_computer_use.factory import create_subagent

    agent = create_subagent({"browser": {"scope": "managed-page", "url": site}})
    agent.controller.selector = SelectOnlyCandidate()
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


@pytest.mark.parametrize("region", ["form", "dialog", "section"])
async def test_goal_dom_observes_form_and_navigation_evidence(channel, region: str) -> None:
    browser, ctx = channel
    page = browser.page
    inner = "div" if region == "form" else "form"
    await page.set_content(f'''
        <span id="profileTitle">Profile</span>
        <button aria-controls="profile" onclick="profile.hidden=false">Personal info</button>
        <{region} id="profile" aria-label="Wrong" aria-labelledby="profileTitle" hidden
          {'open' if region == 'dialog' else 'role="region"' if region == 'section' else ''}>
          <{inner} aria-label="Editor">
          <label>Public name<input value="Bob"></label><button type="submit">Save</button>
          </{inner}>
        </{region}>''')
    snapshot = await browser.observe("managed-page", ctx)
    navigation = next(e for e in snapshot.elements if e.label == "Personal info")
    key = "visible:dialog:Profile" if region == "dialog" else "visible:region:Profile"
    assert navigation.click_effect[0].key == key
    await page.get_by_role("button", name="Personal info").click()
    snapshot = await browser.observe("managed-page", ctx)
    assert any(f.key == key and f.value == "true" for f in snapshot.facts)
    assert any(f.key == key.removeprefix("visible:") and "Save" in f.value
               for f in snapshot.facts)
    field = next(e for e in snapshot.elements if e.role == "textbox")
    assert (region, "Profile") in field.ancestors
    assert next(e for e in snapshot.elements if e.label == "Save").submits


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
    if index == 1:
        contract = contract.model_copy(update={"inputs": (), "allowed_operations": ("click",)})
    else:
        contract = contract.model_copy(update={"allowed_operations": ("fill",)})
    return ActionBuilder().build("goal", 1, contract, snapshot)


async def test_goal_input_binding_does_not_survive_document_reload(channel) -> None:
    from agent_computer_use.contracts import GoalContract, GoalProgress

    browser, ctx = channel
    page = browser.page
    await page.goto(browser.config.url + "goal/plain")
    await page.get_by_role("button", name="Personal info").click()
    await page.get_by_role("textbox", name="Public name").fill("Ada")
    before = await browser.observe("managed-page", ctx)
    original = next(e for e in before.elements if e.role == "textbox")
    progress = GoalProgress(input_bindings=(("name", original.ref),))
    contract = GoalContract.model_validate_json('''{
      "schema_version": 2, "goal_id": "name", "intent": "Save name Ada",
      "objective": "Save name Ada", "scope": "managed-page",
      "authorization_ref": "current_task", "allowed_operations": ["click", "fill"],
      "inputs": [{"key": "name", "purpose": "display name", "value": "Ada"}],
      "completion": [{"key": "status:Saved name", "value": "Ada"}]
    }''')
    assert any(a.operation == "click" and a.target_ref == next(
        e.ref for e in before.elements if e.label == "Save")
        for a in ActionBuilder().build("name", 1, contract, before, progress).actions)
    await page.reload()
    await page.get_by_role("button", name="Personal info").click()
    await page.get_by_role("textbox", name="Public name").fill("Ada")
    after = await browser.observe("managed-page", ctx)
    save = next(e.ref for e in after.elements if e.label == "Save")
    # A new document's coincidentally equal value is not the input we verified.
    assert not any(a.target_ref == save for a in ActionBuilder().build(
        "name", 1, contract, after, progress).actions)
    assert original.ref != next(e.ref for e in after.elements if e.role == "textbox")


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
    agent.controller.selector = SelectOnlyCandidate()
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
    agent.controller.selector = SelectOnlyCandidate()
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
    assert len(results) == 1 and results[0]["status"] == "partial", outputs
    assert results[0]["reason"] == "jev_eligible"
    assert len(results[0]["details"]["receipts"]) == 1
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


async def test_yaml_runner_jev_clicks_and_verifies_real_dom(
    site, chromium_required, monkeypatch, tmp_path,
):
    import json
    from unittest.mock import MagicMock

    import httpx

    from tank_backend.agents.approval import PendingToolCallStore, ToolApprovalPolicy
    from tank_backend.agents.definition import parse_agent_file
    from tank_backend.agents.resources import DesktopResource
    from tank_backend.agents.runner import AgentRunner
    from tank_backend.config.app_config import AppConfig
    from tank_backend.pipeline.bus import Bus
    from tank_backend.plugin.manifest import read_manifest_from_yaml
    from tank_backend.plugin.registry import ExtensionRegistry

    sent, closed, audits = [], [], []
    monkeypatch.setenv("TEST_JEV_KEY", "never-in-plugin-config")

    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            data = json.loads(request.content)
            sent.append(data)
            assert request.headers["authorization"] == "Bearer never-in-plugin-config"
            assert data["state"]["snapshot"]["facts"]
            criteria = data["questions"]["next_action"]["criteria"]
            choice = next(key for key, value in criteria.items() if isinstance(value, dict))
            return httpx.Response(200, json={"model": "jev-1.13.0", "answers": {
                "next_action": {"type": "choice", "choice": choice, "confidence": 1,
                                "probabilities": {key: int(key == choice) for key in criteria}},
            }, "usage": {"input_tokens": 12, "output_tokens": 0}})

        async def aclose(self):
            closed.append(True)

    async def audit(record):
        audits.append(record)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)
    registry = ExtensionRegistry()
    manifest = read_manifest_from_yaml(Path(__file__).parents[1] / "plugin.yaml")
    for extension in manifest.extensions:
        registry.register(manifest.plugin_name, extension)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(f'''llm:
  default:
    api_key: unused
    model: unused
    base_url: https://offline.invalid/v1
decision_models:
  decision:
    url: https://offline.invalid/v1/systemone
    model: jev-1.13.0
    credential_env: TEST_JEV_KEY
subagents:
  agent-computer-use:agent:
    config:
      browser:
        scope: managed-page
        url: {site}
      selector: jev
''')
    definition_path = tmp_path / "agent.md"
    definition_path.write_text('''---
name: ladder
extension: agent-computer-use:agent
decision-model: decision
---
Save name.
''')
    definition = parse_agent_file(definition_path)
    runner = AgentRunner(
        MagicMock(), MagicMock(), Bus(), ToolApprovalPolicy(computer_mode="allow"),
        PendingToolCallStore(), {definition.name: definition}, registry=registry,
        app_config=AppConfig.load(config_path), desktop_resource=DesktopResource(),
    )
    task_goal = goal().model_dump(mode="json")
    task_goal["inputs"] = []
    task_goal["completion"] = [{"key": "status:Result", "value": ""}]
    outputs = [output async for output in runner.run_agent(
        definition, [], task_id="jev-dom", task_input=task_goal,
        authorization=SubAgentAuthorization(frozenset({"desktop", "network"})), audit=audit,
    )]
    results = [out.metadata["task_result"] for out in outputs if "task_result" in out.metadata]
    assert len(results) == 1 and results[0]["status"] == "completed", outputs
    assert results[0]["cleanup"] == "confirmed"
    assert len(sent) == 1 and closed == [True]
    assert not any(record.category == "model" for record in audits)
    assert any(record.operation == "computer_use.dispatch" for record in audits)
    assert "never-in-plugin-config" not in repr(outputs) + repr(audits)


@pytest.mark.parametrize("layout", ["plain", "offset", "middle"])
async def test_goal_runner_sdk_dom_saves_without_a_script(
    site, chromium_required, monkeypatch, tmp_path, profile_store, layout,
):
    import json
    from unittest.mock import MagicMock

    import httpx

    from tank_backend.agents.approval import PendingToolCallStore, ToolApprovalPolicy
    from tank_backend.agents.definition import parse_agent_file
    from tank_backend.agents.resources import DesktopResource
    from tank_backend.agents.runner import AgentRunner
    from tank_backend.config.app_config import AppConfig
    from tank_backend.pipeline.bus import Bus
    from tank_backend.plugin.manifest import read_manifest_from_yaml
    from tank_backend.plugin.registry import ExtensionRegistry

    sent, closed, audits = [], [], []
    monkeypatch.setenv("TEST_JEV_KEY", "never-in-plugin-config")

    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            data = json.loads(request.content)
            sent.append(data)
            assert request.headers["authorization"] == "Bearer never-in-plugin-config"
            assert data["state"]["snapshot"]["facts"]
            criteria = data["questions"]["next_action"]["criteria"]
            options = {key: value for key, value in criteria.items() if isinstance(value, dict)}
            fills = {key: value for key, value in options.items() if value["operation"] == "fill"}
            if fills:
                assert {v["operation"] for v in options.values()} == {"click", "fill"}
                choice = next(iter(fills))
            else:
                choice = next(key for key, value in options.items()
                              if value["label"] in {"Personal info", "Edit profile", "Continue", "Save"})
            assert "milestones" not in data["state"]["goal"]
            assert "progress" in data["state"]
            return httpx.Response(200, json={"model": "jev-1.13.0", "answers": {
                "next_action": {"type": "choice", "choice": choice, "confidence": 1,
                                "probabilities": {key: int(key == choice) for key in criteria}},
            }, "usage": {"input_tokens": 12, "output_tokens": 0}})

        async def aclose(self):
            closed.append(True)

    async def audit(record):
        audits.append(record)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)
    registry = ExtensionRegistry()
    manifest = read_manifest_from_yaml(Path(__file__).parents[1] / "plugin.yaml")
    for extension in manifest.extensions:
        registry.register(manifest.plugin_name, extension)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(f'''llm:
  default:
    api_key: unused
    model: unused
    base_url: https://offline.invalid/v1
decision_models:
  decision:
    url: https://offline.invalid/v1/systemone
    model: jev-1.13.0
    credential_env: TEST_JEV_KEY
subagents:
  agent-computer-use:agent:
    config:
      browser:
        scope: managed-page
        url: {site}goal/{layout}
      selector: jev
''')
    definition_path = tmp_path / "agent.md"
    definition_path.write_text('''---
name: ladder
extension: agent-computer-use:agent
decision-model: decision
---
Save name.
''')
    definition = parse_agent_file(definition_path)
    runner = AgentRunner(
        MagicMock(), MagicMock(), Bus(), ToolApprovalPolicy(computer_mode="allow"),
        PendingToolCallStore(), {definition.name: definition}, registry=registry,
        app_config=AppConfig.load(config_path), desktop_resource=DesktopResource(),
    )
    task_goal = {
        "schema_version": 2, "goal_id": "name", "intent": "Save display name Ada; preserve email",
        "objective": "Save display name Ada", "scope": "managed-page", "authorization_ref": "jev-dom",
        "allowed_operations": ["click", "fill"],
        "inputs": [{"key": "name", "purpose": "profile display name", "value": "Ada"}],
        "completion": [{"key": "status:Saved name", "value": "Ada"},
                       {"key": "status:Saved email", "value": "unchanged@example.test"}],
    }
    outputs = [output async for output in runner.run_agent(
        definition, [], task_id="jev-dom", task_input=task_goal,
        authorization=SubAgentAuthorization(frozenset({"desktop", "network"})), audit=audit,
    )]
    results = [out.metadata["task_result"] for out in outputs if "task_result" in out.metadata]
    assert len(results) == 1 and results[0]["status"] == "completed", outputs
    assert results[0]["cleanup"] == "confirmed"
    assert len(sent) == (4 if layout == "middle" else 3) and closed == [True]
    assert profile_store == {"name": "Ada", "email": "unchanged@example.test", "saves": "1"}
    assert len(results[0]["details"]["progress"]["verified_actions"]) == len(sent)
    assert not any(record.category == "model" for record in audits)
    assert any(record.operation == "computer_use.dispatch" for record in audits)
    assert "never-in-plugin-config" not in repr(outputs) + repr(audits)


@pytest.mark.parametrize("bad_reply", [False, True])
async def test_frozen_jev_smoke_harness_with_fake_http(
    chromium_required, monkeypatch, tmp_path, bad_reply,
):
    import json
    import runpy

    import httpx

    module = runpy.run_path(str(Path(__file__).parents[3] / "benchmarks/computer_use/jev_smoke.py"))
    sent = []

    async def respond(request):
        data = json.loads(request.content)
        sent.append(data)
        criteria = data["questions"]["next_action"]["criteria"]
        refs = {element["ref"] for element in data["state"]["snapshot"]["elements"]
                if element["label"] in {"Save", "保存"}}
        choice = next((key for key, value in criteria.items()
                       if isinstance(value, dict) and value["target_ref"] in refs), "none")
        return httpx.Response(200, json={
            "model": "invalid" if bad_reply and len(sent) == 3 else "jev-1.13.0", "answers": {
            "next_action": {"type": "choice", "choice": choice, "confidence": 1,
                            "probabilities": {key: int(key == choice) for key in criteria}},
        }, "usage": {"input_tokens": 20, "output_tokens": 0}})

    monkeypatch.setenv("TYPESAFE_API_KEY", "fake-smoke-key")
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda: httpx.MockTransport(respond))
    report = await module["run_smoke"](tmp_path / "report")
    assert len(sent) == 3
    assert [case["passed"] for case in report["cases"]] == [True, True, not bad_reply]
    assert report["spend"]["batch"]["known_tokens"] == 60
    assert "fake-smoke-key" not in repr(report)


def test_smoke_refuses_a_second_request_in_one_case():
    import runpy

    from tank_backend.llm.model_data import ModelRequest

    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, SpendLimitExceeded

    module = runpy.run_path(str(Path(__file__).parents[3] / "benchmarks/computer_use/jev_smoke.py"))
    ledger = SpendLedger(SpendLimit(393216, 10_000_000), request_limit=3)
    ledger.start_trial("case", SpendLimit(131072, 3_000_000))
    policy = module["OneCallPolicy"](ledger)
    request = ModelRequest(module["ENDPOINT"], module["MODEL"], {"model": module["MODEL"]})
    policy.reserve("one", request)
    policy.settle("one", 20, 0)
    with pytest.raises(SpendLimitExceeded, match="smoke_case_requests"):
        policy.reserve("two", request)
    assert ledger.snapshot()["batch"]["admitted_requests"] == 1
    ledger.close()


@pytest.mark.parametrize("layout", ["toolbar", "table", "dialog"])
@pytest.mark.parametrize("scenario", ["sufficient", "missing", "conflicting", "stale", "no_effect"])
async def test_real_dom_multilayout_selection_readback(
    site, chromium_required, monkeypatch, tmp_path, layout, scenario,
):
    import json
    from dataclasses import asdict
    from typing import cast

    import httpx
    from agent_computer_use.channels.dom import ManagedChromiumChannel
    from agent_computer_use.contracts import snapshot_json
    from agent_computer_use.factory import create_subagent
    from tank_backend.llm.decision_profile import DecisionModelProfile

    source_html = multilayout_html(layout, scenario)
    desired_slot = "A" if layout == "table" else "B"
    captured, audits, closed = [], [], []
    agent = create_subagent({"browser": {"scope": "managed-page",
                                         "url": f"{site}multilayout/{layout}/{scenario}"},
                             "selector": "jev"})
    browser = cast(ManagedChromiumChannel, agent.controller.source)

    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            payload = json.loads(request.content)
            snapshot = payload["state"]["snapshot"]
            assert snapshot["complete"] and snapshot["ready"]
            assert all(e["source"] == "dom" for e in snapshot["elements"])
            facts = {f["key"]: f["value"] for f in snapshot["facts"]}
            assert facts["status:Result"] == "idle"
            assert payload["state"]["evidence_contract"]["output_effect"] == "proposal_only"
            criteria = payload["questions"]["next_action"]["criteria"]
            if scenario == "missing":
                assert not any(key.startswith("status:Identity") for key in facts)
                choice = "need_more_context"
            elif scenario == "conflicting":
                assert facts[f"status:Secondary identity {desired_slot}"] != facts[f"status:Identity {desired_slot}"]
                choice = "ambiguous"
            else:
                matches = [slot for slot in ("A", "B") if facts[f"status:Identity {slot}"] == "K7"]
                assert matches == [desired_slot]
                ref = next(e["ref"] for e in snapshot["elements"] if e["label"] == f"执行 {matches[0]}")
                choice = next(key for key, value in criteria.items()
                              if isinstance(value, dict) and value["target_ref"] == ref)
            response = {"model": "jev-1.13.0", "answers": {"next_action": {
                "type": "choice", "choice": choice, "confidence": 1,
                "probabilities": {key: int(key == choice) for key in criteria},
            }}, "usage": {"input_tokens": 12, "output_tokens": 0}}
            captured.append({"request": payload, "response": response})
            if scenario == "stale":
                assert browser.page is not None
                await browser.page.get_by_role("button", name=f"执行 {desired_slot}", exact=True).evaluate(
                    "el => el.replaceWith(el.cloneNode(true))")
            return httpx.Response(200, json=response)

        async def aclose(self):
            closed.append(True)

    async def audit(record):
        audits.append(asdict(record))

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)
    ctx = SubAgentContext(SubAgentAuthorization(frozenset({"desktop", "network"})),
                          SubAgentBudget(), asyncio.Event(), audit=audit)
    ctx.runtime.configure_decision_model("dom-task", DecisionModelProfile(
        "https://offline.invalid/v1/systemone", "jev-1.13.0", "jev"), credential="fixture-only-key")
    task_goal = GoalContract.from_input({'schema_version': 2, 'scope': 'managed-page', 'objective': '执行身份 K7 对应的项目', 'inputs': [{'key': 'identity', 'value': 'K7', 'purpose': 'identity'}], 'completion': [{'key': 'status:Result', 'value': 'selected:K7'}], 'goal_id': 'goal', 'intent': '执行身份 K7 对应的项目', 'authorization_ref': 'current_task', 'allowed_operations': ['click', 'fill']})
    try:
        outputs = [o async for o in agent.run(SubAgentRequest(
            "select target", "", "dom-task", task_goal.model_dump(mode="json")), ctx)]
        result = outputs[-1].metadata["task_result"]
        assert browser.page is not None
        effects = await browser.page.evaluate("window.clicks")
        displayed = await browser.page.get_by_role("status", name="Result", exact=True).text_content()
        assert len(captured) == 1 and ctx.budget.total_tokens == 12
        assert browser.previous is not None
        if scenario == "sufficient":
            assert result["status"] == "completed" and result["reason"] == "goal_verified"
            assert effects == [desired_slot] and displayed == "selected:K7"
            assert browser.previous.observation_id != captured[0]["request"]["state"]["snapshot"]["observation_id"]
            assert len(agent.controller.receipts) == 1
        elif scenario == "no_effect":
            assert result["status"] == "unknown" and result["reason"] == "effect_unknown"
            assert result["details"]["pending_effect"] is True
            assert effects == [desired_slot] and displayed == "idle"
            assert len(agent.controller.receipts) == 1
        else:
            assert result["status"] == "stopped"
            if scenario == "stale":
                assert result["reason"] == "stale_reference"
            assert effects == [] and displayed == "idle" and not agent.controller.receipts
        screenshot = await browser.page.screenshot() if scenario == "sufficient" else None
        evidence = {"layout": layout, "scenario": scenario, "model_http": "fixed_fake",
                    "source_html": source_html, "calls": captured, "task_result": result,
                    "last_snapshot": snapshot_json(browser.previous), "page_clicks": effects,
                    "page_result": displayed, "audit": audits}
    finally:
        await agent.aclose()
        await ctx.runtime.aclose()
    assert browser.closed and browser.browser is not None
    assert not browser.browser.is_connected() and closed == [True]
    evidence["browser_closed"] = True
    destination = Path(os.environ.get("TANK_DOM_EVIDENCE_DIR", str(tmp_path)))
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / f"{layout}-{scenario}.json").open("x") as file:
        json.dump(evidence, file, ensure_ascii=False, indent=2)
    if screenshot is not None:
        with (destination / f"{layout}-{scenario}.png").open("xb") as file:
            file.write(screenshot)


@pytest.mark.parametrize("failure", [None, "unknown", "cancel", "wrong", "audit", "budget", "invalid", "cleanup", "http"])
async def test_real_model_dom_harness_with_fake_http(chromium_required, monkeypatch, tmp_path, failure):
    import json
    import httpx

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s3_dom_live as live

    sent = []

    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            data = json.loads(request.content)
            sent.append(data)
            if failure == "cancel":
                raise asyncio.CancelledError
            if failure == "http":
                return httpx.Response(503)
            state = data["state"]["snapshot"]
            facts = {f["key"]: f["value"] for f in state["facts"]}
            criteria = data["questions"]["next_action"]["criteria"]
            if not any(k.startswith("status:Identity") for k in facts):
                choice = "need_more_context"
            elif any(k.startswith("status:Secondary identity") for k in facts):
                choice = "ambiguous"
            else:
                slot = next(slot for slot in ("A", "B") if facts[f"status:Identity {slot}"] == "K7")
                if failure == "wrong":
                    slot = "A" if slot == "B" else "B"
                ref = next(e["ref"] for e in state["elements"] if e["label"] == f"执行 {slot}")
                choice = next(k for k, v in criteria.items() if isinstance(v, dict) and v["target_ref"] == ref)
            response = {"model": "jev-1.13.0", "answers": {"next_action": {
                "type": "choice", "choice": choice, "confidence": 1,
                "probabilities": {k: int(k == choice) for k in criteria}}},
                "usage": {"input_tokens": 12, "output_tokens": 0}}
            if failure == "invalid":
                response["answers"]["next_action"]["confidence"] = True
            if failure == "unknown":
                response.pop("usage")
            return httpx.Response(200, json=response)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)
    if failure == "cleanup":
        close = live.dom.ManagedChromiumChannel.aclose

        async def failed_close(self):
            await close(self)
            raise RuntimeError("reported cleanup failure")

        monkeypatch.setattr(live.dom.ManagedChromiumChannel, "aclose", failed_close)
    if failure == "audit":
        append = live.v1.append_json

        def failing(file, row):
            if Path(file.name).name == "audit.jsonl":
                raise OSError("audit failure")
            append(file, row)

        monkeypatch.setattr(live.v1, "append_json", failing)
    if failure == "budget":
        original = live.SpendLedger

        def zero(*args, **kwargs):
            kwargs["request_limit"] = 0
            return original(*args, **kwargs)

        monkeypatch.setattr(live, "SpendLedger", zero)
    frozen = live.prepare(tmp_path / "run")
    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await live.run_batch(tmp_path / "run", frozen["sha256"], "fixture-key")
        result = json.loads((tmp_path / "run/result.json").read_text())
    else:
        result = await live.run_batch(tmp_path / "run", frozen["sha256"], "fixture-key")
    assert len(result["rows"]) == len(frozen["cases"]) == 15
    assert len((tmp_path / "run/rows.jsonl").read_text().splitlines()) == 15
    assert result["completed"] == (failure is None)
    assert all(r["cleanup_confirmed"] == (failure != "cleanup")
               for r in result["rows"] if r["status"] != "not_run")
    if failure is None:
        assert len(sent) == 15 and all(r["passed"] for r in result["rows"])
        assert result["spend"]["batch"]["known_tokens"] == 180
        assert result["spend"]["batch"]["reserved_tokens"] == 0
        assert sum(len(r["page_clicks"]) for r in result["rows"]) == 6
    else:
        assert len(sent) == (0 if failure in ("audit", "budget") else 1)
        assert sum(r["status"] == "not_run" for r in result["rows"]) == 14
        assert result["spend"]["stop_reason"]
    before = len(sent)
    with pytest.raises(FileExistsError):
        await live.run_batch(tmp_path / "run", frozen["sha256"], "fixture-key")
    assert len(sent) == before


async def test_dom_live_freeze_requires_exact_recipe_before_resources(monkeypatch, tmp_path):
    import json

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s3_dom_live as live

    def forbidden(*args, **kwargs):
        raise AssertionError("offline or rejected proposal touched resources")

    monkeypatch.setattr(live.factory, "create_subagent", forbidden)
    monkeypatch.setattr(asyncio, "start_server", forbidden)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    frozen = live.prepare(tmp_path / "run")
    assert len(frozen["cases"]) == frozen["request_limit"] == 15
    live.load_freeze(tmp_path / "run", frozen["sha256"])
    with pytest.raises(ValueError, match="credential"):
        await live.run_batch(tmp_path / "run", frozen["sha256"], "")
    frozen["cases"][0]["goal"]["objective"] = "changed"
    frozen["sha256"] = live.v1.digest({k: v for k, v in frozen.items() if k != "sha256"})
    (tmp_path / "run/freeze.json").write_text(json.dumps(frozen))
    with pytest.raises(ValueError, match="recipe changed"):
        await live.run_batch(tmp_path / "run", frozen["sha256"], "fixture-key")
    assert not (tmp_path / "run/spend.jsonl").exists()


@pytest.mark.parametrize("control", ["none", "ambiguous", "need_more_context", "escalate"])
def test_followup_separates_safe_refusal_from_legacy_classification(monkeypatch, control):
    import copy
    import json

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s3_dom_followup as followup

    old = json.loads(followup.PRIOR_RESULT.read_text())
    original = next(r for r in old["rows"] if r["id"] == "toolbar-missing")
    row = copy.deepcopy(original)
    call = next(iter(row["calls"].values()))
    answer = call["response"]["answers"]["next_action"]
    answer.update(choice=control, confidence=1,
                  probabilities={k: int(k == control) for k in answer["probabilities"]})
    case = {"scenario": "missing", "expected_slot": "B"}
    assert followup.assess(case, row)
    assert row["safe_refusal"] is True
    assert row["refusal_classification_match"] == (control in ("ambiguous", "need_more_context"))
    assert row["legacy_acceptance_passed"] == row["refusal_classification_match"]
    assert original["passed"] is False
    row["page_clicks"] = ["B"]
    assert not followup.assess(case, row)
    row["page_clicks"] = []
    row["result"]["reason"] = "invalid_decision"
    assert not followup.assess(case, row)


@pytest.mark.parametrize("failure", [None, "unsafe", "invalid"])
async def test_dom_followup_keeps_classification_misses_and_stops_bad_behavior(
    chromium_required, monkeypatch, tmp_path, failure,
):
    import json
    import httpx

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s3_dom_followup as followup

    sent = []

    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            data = json.loads(request.content)
            sent.append(data)
            snapshot = data["state"]["snapshot"]
            facts = {f["key"]: f["value"] for f in snapshot["facts"]}
            criteria = data["questions"]["next_action"]["criteria"]
            if failure == "unsafe":
                choice = next(k for k, v in criteria.items() if isinstance(v, dict))
            elif not any(k.startswith("status:Identity") for k in facts) or any(k.startswith("status:Secondary") for k in facts):
                choice = "none"
            else:
                slot = next(s for s in ("A", "B") if facts[f"status:Identity {s}"] == "K7")
                ref = next(e["ref"] for e in snapshot["elements"] if e["label"] == f"执行 {slot}")
                choice = next(k for k, v in criteria.items() if isinstance(v, dict) and v["target_ref"] == ref)
            return httpx.Response(200, json={"model": "jev-1.13.0", "answers": {"next_action": {
                "type": "choice", "choice": choice, "confidence": True if failure == "invalid" else 1,
                "probabilities": {k: int(k == choice) for k in criteria}}},
                "usage": {"input_tokens": 12, "output_tokens": 0}})

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)
    frozen = followup.prepare(tmp_path / "run")
    old = json.loads(followup.PRIOR_RESULT.read_text())
    assert [c["id"] for c in frozen["cases"]] == [r["id"] for r in old["rows"] if r["status"] == "not_run"]
    assert frozen["request_limit"] == 11
    result = await followup.run_batch(tmp_path / "run", frozen["sha256"], "fixture-key")
    assert len(result["rows"]) == 11
    assert len((tmp_path / "run/rows.jsonl").read_text().splitlines()) == 11
    if failure is None:
        assert result["completed"] and len(sent) == 11
        assert sum(r.get("safe_refusal") is True for r in result["rows"]) == 5
        assert sum(r.get("refusal_classification_match") is False for r in result["rows"]) == 5
        assert sum(r["legacy_acceptance_passed"] for r in result["rows"]) == 6
        assert sum(len(r["page_clicks"]) for r in result["rows"]) == 3
    else:
        assert not result["completed"] and len(sent) == 1
        assert sum(r["status"] == "not_run" for r in result["rows"]) == 10
        if failure == "unsafe":
            assert result["rows"][0]["page_clicks"] == ["A"]
            assert result["rows"][0]["result"]["status"] == "completed"
        else:
            assert result["rows"][0]["page_clicks"] == []
            assert result["rows"][0]["result"]["reason"] == "invalid_decision"
    with pytest.raises(FileExistsError):
        await followup.run_batch(tmp_path / "run", frozen["sha256"], "fixture-key")


async def test_dom_followup_freeze_rejects_changed_protocol_before_resources(monkeypatch, tmp_path):
    import json

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s3_dom_followup as followup

    frozen = followup.prepare(tmp_path / "run")
    followup.load_freeze(tmp_path / "run", frozen["sha256"])
    frozen["refusal_protocol"]["controls"].append("invented")
    frozen["sha256"] = followup.v1.digest({k: v for k, v in frozen.items() if k != "sha256"})
    (tmp_path / "run/freeze.json").write_text(json.dumps(frozen))

    def forbidden(*args, **kwargs):
        raise AssertionError("changed protocol created resources")

    monkeypatch.setattr(asyncio, "start_server", forbidden)
    with pytest.raises(ValueError, match="recipe changed"):
        await followup.run_batch(tmp_path / "run", frozen["sha256"], "fixture-key")
    assert not (tmp_path / "run/spend.jsonl").exists()


@pytest.mark.parametrize("mode", ["llm", "jev-fallback"])
async def test_runner_candidate_strategy_selects_fill_and_submit(site, chromium_required, monkeypatch, tmp_path, mode):
    import json
    import httpx
    from unittest.mock import MagicMock
    from tank_backend.agents.approval import PendingToolCallStore, ToolApprovalPolicy
    from tank_backend.agents.definition import parse_agent_file
    from tank_backend.agents.resources import DesktopResource
    from tank_backend.agents.runner import AgentRunner
    from tank_backend.config.app_config import AppConfig
    from tank_backend.pipeline.bus import Bus
    from tank_backend.plugin.manifest import read_manifest_from_yaml
    from tank_backend.plugin.registry import ExtensionRegistry

    calls, events, audits = [], [], []
    class Observer:
        def on_event(self, kind, metadata):
            events.append((kind, metadata))
    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            data = json.loads(request.content)
            calls.append(data)
            if "questions" in data:
                criteria = data["questions"]["next_action"]["criteria"]
                return httpx.Response(200, json={"model": "jev-1.13.0", "answers": {"next_action": {
                    "type": "choice", "choice": "none", "confidence": 1,
                    "probabilities": {k: int(k == "none") for k in criteria}}},
                    "usage": {"input_tokens": 12, "output_tokens": 0}})
            question = json.loads(data["messages"][1]["content"])
            choice = next(k for k, v in question["questions"]["next_action"]["criteria"].items() if isinstance(v, dict))
            assert data["enable_thinking"] is False
            return httpx.Response(200, json={"id": "f", "object": "chat.completion", "created": 1,
                "model": "f-model", "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps({"choice": choice})}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}})
    async def audit(record):
        audits.append(record)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)
    monkeypatch.setenv("S3_TEST_JEV_KEY", "fixture-key")
    registry = ExtensionRegistry()
    manifest = read_manifest_from_yaml(Path(__file__).parents[1] / "plugin.yaml")
    for extension in manifest.extensions:
        registry.register(manifest.plugin_name, extension)
    config = AppConfig.from_raw_dict({
        "llm": {"default": {"api_key": "fixture-f", "model": "f-model", "base_url": "https://offline.invalid/v1",
                            "max_tokens": 128, "extra_body": {"enable_thinking": False}}},
        "decision_models": {"jev": {"url": "https://offline.invalid/v1/systemone",
                                 "model": "jev-1.13.0", "credential_env": "S3_TEST_JEV_KEY"}},
        "subagents": {"agent-computer-use:agent": {"config": {"browser": {"scope": "managed-page", "url": site},
                                                              "selector": mode}}}})
    definition_file = tmp_path / "strategy.md"
    definition_file.write_text("---\nname: strategy\nextension: agent-computer-use:agent\nmodel: default\ndecision-model: jev\n---\nUse the declared task.\n")
    definition = parse_agent_file(definition_file)
    runner = AgentRunner(MagicMock(), MagicMock(), Bus(), ToolApprovalPolicy(computer_mode="allow"),
                        PendingToolCallStore(), {definition.name: definition}, registry=registry,
                        app_config=config, desktop_resource=DesktopResource())
    # Both the unbound fill and the submit require semantic selection.
    task = goal().model_dump(mode="json")
    task["inputs"][0]["field_label"] = None
    outputs = [o async for o in runner.run_agent(definition, [], task_id="strategy-task", task_input=task,
        authorization=SubAgentAuthorization(frozenset({"desktop", "network"})), observer=Observer(), audit=audit)]
    result = next(o.metadata["task_result"] for o in outputs if "task_result" in o.metadata)
    assert result["status"] == "completed" and result["cleanup"] == "confirmed"
    assert len(result["details"]["receipts"]) == 2
    assert len(calls) == (4 if mode == "jev-fallback" else 2)
    routes = [m["reason"] for k, m in events if k == "computer_use_route"]
    assert routes == ["jev_eligible", "jev_eligible"]
    assert not any(a.category == "model" for a in audits)
    assert len([m for k, m in events if k == "model_call" and m["phase"] == "finished"]) == len(calls)


@pytest.mark.parametrize("force_fallback", [False, True])
async def test_s3_strategy_pairs_governed_tasks_and_counts_fallback(chromium_required, monkeypatch, tmp_path, force_fallback):
    import json
    import httpx

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s3_strategy as bench

    calls = []
    async def respond(request):
        payload = json.loads(request.content)
        calls.append(payload)
        native = "questions" in payload
        q = payload if native else json.loads(payload["messages"][1]["content"])
        criteria = q["questions"]["next_action"]["criteria"]
        objective = q["state"]["goal"]["objective"]
        target = next((label for word,label in [('显示名称','保存'),('紧凑','紧凑视图'),('外观','界面与显示'),('草稿','保存进度'),('优惠','取消营销订阅'),('收据','查看支付凭证')] if word in objective), None)
        if target == "取消营销订阅" and any(
            f["key"] == "status:优惠邮件" and f["value"] == "off"
            for f in q["state"]["snapshot"]["facts"]
        ):
            target = "应用"
        if target is None or (native and force_fallback):
            choice = "none"
        else:
            ref = next(e["ref"] for e in q["state"]["snapshot"]["elements"] if e["label"] == target)
            choice = next(k for k,v in criteria.items() if isinstance(v,dict) and v["target_ref"] == ref)
        if native:
            return httpx.Response(200,json={"model":"jev-1.13.0","answers":{"next_action":{
                "type":"choice","choice":choice,"confidence":1,"probabilities":{k:int(k==choice) for k in criteria}}},
                "usage":{"input_tokens":12,"output_tokens":0}})
        assert payload["enable_thinking"] is False
        return httpx.Response(200,json={"id":"f","object":"chat.completion","created":1,
            "model":bench.MODELS['f']['model'],"choices":[{"index":0,"finish_reason":"stop",
            "message":{"role":"assistant","content":json.dumps({'choice':choice})}}],
            "usage":{"prompt_tokens":10,"completion_tokens":2,"total_tokens":12}})
    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            return await respond(request)
    monkeypatch.setattr(httpx,'AsyncHTTPTransport',HTTP)
    f=bench.prepare(tmp_path/'run')
    result=await bench.run_batch(tmp_path/'run',f['sha256'],{'jev':'fixture-j','f':'fixture-f'})
    assert result['completed'] and len(result['rows']) == 48
    assert len(result['paired']) == 24
    assert all(r['accepted'] and r['cleanup_confirmed'] for r in result['rows'])
    assert len(calls) == (81 if force_fallback else 60)
    assert result['spend']['batch']['known_tokens'] == len(calls)*12
    assert result['spend']['batch']['reserved_tokens'] == 0
    for row in result['rows']:
        if row['case_id'] == 'profile-name':
            assert len(row['calls']) == (2 if force_fallback and row['arm'] == 'J3' else 1)
    assert result['summary']['H3']['f_calls'] == 27
    assert result['summary']['J3']['f_calls'] == (27 if force_fallback else 6)
    assert result['summary']['J3']['jev_calls'] == 27
    with pytest.raises(FileExistsError):
        await bench.run_batch(tmp_path/'run',f['sha256'],{'jev':'fixture-j','f':'fixture-f'})


@pytest.mark.parametrize("failure", ["unknown", "cancelled", "audit", "cleanup"])
async def test_s3_strategy_stops_operational_failures_with_full_denominator(chromium_required, monkeypatch, tmp_path, failure):
    import json
    import httpx
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s3_strategy as bench
    sent=[]
    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self,request):
            sent.append(request)
            if failure=='cancelled':
                raise asyncio.CancelledError
            return httpx.Response(503)
    monkeypatch.setattr(httpx,'AsyncHTTPTransport',HTTP)
    if failure=='cleanup':
        original_close=bench.dom.ManagedChromiumChannel.aclose
        async def bad_close(self):
            await original_close(self)
            raise RuntimeError('reported close failure')
        monkeypatch.setattr(bench.dom.ManagedChromiumChannel,'aclose',bad_close)
    if failure=='audit':
        append=bench.v1.append_json
        def broken(file,row):
            if Path(file.name).name=='audit.jsonl':
                raise OSError('required audit unavailable')
            append(file,row)
        monkeypatch.setattr(bench.v1,'append_json',broken)
    f=bench.prepare(tmp_path/'run')
    if failure=='cancelled':
        with pytest.raises(asyncio.CancelledError):
            await bench.run_batch(tmp_path/'run',f['sha256'],{'jev':'j','f':'f'})
        result=json.loads((tmp_path/'run/result.json').read_text())
    else:
        result=await bench.run_batch(tmp_path/'run',f['sha256'],{'jev':'j','f':'f'})
    assert not result['completed'] and len(result['rows'])==48
    assert result['conclusion']=='incomplete_no_adoption_conclusion'
    assert len((tmp_path/'run/rows.jsonl').read_text().splitlines())==48
    assert len(sent)==(0 if failure == 'audit' else 1)
    assert result['spend']['stop_reason']


async def test_s3_strategy_freeze_rejects_drift_without_resources(monkeypatch,tmp_path):
    import json
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s3_strategy as bench
    def forbidden(*args,**kwargs):
        raise AssertionError('unexpected resource creation')
    monkeypatch.setattr(asyncio,'start_server',forbidden)
    f=bench.prepare(tmp_path/'run')
    f['request_limit']=55
    f['sha256']=bench.v1.digest({k:v for k,v in f.items() if k!='sha256'})
    (tmp_path/'run/freeze.json').write_text(json.dumps(f))
    with pytest.raises(ValueError,match='recipe changed'):
        await bench.run_batch(tmp_path/'run',f['sha256'],{'jev':'j','f':'f'})
    assert not (tmp_path/'run/spend.jsonl').exists()
