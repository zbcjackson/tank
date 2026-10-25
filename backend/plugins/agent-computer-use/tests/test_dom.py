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
def navigation_gate() -> tuple[asyncio.Event, asyncio.Event]:
    return asyncio.Event(), asyncio.Event()


@pytest.fixture
async def site(profile_store: dict[str, str],
               navigation_gate: tuple[asyncio.Event, asyncio.Event]) -> AsyncIterator[str]:
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
        if path.path == "/spatial":
            body = profile_store["spatial_html"].encode()
        if path.path == "/table-readback":
            profile_store["table_reads"] = str(int(profile_store.get("table_reads", "0")) + 1)
            profile_store["table_methods"] = profile_store.get("table_methods", "") + request.split(b" ", 1)[0].decode() + ","
            body = ('<!doctype html><table><thead><tr><th>id</th><th>title</th><th>notes</th>'
                    '</tr></thead><tbody><tr><td>1</td><td>' + profile_store["name"]
                    + '</td><td>Keep A</td></tr><tr><td>2</td><td>Tavi</td><td>Keep B</td>'
                    '</tr></tbody></table>').encode()
            body = profile_store.get("table_html", body.decode()).encode()
        if request.startswith(b"GET /multilayout/"):
            layout_path = request.split(b" ", 2)[1].decode()
            _, _, layout, scenario = layout_path.split("/")
            body = multilayout_html(layout, scenario).encode()
        if request.startswith(b"GET /frame"):
            child = html.decode()
            if b"/frame-nested" in request.splitlines()[0]:
                child += '<iframe></iframe>'
            body = ('<iframe name="bound" srcdoc="' + html_module.escape(child, quote=True)
                    + '"></iframe>').encode()
            if b"/frame-duplicate" in request.splitlines()[0]:
                body += body
        prefix = b''
        if path.path == '/deferred':
            prefix = b'<!doctype html><body>'
            body = b'<label>Title<input value="New document"></label></body>'
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                     + f"Content-Length: {len(prefix) + len(body)}\r\nConnection: close\r\n\r\n".encode())
        if prefix:
            writer.write(prefix)
            await writer.drain()
            navigation_gate[0].set()
            await navigation_gate[1].wait()
        writer.write(body)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(respond, "127.0.0.1", 0)
    try:
        yield f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/"
    finally:
        navigation_gate[1].set()
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


async def test_dom_table_readback_emits_complete_page_bound_result_after_get(
    site, profile_store, chromium_required,
):
    from agent_computer_use.channels.dom import BrowserConfig, ManagedChromiumChannel, dom_table_fact

    ctx = context()
    url = site + "table-readback"
    browser = ManagedChromiumChannel(BrowserConfig(
        scope="managed-page", url=url, readback_tables=True))
    try:
        snapshot = await browser.observe("managed-page", ctx)
        expected = dom_table_fact(url, ("id", "title", "notes"),
                                  (("1", "Bob", "Keep A"), ("2", "Tavi", "Keep B")))
        assert snapshot.ready and snapshot.complete
        assert expected in snapshot.facts
        assert profile_store["table_reads"] == "2"
        assert await browser.is_snapshot_current(snapshot, ctx)
    finally:
        await browser.aclose()
        await ctx.runtime.aclose()


@pytest.mark.parametrize("markup", [
    '<th></th><th>id</th><th>title</th></tr></thead><tbody>'
    '<tr><td colspan="2">ignored</td><td>1</td><td>Miro</td></tr>',
    '<th>id<span aria-hidden="true">hidden-key</span></th><th>title</th></tr></thead>'
    '<tbody><tr><td>1</td><td>Miro</td></tr>',
])
async def test_dom_table_readback_rejects_ambiguous_cell_geometry_and_hidden_headers(
    site, profile_store, chromium_required, markup,
):
    from agent_computer_use.channels.dom import BrowserConfig, ManagedChromiumChannel

    profile_store["table_html"] = '<table><thead><tr>' + markup + '</tbody></table>'
    ctx = context()
    browser = ManagedChromiumChannel(BrowserConfig(
        scope="managed-page", url=site + "table-readback", readback_tables=True))
    try:
        snapshot = await browser.observe("managed-page", ctx)
        assert not any(f.key.startswith("status:DOM table:") for f in snapshot.facts)
    finally:
        await browser.aclose()
        await ctx.runtime.aclose()


_READBACK_TABLE = ('<table><thead><tr><th>id</th><th>title</th></tr></thead>'
                   '<tbody><tr><td>1</td><td>Miro</td></tr></tbody></table>')


@pytest.mark.parametrize("markup", [
    _READBACK_TABLE.replace('<th>title</th>', '<th>id</th>'),
    _READBACK_TABLE + _READBACK_TABLE,
    _READBACK_TABLE + _READBACK_TABLE.replace('Miro', '<input value="Miro">'),
    _READBACK_TABLE + _READBACK_TABLE.replace('</table>', '<tfoot><tr><td>1</td><td>Total</td></tr></tfoot></table>'),
    _READBACK_TABLE + '<table><tr><td>' + _READBACK_TABLE + '</td></tr></table>',
    _READBACK_TABLE + _READBACK_TABLE.replace('</thead>', '<tr><th>more</th><th>headers</th></tr></thead>'),
    _READBACK_TABLE.replace('<td>Miro</td>', '<td hidden>Miro</td>'),
    _READBACK_TABLE.replace('<tbody><tr>', '<tbody><tr hidden>'),
    _READBACK_TABLE.replace('Miro', '<input value="Miro">'),
    _READBACK_TABLE.replace('<td>Miro</td>', '<td contenteditable="true">Miro</td>'),
    '<section contenteditable="true">' + _READBACK_TABLE + '</section>',
    _READBACK_TABLE.replace('<th>title</th>', '<th>title<input value="Uncommitted"></th>'),
    _READBACK_TABLE.replace('<tbody>', '<tbody aria-busy="true">'),
    _READBACK_TABLE.replace('<table>', '<table style="opacity:0">'),
    '<table><tr><td>' + _READBACK_TABLE + '</td></tr></table>',
    _READBACK_TABLE.replace('Miro', 'x' * 4097),
    _READBACK_TABLE.replace('<tr><td>1</td><td>Miro</td></tr>',
                            '<tr><td>1</td><td>Miro</td></tr>' * 65),
])
async def test_dom_table_readback_withholds_partial_editable_ambiguous_or_oversized_tables(
    site, profile_store, chromium_required, markup,
):
    from agent_computer_use.channels.dom import BrowserConfig, ManagedChromiumChannel

    profile_store["table_html"] = markup
    ctx = context()
    browser = ManagedChromiumChannel(BrowserConfig(
        scope="managed-page", url=site + "table-readback", readback_tables=True))
    try:
        snapshot = await browser.observe("managed-page", ctx)
        assert not any(f.key.startswith("status:DOM table:") for f in snapshot.facts)
    finally:
        await browser.aclose()
        await ctx.runtime.aclose()


async def test_dom_table_readback_ignores_unsaved_display_and_never_reposts(
    site, profile_store, chromium_required,
):
    from agent_computer_use.channels.dom import BrowserConfig, ManagedChromiumChannel, dom_table_fact

    ctx = context()
    url = site + "table-readback"
    browser = ManagedChromiumChannel(BrowserConfig(
        scope="managed-page", url=url, readback_tables=True))
    try:
        await browser.observe("managed-page", ctx)
        assert browser.page is not None
        await browser.page.locator('tbody tr').first.locator('td').nth(1).evaluate(
            "node => node.textContent = 'Miro'")
        snapshot = await browser.observe("managed-page", ctx)
        assert dom_table_fact(url, ("id", "title", "notes"),
                              (("1", "Bob", "Keep A"), ("2", "Tavi", "Keep B"))) in snapshot.facts
        assert not any('Miro' in f.value for f in snapshot.facts)
        await browser.page.evaluate("""() => {
            const form = document.createElement('form');
            form.method = 'post'; form.action = location.href;
            document.body.append(form); form.submit();
        }""")
        await browser.page.wait_for_url(url, wait_until="load")
        snapshot = await browser.observe("managed-page", ctx)
        assert snapshot.complete
        assert profile_store["table_methods"].endswith("POST,GET,")
        assert profile_store["table_methods"].count("POST,") == 1
    finally:
        await browser.aclose()
        await ctx.runtime.aclose()


@pytest.mark.parametrize("enabled", [False, True])
async def test_dom_table_readback_reserves_namespace_and_preserves_default(
    site, profile_store, chromium_required, enabled,
):
    from agent_computer_use.channels.dom import BrowserConfig, ManagedChromiumChannel, dom_table_fact

    url = site + "table-readback"
    expected = dom_table_fact(url, ("id",), (("1",),))
    profile_store["table_html"] = f"<output aria-label='{expected.key}'>{expected.value}</output>"
    ctx = context()
    browser = ManagedChromiumChannel(BrowserConfig(
        scope="managed-page", url=url, readback_tables=enabled))
    try:
        snapshot = await browser.observe("managed-page", ctx)
        assert not any(f.key.startswith("status:DOM table:") for f in snapshot.facts)
        assert profile_store["table_reads"] == "1"
    finally:
        await browser.aclose()
        await ctx.runtime.aclose()


@pytest.mark.parametrize("form", [
    '<form><label>Notes<input value="Old"></label></form>',
    '<form id="editor"><button>Save</button></form>'
    '<label>Notes<input form="editor" value="Old"></label>',
])
async def test_dom_table_readback_does_not_discard_an_editable_form(
    site, profile_store, chromium_required, form,
):
    from agent_computer_use.channels.dom import BrowserConfig, ManagedChromiumChannel

    profile_store["table_html"] = _READBACK_TABLE + form
    ctx = context()
    browser = ManagedChromiumChannel(BrowserConfig(
        scope="managed-page", url=site + "table-readback", readback_tables=True))
    try:
        await browser.start(ctx)
        assert browser.page is not None
        await browser.page.get_by_label('Notes').fill('Uncommitted')
        snapshot = await browser.observe("managed-page", ctx)
        assert not any(f.key.startswith("status:DOM table:") for f in snapshot.facts)
        assert await browser.page.get_by_label('Notes').input_value() == 'Uncommitted'
        assert profile_store["table_reads"] == "1"
    finally:
        await browser.aclose()
        await ctx.runtime.aclose()


async def test_dom_table_readback_preserves_a_non_http_named_frame(
    site, profile_store, chromium_required,
):
    from agent_computer_use.channels.dom import BrowserConfig, ManagedChromiumChannel

    markup = html_module.escape(_READBACK_TABLE, quote=True)
    profile_store["table_html"] = f'<iframe name="bound" srcdoc="{markup}"></iframe>'
    ctx = context()
    browser = ManagedChromiumChannel(BrowserConfig(
        scope="managed-page", url=site + "table-readback", frame_name="bound", readback_tables=True))
    try:
        snapshot = await browser.observe("managed-page", ctx)
        assert snapshot.complete and snapshot.ready
        assert browser.frame is not None and browser.frame.url == "about:srcdoc"
        assert not any(f.key.startswith("status:DOM table:") for f in snapshot.facts)
        assert profile_store["table_reads"] == "1"
    finally:
        await browser.aclose()
        await ctx.runtime.aclose()


def goal() -> GoalContract:
    return GoalContract.from_input({'schema_version': 2, 'objective': 'Save name', 'scope': 'managed-page', 'inputs': [{'key': 'name', 'value': '小明', 'purpose': 'name', 'field_label': 'Name'}], 'completion': [{'key': 'status:Result', 'value': '小明'}], 'goal_id': 'goal', 'intent': 'Save name', 'authorization_ref': 'current_task', 'allowed_operations': ['click', 'fill']})


class SelectOnlyCandidate:
    async def choose(self, goal, snapshot, actions, ctx):
        from agent_computer_use.contracts import DecisionResult

        assert len(actions.actions) == 1
        return DecisionResult(actions.binding, "candidate", actions.actions[0].id)


async def test_dom_aggregate_visible_text_does_not_overflow_on_formatting(channel):
    browser, ctx = channel
    padding = "\n " * 1500
    await browser.page.set_content(
        '<ul role="list" aria-label="Records">'
        + ''.join(f'<li>{padding}Record {n}{padding}</li>' for n in range(1, 5))
        + '</ul>')
    snapshot = await browser.observe("managed-page", ctx)
    assert snapshot.complete
    records = next(e for e in snapshot.elements if e.label == "Records")
    assert records.value.splitlines() == [f'Record {n}' for n in range(1, 5)]


async def test_dom_aggregate_labels_exclude_hidden_descendants(channel):
    browser, ctx = channel
    await browser.page.set_content(
        '<ul role="list"><li>Visible record'
        f'<span hidden>{"private-hidden" * 100}</span></li></ul>')
    snapshot = await browser.observe("managed-page", ctx)
    assert snapshot.complete
    records = next(e for e in snapshot.elements if e.role == "list")
    assert records.label == records.value == "Visible record"


async def test_dom_visible_text_limits_keep_input_whitespace_exact(channel):
    browser, ctx = channel
    await browser.page.set_content(
        '<label>Notes<textarea></textarea></label><ul role="list" aria-label="Records"></ul>')
    value = "  Keep\n  these spaces  "
    await browser.page.get_by_label('Notes').fill(value)
    snapshot = await browser.observe("managed-page", ctx)
    assert snapshot.complete
    assert next(e.value for e in snapshot.elements if e.label == 'Notes') == value
    await browser.page.locator('ul').evaluate("node => node.textContent = 'x'.repeat(4097)")
    assert not (await browser.observe("managed-page", ctx)).complete


async def test_dom_rendered_preformatted_status_keeps_visible_whitespace(channel):
    browser, ctx = channel
    value = '  first line\n second line  '
    await browser.page.set_content(
        f'<output aria-label="Report" style="white-space:pre">{value}</output>')
    snapshot = await browser.observe("managed-page", ctx)
    assert snapshot.complete
    assert next(e.value for e in snapshot.elements if e.label == 'Report') == value


async def test_dom_observe_navigation_discards_partial_read(channel, monkeypatch):
    browser, ctx = channel
    before = await browser.observe('managed-page', ctx)
    actions = ActionBuilder().build('goal', 1, goal(), before)
    original_read = browser.read
    async def navigate_after_read(frame, context):
        view = await original_read(frame, context)
        await browser.page.goto(browser.config.url + 'goal/plain')
        return view
    with monkeypatch.context() as patch:
        patch.setattr(browser, 'read', navigate_after_read)
        unavailable = await browser.observe('managed-page', ctx)
    assert not unavailable.ready and not unavailable.complete
    assert not unavailable.elements and not unavailable.facts
    receipt = await browser.dispatch(actions.binding, actions.actions[0], ctx)
    assert receipt.status == 'not_sent'
    fresh = await browser.observe('managed-page', ctx)
    assert fresh.ready and fresh.complete
    assert any(e.label == 'Personal info' for e in fresh.elements)


@pytest.mark.parametrize('same_url', [False, True])
async def test_dom_observe_navigation_waits_for_committed_document(channel, navigation_gate, same_url):
    browser, ctx = channel
    if same_url:
        navigation_gate[1].set()
        await browser.page.goto(browser.config.url + 'deferred')
        navigation_gate[0].clear()
        navigation_gate[1].clear()
    await browser.page.set_content('<a href="/deferred">Retry</a>')
    before = await browser.observe('managed-page', ctx)
    retry = next(e for e in before.elements if e.label == 'Retry')
    if same_url:
        await browser.page.reload(wait_until='commit')
    else:
        await browser.page.goto(browser.config.url + 'deferred', wait_until='commit')
    await navigation_gate[0].wait()
    observing = asyncio.create_task(browser.observe('managed-page', ctx))
    try:
        done, _ = await asyncio.wait({observing}, timeout=.05)
        assert not done, 'A committed document is still loading, so it cannot be published yet'
        navigation_gate[1].set()
        snapshot = await asyncio.wait_for(observing, 2)
        assert snapshot.ready and snapshot.complete
        assert next(e.value for e in snapshot.elements if e.label == 'Title') == 'New document'
        assert all(e.ref != retry.ref for e in snapshot.elements)
        assert next(f.value for f in snapshot.facts if f.key == 'status:Page URL').endswith('/deferred')
    finally:
        navigation_gate[1].set()
        await asyncio.gather(observing, return_exceptions=True)


async def test_dom_observe_navigation_timeout_discards_references(channel, navigation_gate):
    from tank_backend.agents.subagent import SubAgentStopped

    browser, ctx = channel
    before = await browser.observe('managed-page', ctx)
    actions = ActionBuilder().build('goal', 1, goal(), before)
    await browser.page.goto(browser.config.url + 'deferred', wait_until='commit')
    await navigation_gate[0].wait()
    try:
        snapshot = await browser.observe('managed-page', ctx)
        assert not snapshot.ready and not snapshot.complete
        assert not snapshot.elements and not snapshot.facts
        assert (await browser.dispatch(actions.binding, actions.actions[0], ctx)).status == 'not_sent'
        with pytest.raises(SubAgentStopped):
            await browser.capture(before, ctx)
    finally:
        navigation_gate[1].set()
    await browser.page.wait_for_load_state('domcontentloaded')
    assert (await browser.observe('managed-page', ctx)).complete


@pytest.mark.parametrize('stop', ['cancel', 'revoke', 'deadline'])
async def test_dom_observe_navigation_wait_respects_task_stop(channel, navigation_gate, stop):
    import time
    from dataclasses import replace
    from tank_backend.agents.subagent import SubAgentStopped

    browser, ctx = channel
    await browser.page.goto(browser.config.url + 'deferred', wait_until='commit')
    await navigation_gate[0].wait()
    if stop == 'deadline':
        ctx = replace(ctx, deadline=time.monotonic() + .05)
        ctx.runtime.bind('dom-task')
    observing = asyncio.create_task(browser.observe('managed-page', ctx))
    await asyncio.wait({observing}, timeout=.02)
    if stop == 'cancel':
        ctx.cancel.set()
        expected = asyncio.CancelledError
    elif stop == 'revoke':
        ctx.authorization.revoke()
        expected = SubAgentStopped
    else:
        expected = TimeoutError
    try:
        with pytest.raises(expected, match='subagent deadline' if stop == 'deadline' else None):
            await asyncio.wait_for(observing, .2)
    finally:
        navigation_gate[1].set()
        await asyncio.gather(observing, return_exceptions=True)
        if stop == 'deadline':
            await ctx.runtime.aclose()


async def test_dom_observe_busy_navigation_waits_for_css_and_new_body(channel):
    browser, ctx = channel
    await browser.page.set_content('<a href="/old-retry">Retry</a>')
    before = await browser.observe('managed-page', ctx)
    old_actions = ActionBuilder().build('goal', 1, goal(), before)
    requested, release = asyncio.Event(), asyncio.Event()

    async def pending_css(route):
        requested.set()
        await release.wait()
        await route.fulfill(content_type='text/css', body='input {color: black}')

    await browser.page.route('**/pending-navigation.css', pending_css)
    await browser.page.evaluate("""() => {
        history.pushState({}, '', '/busy-editor');
        document.documentElement.setAttribute('aria-busy', 'true');
        const link = document.createElement('link');
        link.rel = 'stylesheet'; link.href = '/pending-navigation.css';
        link.onload = () => {
            document.body.innerHTML = '<label>Title<input value="New editor"></label>';
            document.documentElement.removeAttribute('aria-busy');
        };
        document.head.append(link);
    }""")
    await requested.wait()
    assert await browser.page.evaluate('document.readyState') == 'complete'
    observing = asyncio.create_task(browser.observe('managed-page', ctx))
    try:
        done, _ = await asyncio.wait({observing}, timeout=.05)
        assert not done, 'A busy SPA must not pair its new URL with the old Retry DOM'
        assert (await browser.dispatch(old_actions.binding, old_actions.actions[0], ctx)).status == 'not_sent'
        assert browser.page.url.endswith('/busy-editor')
        release.set()
        snapshot = await asyncio.wait_for(observing, 2)
        assert snapshot.ready and snapshot.complete
        assert next(e.value for e in snapshot.elements if e.label == 'Title') == 'New editor'
        assert all(e.ref != before.elements[0].ref for e in snapshot.elements)
        assert ctx.budget.total_tokens == 0
    finally:
        release.set()
        await asyncio.gather(observing, return_exceptions=True)


async def test_dom_observe_busy_clear_waits_for_finite_teardown(channel):
    browser, ctx = channel
    await browser.page.set_content('''<style>
        @keyframes finish {from {opacity: 1} to {opacity: 0}}
        </style><div id="progress">Loading</div><label>Name<input value="Ready"></label>''')
    await browser.page.evaluate("document.documentElement.setAttribute('aria-busy', 'true')")
    observing = asyncio.create_task(browser.observe('managed-page', ctx))
    try:
        await asyncio.wait({observing}, timeout=.02)
        await browser.page.evaluate("""() => {
            const progress = document.getElementById('progress');
            progress.addEventListener('animationend', () => progress.remove(), {once: true});
            progress.style.animation = 'finish 120ms linear forwards';
            document.documentElement.removeAttribute('aria-busy');
        }""")
        done, _ = await asyncio.wait({observing}, timeout=.03)
        assert not done, 'Busy clearance does not finish the finite DOM teardown'
        snapshot = await asyncio.wait_for(observing, 2)
        assert snapshot.ready and snapshot.complete
        assert await browser.page.locator('#progress').count() == 0
        actions = ActionBuilder().build('goal', 1, goal(), snapshot)
        assert await browser.is_current(actions.binding, actions.actions[0], ctx)
    finally:
        await asyncio.gather(observing, return_exceptions=True)


async def test_dom_observe_busy_timeout_discards_old_references(channel):
    from tank_backend.agents.subagent import SubAgentStopped

    browser, ctx = channel
    before = await browser.observe('managed-page', ctx)
    actions = ActionBuilder().build('goal', 1, goal(), before)
    await browser.page.evaluate("document.documentElement.setAttribute('aria-busy', 'true')")
    snapshot = await browser.observe('managed-page', ctx)
    assert not snapshot.ready and not snapshot.complete
    assert not snapshot.elements and not snapshot.facts
    assert (await browser.dispatch(actions.binding, actions.actions[0], ctx)).status == 'not_sent'
    with pytest.raises(SubAgentStopped):
        await browser.capture(before, ctx)


@pytest.mark.parametrize('stop', ['cancel', 'revoke', 'deadline'])
async def test_dom_observe_busy_wait_respects_task_stop(channel, stop):
    import time
    from dataclasses import replace
    from tank_backend.agents.subagent import SubAgentStopped

    browser, ctx = channel
    await browser.page.evaluate("document.documentElement.setAttribute('aria-busy', 'true')")
    if stop == 'deadline':
        ctx = replace(ctx, deadline=time.monotonic() + .05)
        ctx.runtime.bind('dom-task')
    observing = asyncio.create_task(browser.observe('managed-page', ctx))
    await asyncio.wait({observing}, timeout=.02)
    if stop == 'cancel':
        ctx.cancel.set()
        expected = asyncio.CancelledError
    elif stop == 'revoke':
        ctx.authorization.revoke()
        expected = SubAgentStopped
    else:
        expected = TimeoutError
    try:
        with pytest.raises(expected, match='subagent deadline' if stop == 'deadline' else None):
            await asyncio.wait_for(observing, .2)
    finally:
        await asyncio.gather(observing, return_exceptions=True)
        if stop == 'deadline':
            await ctx.runtime.aclose()


@pytest.mark.parametrize('count', [38, 65])
async def test_dom_explicit_candidate_budget_preserves_whole_action_set(channel, count):
    browser, ctx = channel
    await browser.page.set_content(''.join(
        f'<a href="/record/{n}">Edit record {n}</a>' for n in range(count)))
    snapshot = await browser.observe("managed-page", ctx)
    default = ActionBuilder(visual=True).build('goal', 1, goal(), snapshot)
    assert default.reason == 'candidate_limit' and not default.actions
    declared = ActionBuilder(64, visual=True).build('goal', 1, goal(), snapshot)
    assert declared.total_candidates == count
    assert len(declared.actions) == (count if count <= 64 else 0)
    assert (declared.reason == 'candidate_limit') == (count > 64)


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


@pytest.mark.parametrize("prevent", [False, True])
async def test_dom_same_origin_link_requires_actual_navigation(channel, prevent):
    from agent_computer_use.controller import ComputerUseController

    browser, ctx = channel
    destination = browser.page.url + "next"
    await browser.page.set_content(
        f'<a href="{destination}" {"onclick=\"event.preventDefault()\"" if prevent else ""}>Next</a>'
        '<a href="https://example.invalid/">External</a>'
        '<a href="/download" download>Download</a>'
        '<a href="/new" target="_blank">New window</a>')
    contract = GoalContract.from_input({
        **goal().model_dump(mode="json"), "inputs": [],
        "completion": [{"key": "status:Page URL", "value": destination}],
    })
    snapshot = await browser.observe("managed-page", ctx)
    actions = ActionBuilder(visual=True).build("goal", 1, contract, snapshot)
    assert len(actions.actions) == 1
    assert actions.details[0].label == "Next"
    host = ComputerUseController(browser, browser, selector=SelectOnlyCandidate())
    result = await host.run(SubAgentRequest("Go next", "", "dom-task",
                                           contract.model_dump(mode="json")), ctx)
    assert result.reason == ("effect_unknown" if prevent else "goal_verified")
    assert len(host.receipts) == 1


@pytest.mark.parametrize("prevent", [False, True])
async def test_dom_checkbox_requires_checked_readback(channel, prevent):
    from agent_computer_use.controller import ComputerUseController

    browser, ctx = channel
    handler = 'onclick="event.preventDefault()"' if prevent else ''
    await browser.page.set_content(
        f'<label>Allow edit<input type="checkbox" {handler} '
        'onchange="document.querySelector(\'output\').textContent=\'enabled\'"></label>'
        '<output aria-label="Result">disabled</output>')
    contract = GoalContract.from_input({
        **goal().model_dump(mode="json"), "inputs": [],
        "completion": [{"key": "status:Result", "value": "enabled"}],
    })
    snapshot = await browser.observe("managed-page", ctx)
    actions = ActionBuilder(visual=True).build("goal", 1, contract, snapshot)
    assert len(actions.actions) == 1
    assert actions.details[0].effect[0].key == "checkbox:Allow edit"
    host = ComputerUseController(browser, browser, selector=SelectOnlyCandidate())
    result = await host.run(SubAgentRequest("Enable editing", "", "dom-task",
                                           contract.model_dump(mode="json")), ctx)
    assert result.reason == ("effect_unknown" if prevent else "goal_verified")
    assert len(host.receipts) == 1


async def test_dom_navigation_fact_and_checkbox_identity_are_host_checked(channel):
    browser, ctx = channel
    actual_url = browser.page.url
    await browser.page.set_content(
        '<output aria-label="Page URL">https://example.invalid/spoof</output>'
        '<a href="http://[">Malformed</a>'
        '<label>Same<input type="checkbox"></label>'
        '<label>Same<input type="checkbox"></label>'
        '<label>Unavailable<input type="checkbox" disabled></label>')
    snapshot = await browser.observe("managed-page", ctx)
    assert next(f.value for f in snapshot.facts if f.key == "status:Page URL") == actual_url
    assert not any(f.key == "checkbox:Same" for f in snapshot.facts)
    actions = ActionBuilder(visual=True).build("goal", 1, goal(), snapshot)
    assert len(actions.actions) == 2 and actions.reason == 'visual_required'


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
@pytest.mark.parametrize("wait_for_user", [False, True])
async def test_goal_runner_sdk_dom_saves_without_a_script(
    site, chromium_required, monkeypatch, tmp_path, profile_store, layout, wait_for_user,
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
    if wait_for_user:
        from tank_backend.agents.store import WorkerStore
        from tank_backend.agents.supervisor import WorkerSupervisor
        from tank_backend.agents.task_result import TaskResult
        from tank_backend.persistence import Base, Database

        task_goal["authorization_ref"] = "current_task"
        task_goal["inputs"][0]["value"] = None
        db = Database(f"sqlite+pysqlite:///{tmp_path}/waiting.db")
        Base.metadata.create_all(db.engine)
        supervisor = WorkerSupervisor(runner, WorkerStore(db))
        waiting = await asyncio.wait_for(supervisor.run_foreground(
            agent_def=definition, prompt="Save the supplied name; preserve email",
            task_input=task_goal, timeout=10,
            authorization=SubAgentAuthorization(frozenset({"desktop", "network"})),
        ), 5)
        try:
            assert waiting.status == "waiting"
            assert runner._desktop_resource.lock.locked()
            assert len(sent) == (2 if layout == "middle" else 1)
            assert await supervisor.resume_with_answer(waiting.task_id, "Ada")
            finished = await supervisor.wait(waiting.task_id, timeout=5)
            assert finished is not None
            assert finished.status == "completed"
            results = [TaskResult.model_validate(finished.task_result).model_dump(mode="json")]
            assert results[0]["details"]["goal_version"] == 2
            receipts = results[0]["details"]["receipts"]
            assert receipts[0]["goal_version"] == 1 and receipts[-1]["goal_version"] == 2
        finally:
            supervisor.stop(waiting.task_id)
            await supervisor.wait(waiting.task_id, timeout=5)
            db.dispose()
        assert not runner._desktop_resource.lock.locked()
    else:
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
    if not wait_for_user:
        assert any(record.operation == "computer_use.dispatch" for record in audits)
    assert "never-in-plugin-config" not in repr(results) + repr(audits)
    first_count = len(sent)
    first_refs = {element["ref"] for element in sent[0]["state"]["snapshot"]["elements"]}
    next_goal = {
        **task_goal, "goal_id": "next-name", "authorization_ref": "next-dom",
        "intent": "Save Grace; preserve email", "objective": "Save display name Grace",
        "inputs": [{"key": "name", "purpose": "profile display name", "value": "Grace"}],
        "completion": [{"key": "status:Saved name", "value": "Grace"},
                       {"key": "status:Saved email", "value": "unchanged@example.test"}],
    }
    next_outputs = [output async for output in runner.run_agent(
        definition, [], task_id="next-dom", task_input=next_goal,
        authorization=SubAgentAuthorization(frozenset({"desktop", "network"})),
    )]
    next_results = [out.metadata["task_result"] for out in next_outputs if "task_result" in out.metadata]
    assert len(next_results) == 1 and next_results[0]["status"] == "completed"
    assert next_results[0]["cleanup"] == "confirmed"
    assert next_results[0]["details"]["goal_version"] == 1
    next_refs = {element["ref"] for element in sent[first_count]["state"]["snapshot"]["elements"]}
    assert first_refs.isdisjoint(next_refs)
    assert len(sent) == first_count * 2 and closed == [True, True]
    assert profile_store == {"name": "Grace", "email": "unchanged@example.test", "saves": "2"}
    assert not runner._desktop_resource.lock.locked()


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
    row["result"]["reason"] = "no_progress" if control in {"ambiguous", "need_more_context"} else control
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


@pytest.mark.parametrize("mode,jev_control,visual_declared", [
    ("llm", True, False), ("jev-fallback", True, False), ("jev-vision", True, True),
    ("jev-action-vision", False, True), ("jev-action-vision", True, True),
    ("jev-action-vision", True, False),
])
async def test_runner_candidate_strategy_selects_fill_and_submit(site, chromium_required, monkeypatch, tmp_path, mode, jev_control, visual_declared):
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
    jev_model = "jev-1.14.0" if mode == "jev-action-vision" else "jev-1.13.0"
    class Observer:
        def on_event(self, kind, metadata):
            events.append((kind, metadata))
    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            data = json.loads(request.content)
            calls.append(data)
            if "questions" in data:
                criteria = data["questions"]["next_action"]["criteria"]
                selected = "none" if jev_control else next(k for k, v in criteria.items() if isinstance(v, dict))
                return httpx.Response(200, json={"model": jev_model, "answers": {"next_action": {
                    "type": "choice", "choice": selected, "confidence": 1,
                    "probabilities": {k: int(k == selected) for k in criteria}}},
                    "usage": {"input_tokens": 12, "output_tokens": 0}})
            content = data["messages"][1]["content"]
            if mode in {"jev-vision", "jev-action-vision"}:
                assert content[1]["type"] == "image_url"
                assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
                content = content[0]["text"]
            question = json.loads(content)
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
                                 "model": jev_model, "credential_env": "S3_TEST_JEV_KEY"}},
        "subagents": {"agent-computer-use:agent": {"config": {"browser": {"scope": "managed-page", "url": site},
                                                              "selector": mode}}}})
    definition_file = tmp_path / "strategy.md"
    definition_file.write_text("---\nname: strategy\nextension: agent-computer-use:agent\nmodel: default\ndecision-model: jev\n---\nUse the declared task.\n")
    if visual_declared:
        definition_file.write_text(definition_file.read_text().replace(
            "model: default\n", "model: default\nvisual-model: default\n"))
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
    if mode == "jev-action-vision" and not visual_declared:
        assert result["reason"] == "visual_model_unavailable" and result["cleanup"] == "confirmed"
        assert len(calls) == 1 and "questions" in calls[0]
        assert not result["details"]["receipts"]
        return
    assert result["status"] == "completed" and result["cleanup"] == "confirmed", result
    assert all(f["key"] != "status:Records" for p in calls if "questions" in p
               for f in p["state"]["snapshot"]["facts"])
    if mode == "jev-action-vision" and not jev_control:
        assert all("questions" in p for p in calls), "unique text actions need no images"
    assert len(result["details"]["receipts"]) == 2
    assert len(calls) == (4 if mode in {"jev-fallback", "jev-vision"} or mode == "jev-action-vision" and jev_control else 2)
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


@pytest.mark.parametrize("layout", ["plain", "panel", "middle"])
@pytest.mark.parametrize("focus_mode", [False, True])
async def test_runner_advisor_returns_to_jev_for_multistep_goal(
    site, chromium_required, profile_store, monkeypatch, layout, focus_mode,
):
    import json
    import httpx
    from unittest.mock import MagicMock
    from tank_backend.agents.approval import PendingToolCallStore, ToolApprovalPolicy
    from tank_backend.agents.definition import AgentDefinition
    from tank_backend.agents.resources import DesktopResource
    from tank_backend.agents.runner import AgentRunner
    from tank_backend.config.app_config import AppConfig
    from tank_backend.pipeline.bus import Bus
    from tank_backend.plugin.manifest import read_manifest_from_yaml
    from tank_backend.plugin.registry import ExtensionRegistry
    from .test_ladder import profile_goal

    calls, events = [], []
    class Observer:
        def on_event(self, kind, metadata):
            events.append((kind, metadata))
    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            payload = json.loads(request.content)
            calls.append(payload)
            if "questions" in payload:
                options = payload["questions"]["next_action"]["criteria"]
                choice = "escalate" if len(calls) == 1 else next(
                    k for k, v in options.items() if isinstance(v, dict)
                    and (v["operation"] == "fill" or v.get("label") in {
                        "Personal info", "Edit profile", "Continue", "Save"}))
                return httpx.Response(200, json={"model": "jev-1.13.0", "answers": {"next_action": {
                    "type": "choice", "choice": choice, "confidence": 1,
                    "probabilities": {k: int(k == choice) for k in options}}},
                    "usage": {"input_tokens": 12, "output_tokens": 0}})
            advice = json.loads(payload["messages"][1]["content"])
            assert advice["reason"] == "escalate" and "milestones" not in advice["state"]["goal"]
            choice = next(k for k, v in advice["actions"].items()
                          if v["label"] in {"Personal info", "Edit profile"})
            response = {"kind": "focus", "focus": {"objective": "Open the editing region",
                "completion": advice["actions"][choice]["effect"]}} if focus_mode else {
                    "kind": "candidate", "candidate_id": choice}
            return httpx.Response(200, json={"id": "advice", "object": "chat.completion", "created": 1,
                "model": "planner", "choices": [{"index": 0, "finish_reason": "stop", "message": {
                    "role": "assistant", "content": json.dumps(response)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)
    monkeypatch.setenv("S4_ADVISOR_TEST_KEY", "fixture-key")
    registry = ExtensionRegistry()
    manifest = read_manifest_from_yaml(Path(__file__).parents[1] / "plugin.yaml")
    for extension in manifest.extensions:
        registry.register(manifest.plugin_name, extension)
    config = AppConfig.from_raw_dict({
        "llm": {"default": {"api_key": "fixture-key", "model": "planner", "base_url": "https://offline.invalid/v1",
                            "max_tokens": 512}},
        "decision_models": {"jev": {"url": "https://offline.invalid/v1/systemone",
                                   "model": "jev-1.13.0", "credential_env": "S4_ADVISOR_TEST_KEY"}},
        "subagents": {"agent-computer-use:agent": {"config": {
            "browser": {"scope": "managed-page", "url": site + "goal/" + layout},
            "selector": "jev", "advisor": "llm"}}}})
    definition = AgentDefinition("advisor-test", "test", "Use the declared task",
                                 extension="agent-computer-use:agent", model="default", decision_model="jev")
    runner = AgentRunner(MagicMock(), MagicMock(), Bus(), ToolApprovalPolicy(computer_mode="allow"),
                        PendingToolCallStore(), {definition.name: definition}, registry=registry,
                        app_config=config, desktop_resource=DesktopResource())
    task = {**profile_goal(), "scope": "managed-page", "authorization_ref": "current_task"}
    outputs = [o async for o in runner.run_agent(definition, [], task_id="advisor-test", task_input=task,
        authorization=SubAgentAuthorization(frozenset({"desktop", "network"})), observer=Observer())]
    result = next(o.metadata["task_result"] for o in outputs if "task_result" in o.metadata)
    assert result["status"] == "completed" and result["cleanup"] == "confirmed"
    assert profile_store == {"name": "Ada", "email": "unchanged@example.test", "saves": "1"}
    assert len(calls) == (5 if layout == "middle" else 4) + int(focus_mode)
    assert sum("questions" not in c for c in calls) == 1
    assert "questions" in calls[-1]  # the Advisor returned control to the regular selector
    history = calls[-1]["state"]["recent_actions"]
    assert history[0]["selected_by"] == ("selector" if focus_mode else "advisor")
    assert history[0]["label"] in {"Personal info", "Edit profile"}
    filled = next(step for step in history if step["operation"] == "fill")
    assert filled["value"] == "Ada" and filled["effect_status"] == "verified"
    assert filled["changes"] == [{"key": "target_value", "before": "Bob", "after": "Ada"}]
    assert all("action_id" not in step and "target_ref" not in step for step in history)
    assert sum(k == "computer_use_advisor" and e["phase"] == "returned" for k, e in events) == 1
    if focus_mode:
        assert calls[2]["state"]["progress"]["current_focus"]["proposal"]["objective"] == "Open the editing region"
        assert calls[3]["state"]["progress"]["current_focus"] is None
        assert result["details"]["progress"]["focus_history"][0]["status"] == "completed"
        assert calls[2]["state"]["goal"]["completion"] == task["completion"]
    usage = [e for k, e in events if k == "model_call" and e["phase"] == "finished"]
    assert sum(e["prompt_tokens"] + e["completion_tokens"] for e in usage) == (len(calls) - 1) * 12 + 15


def test_vision_route_prepares_new_tasks_without_clients(monkeypatch, tmp_path):
    import json
    import httpx
    import httpx2
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_vision_route as pilot

    def forbidden(*args, **kwargs):
        raise AssertionError('offline preparation allocated a client')
    monkeypatch.setattr(httpx, 'AsyncClient', forbidden)
    monkeypatch.setattr(httpx2, 'AsyncClient', forbidden)
    frozen = pilot.prepare(tmp_path / 'pilot')
    assert len(frozen['cases']) == 12 and len(frozen['schedule']) == 24
    assert frozen['record_only'] and frozen['models']['peer']['model'] == 'google/gemini-3.8-flash'
    assert {c['layout'] for c in frozen['cases']} == {'form', 'grid', 'drawer'}
    assert pilot.load_freeze(tmp_path / 'pilot', frozen['sha256']) == frozen
    with pytest.raises(FileExistsError):
        pilot.prepare(tmp_path / 'pilot')
    disk = tmp_path / 'pilot/freeze.json'
    changed = json.loads(disk.read_text())
    changed['cases'][0]['html'] += '<p>tampered</p>'
    disk.write_text(json.dumps(changed))
    with pytest.raises(ValueError):
        pilot.load_freeze(tmp_path / 'pilot', frozen['sha256'])


def install_route_http(monkeypatch, failure=None, *, guess=False):
    import base64
    import io
    import json
    import httpx
    import httpx2
    from PIL import Image
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_vision_route as pilot
    calls = []
    payloads = []

    def answer(payload):
        payloads.append(payload)
        parts = []
        visual = 'messages' in payload
        if visual:
            assert payload['response_format'] == {'type': 'json_object'}
            parts = payload['messages'][1]['content']
            packet = json.loads(parts[0]['text'])
        else:
            packet = payload
        choices = packet['questions']['next_action']['criteria']
        offered = {k: v for k, v in choices.items() if isinstance(v, dict)}
        choice = next((k for k, v in offered.items() if v['label'] in ('Begin setup', 'Work title', 'Save work')), None)
        palette = {v['label'] for v in offered.values()} == {'Option A', 'Option B'}
        if choice is None:
            if not visual:
                choice = next(iter(offered)) if guess else 'need_more_context'
            else:
                with Image.open(io.BytesIO(base64.b64decode(parts[1]['image_url']['url'].split(',', 1)[1]))) as image:
                    choice = 'none'
                    for key, (x, y, w, h) in packet['image_candidates'].items():
                        pixel = image.convert('RGB').getpixel((int(x + w / 2), int(y + h / 2)))
                        assert isinstance(pixel, tuple)
                        r, g, b = pixel[:3]
                        if r > b * 2 and r > g * 2:
                            choice = key
        calls.append('visual' if visual else 'jev')
        if failure == 'cancel':
            raise asyncio.CancelledError
        if visual:
            result = {'id': 'fixture', 'object': 'chat.completion', 'created': 1, 'model': pilot.PEER['model'],
                    'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': json.dumps({'choice': choice})}}],
                    'usage': {'prompt_tokens': 7, 'completion_tokens': 3, 'total_tokens': 10}}
            if failure == 'unknown':
                result.pop('usage')
            if failure == 'invalid':
                result['choices'][0]['message']['content'] = '{\"choice\":\"invented\"}'
            return result
        result = {'model': pilot.JEV['model'], 'answers': {'next_action': {'type': 'choice', 'choice': choice,
                'confidence': 1, 'probabilities': {k: float(k == choice) for k in choices}}},
                'usage': {'input_tokens': 7, 'output_tokens': 3}}

        if failure == 'unknown' or failure == 'palette_unknown' and palette:
            result.pop('usage')
        return result

    monkeypatch.setattr(httpx, 'AsyncHTTPTransport', lambda **kwargs: httpx.MockTransport(
        lambda request: httpx.Response(200, json=answer(json.loads(request.content)))))
    monkeypatch.setattr(httpx2, 'AsyncHTTPTransport', lambda **kwargs: httpx2.MockTransport(
        lambda request: httpx2.Response(200, json=answer(json.loads(request.content)))))
    return calls, payloads


@pytest.mark.parametrize('arm', ['v', 'jt'])
async def test_vision_route_real_browser_returns_to_structure(chromium_required, monkeypatch, tmp_path, arm):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_vision_route as pilot
    calls, _ = install_route_http(monkeypatch)
    frozen = pilot.prepare(tmp_path / arm)
    case = next(c for c in frozen['cases'] if c['id'] == 'drawer-positive-0')
    row = await pilot.run_task(case, arm, tmp_path / arm, jev_credential='fixture', peer_credential='fixture')
    assert row['strict_completed'] and row['cleanup_confirmed'], row
    assert row['page_state']['trail'] == case['oracle']['events']
    assert calls == (['visual'] * 3 if arm == 'v' else ['jev', 'visual', 'jev'])
    assert row['rules_actions'] == 1
    assert row['visual_captures'] == (3 if arm == 'v' else 1)
    assert row['usage']['total_tokens'] == 30


@pytest.mark.parametrize('failure', [None, 'unknown', 'invalid', 'cleanup'])
async def test_vision_route_batch_retains_denominators_and_hard_stops(chromium_required, monkeypatch, tmp_path, failure):
    import json
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_vision_route as pilot
    calls, payloads = install_route_http(monkeypatch, failure)
    if failure == 'cleanup':
        close = pilot.dom.ManagedChromiumChannel.aclose
        async def fail_close(self):
            await close(self)
            raise RuntimeError('reported cleanup failure')
        monkeypatch.setattr(pilot.dom.ManagedChromiumChannel, 'aclose', fail_close)
    frozen = pilot.prepare(tmp_path / 'batch')
    result = await pilot.run_batch(tmp_path / 'batch', frozen['sha256'], jev_credential='fixture', peer_credential='fixture')
    assert len(result['rows']) == 24
    assert len({r['id'] for r in result['rows']}) == 24
    assert all('oracle' not in json.dumps(p) for p in payloads)
    if failure in ('unknown', 'cleanup'):
        assert not result['completed']
        assert len(calls) == (1 if failure == 'unknown' else 2)
        assert sum(r['status'] == 'not_run' for r in result['rows']) == 23
        assert result['spend']['stop_reason'] == ('unknown_usage' if failure == 'unknown' else 'cleanup_failed')
    else:
        assert result['completed']
        assert all(r['cleanup_confirmed'] for r in result['rows'])
        if failure is None:
            assert all(r['strict_completed'] for r in result['rows'] if r['scenario'] == 'positive')
            assert all(r['negative_passed'] for r in result['rows'] if r['scenario'] != 'positive')
            assert sum(r['strict_completed'] for r in result['rows']) == 12
        else:
            assert any(not r['strict_completed'] and r['capped_completion_ms'] == 120000 for r in result['rows'] if r['scenario'] == 'positive')
    assert result['spend'] == json.loads((tmp_path / 'batch/spend.jsonl').read_text().splitlines()[-1])
    with pytest.raises(FileExistsError):
        await pilot.run_batch(tmp_path / 'batch', frozen['sha256'], jev_credential='fixture', peer_credential='fixture')


async def test_vision_route_private_oracle_cannot_choose_or_fix_actions(chromium_required, monkeypatch, tmp_path):
    import json
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_vision_route as pilot
    calls, payloads = install_route_http(monkeypatch)
    frozen = pilot.prepare(tmp_path / 'private')
    case = next(c for c in frozen['cases'] if c['id'] == 'drawer-positive-1')
    expected = case['oracle']['events']
    case['oracle'] = {'red': 'PRIVATE_ORACLE_SENTINEL', 'events': ['PRIVATE_ORACLE_SENTINEL']}
    row = await pilot.run_task(case, 'jt', tmp_path / 'private', jev_credential='fixture', peer_credential='fixture')
    assert calls == ['jev', 'visual', 'jev']
    assert row['page_state']['trail'] == expected
    assert not row['strict_completed']
    assert 'PRIVATE_ORACLE_SENTINEL' not in json.dumps(payloads)


async def test_vision_route_cancellation_preserves_all_rows(chromium_required, monkeypatch, tmp_path):
    import json
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_vision_route as pilot
    calls, _ = install_route_http(monkeypatch, 'cancel')
    frozen = pilot.prepare(tmp_path / 'cancel')
    with pytest.raises(asyncio.CancelledError):
        await pilot.run_batch(tmp_path / 'cancel', frozen['sha256'], jev_credential='fixture', peer_credential='fixture')
    result = json.loads((tmp_path / 'cancel/result.json').read_text())
    assert len(result['rows']) == 24 and len(calls) == 1
    assert result['rows'][0]['status'] == 'cancelled'
    assert result['rows'][0]['cleanup_confirmed']
    assert sum(r['status'] == 'not_run' for r in result['rows']) == 23


@pytest.mark.parametrize('observer_raises', [False, True])
async def test_dom_freshness_records_exact_pixel_refusal(channel, observer_raises):
    import hashlib
    from dataclasses import replace
    from agent_computer_use.contracts import Action, Binding
    browser, ctx = channel
    events = []
    class Observer:
        def on_event(self, kind, metadata):
            events.append((kind, metadata))
            if observer_raises:
                raise RuntimeError('observer unavailable')
    object.__setattr__(ctx, 'observer', Observer())
    await browser.page.set_content('<canvas width="200" height="80"></canvas><button>Save</button>')
    snapshot = await browser.observe('managed-page', ctx)
    target = next(e for e in snapshot.elements if e.label == 'Save')
    binding = Binding('goal', 1, snapshot.observation_id, snapshot.scope, snapshot.generation, 'candidates')
    action = Action('save', target.ref, 'click', None)
    previous = await browser.capture(snapshot, ctx)
    await browser.page.locator('canvas').evaluate("n => {const c=n.getContext('2d');c.fillStyle='red';c.fillRect(0,0,20,20)}")
    assert not await browser.is_current(binding, action, ctx)
    assert len(events) == 1 and events[0][0] == 'computer_use_freshness'
    meta = events[0][1]
    assert meta['channel'] == 'dom' and meta['stage'] == 'frame_scene'
    assert meta['action_id'] == 'save' and meta['observation_id'] == snapshot.observation_id
    assert meta['expected_sha256'] == hashlib.sha256(previous.png).hexdigest()
    assert meta['current_sha256'] != meta['expected_sha256']
    assert set(meta) == {'channel', 'stage', 'action_id', 'observation_id', 'expected_sha256', 'current_sha256'}
    assert not await browser.is_current(replace(binding, observation_id='old'), action, ctx)
    assert events[-1][1]['stage'] == 'binding'


async def test_dom_freshness_diagnostic_saves_internal_frames_without_models(chromium_required, monkeypatch, tmp_path):
    import httpx
    import httpx2
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import dom_visual_freshness as pilot
    def forbidden(*args, **kwargs):
        raise AssertionError('diagnosis allocated a model client')
    monkeypatch.setattr(httpx, 'AsyncClient', forbidden)
    monkeypatch.setattr(httpx2, 'AsyncClient', forbidden)
    result = await pilot.run(tmp_path / 'diagnosis')
    assert len(result['contexts']) == 6 and len(result['checks']) == 48
    assert result['model_calls'] == 0 and result['task_inputs'] == 0
    assert all(c['cleanup_confirmed'] for c in result['contexts'])
    assert all(c['dom_unchanged'] for c in result['checks'])
    assert all(c['current'] for c in result['checks'] if c['policy'] == 'hide')
    assert len(list((tmp_path / 'diagnosis').glob('*/*.png'))) == 54
    for check in result['checks']:
        assert check['current'] == (check['expected_sha256'] == check['current_sha256'])
        if not check['current']:
            assert check['refusals'][0]['stage'] == 'frame_scene'
            assert check['refusals'][0]['current_sha256'] == check['current_sha256']
    with pytest.raises(FileExistsError):
        await pilot.run(tmp_path / 'diagnosis')


async def test_dom_freshness_ignores_native_caret(channel):
    browser, ctx = channel
    await browser.page.set_content('<form><label>Name<input value="Launch"></label><button>Save</button></form>')
    await browser.page.get_by_role('textbox').focus()
    offered = await actions(browser, ctx)
    snapshot = browser.previous
    before = browser.view
    await browser.capture(snapshot, ctx)
    for _ in range(4):
        await asyncio.sleep(.3)
        assert await browser.is_current(offered.binding, offered.actions[0], ctx)
        assert await browser.read(browser.bound_frame(), ctx) == before
    assert await browser.page.get_by_role('textbox').input_value() == 'Launch'
    assert await browser.page.get_by_role('textbox').evaluate('n => n === document.activeElement')
    assert await browser.page.get_by_role('textbox').get_attribute('style') is None


@pytest.mark.parametrize('change,stage', [('pixels', 'frame_scene'), ('value', 'frame_scene'),
    ('replacement', 'dom_state'), ('navigation', 'navigation'), ('binding', 'binding'),
    ('action', 'selected_action'), ('authority', None)])
async def test_dom_freshness_keeps_real_change_guards(channel, change, stage):
    from dataclasses import replace
    from tank_backend.agents.subagent import SubAgentStopped
    browser, ctx = channel
    events = []
    class Observer:
        def on_event(self, kind, metadata):
            if kind == 'computer_use_freshness':
                events.append(metadata)
    object.__setattr__(ctx, 'observer', Observer())
    await browser.page.set_content('''<canvas width="100" height="40"></canvas><form onsubmit="event.preventDefault();window.sent++">
        <label>Name<input value="Launch"></label><button>Save</button></form><script>window.sent=0</script>''')
    await browser.page.get_by_role('textbox').focus()
    offered = await actions(browser, ctx)
    action, binding = offered.actions[0], offered.binding
    await browser.capture(browser.previous, ctx)
    if change == 'pixels':
        await browser.page.locator('canvas').evaluate("n => n.getContext('2d').fillRect(0,0,10,10)")
    elif change == 'value':
        await browser.page.get_by_role('textbox').evaluate("n => n.value='Changed'")
    elif change == 'replacement':
        await browser.page.get_by_role('button').evaluate('n => n.replaceWith(n.cloneNode(true))')
    elif change == 'navigation':
        await browser.page.reload()
    elif change == 'binding':
        binding = replace(binding, observation_id='old')
    elif change == 'action':
        action = replace(action, target_ref='not-offered')
    else:
        ctx.authorization.revoke()
        with pytest.raises(SubAgentStopped):
            await browser.dispatch(binding, action, ctx)
        assert await browser.page.evaluate('window.sent') == 0
        return
    receipt = await browser.dispatch(binding, action, ctx)
    assert receipt.status == 'not_sent'
    assert events[-1]['stage'] == stage
    if change != 'navigation':
        assert await browser.page.evaluate('window.sent') == 0


async def test_dom_freshness_records_capture_race(channel, monkeypatch):
    from tank_backend.agents.subagent import SubAgentStopped
    browser, ctx = channel
    events = []
    class Observer:
        def on_event(self, kind, metadata):
            if kind == 'computer_use_freshness':
                events.append(metadata)
    object.__setattr__(ctx, 'observer', Observer())
    offered = await actions(browser, ctx)
    original = browser.visual_png
    async def changing_frame():
        png = await original()
        await browser.page.get_by_role('textbox').evaluate("n => n.value='Changed'")
        return png
    monkeypatch.setattr(browser, 'visual_png', changing_frame)
    with pytest.raises(SubAgentStopped, match='stale_reference'):
        await browser.capture(browser.previous, ctx)
    assert events[-1]['stage'] == 'capture_state'
    assert events[-1]['observation_id'] == offered.binding.observation_id
    assert browser.visual_frame is None


def test_route_followup_prepares_real_semantic_gap_without_clients(monkeypatch, tmp_path):
    import httpx
    import httpx2
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_vision_route as pilot
    def forbidden(*args, **kwargs):
        raise AssertionError('preparation allocated a model client')
    monkeypatch.setattr(httpx, 'AsyncClient', forbidden)
    monkeypatch.setattr(httpx2, 'AsyncClient', forbidden)
    legacy = pilot.prepare(tmp_path / 'legacy')
    frozen = pilot.prepare(tmp_path / 'followup', followup=True)
    assert len(legacy['schedule']) == 24 and len(frozen['schedule']) == 36
    assert frozen['cases'][:12] == legacy['cases']
    assert frozen['followup'] and frozen['revision'] == 'vision-route-2'
    gaps = [c for c in frozen['cases'] if c['scenario'].startswith('fallback')]
    assert len(gaps) == 6
    assert all('aria-label="Option A"' in c['html'] and 'aria-label="Option B"' in c['html'] for c in gaps)
    assert pilot.load_freeze(tmp_path / 'followup', frozen['sha256']) == frozen


@pytest.mark.parametrize('layout', ['grid', 'drawer'])
async def test_route_followup_abstention_uses_same_palette_binding(chromium_required, monkeypatch, tmp_path, layout):
    import json
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_vision_route as pilot
    calls, payloads = install_route_http(monkeypatch)
    frozen = pilot.prepare(tmp_path / layout, followup=True)
    case = next(c for c in frozen['cases'] if c['id'] == f'{layout}-fallback-0')
    row = await pilot.run_task(case, 'jt', tmp_path / layout, jev_credential='fixture', peer_credential='fixture')
    assert row['strict_completed'] and row['cleanup_confirmed'], row
    assert calls == (['jev', 'visual'] if layout == 'grid' else ['jev', 'jev', 'visual', 'jev'])
    peers = [p for p in payloads if 'messages' in p]
    assert len(peers) == 1
    packet = json.loads(peers[0]['messages'][1]['content'][0]['text'])
    text = next(p for p in payloads if 'questions' in p and {v['label'] for v in p['questions']['next_action']['criteria'].values() if isinstance(v, dict)} == {'Option A', 'Option B'})
    assert packet['state']['binding'] == text['state']['binding']
    assert packet['state']['snapshot'] == text['state']['snapshot']
    purposes = [e['purpose'] for e in row['events'] if e['kind'] == 'model_call' and e.get('phase') == 'finished']
    assert purposes.count('computer_use.visual_fallback') == 1
    assert 'computer_use.visual' not in purposes
    journal = [json.loads(line) for line in (tmp_path / layout / row['id'] / 'calls.jsonl').read_text().splitlines()]
    proof = row['fallback_proofs'][0]
    delayed = next(r for r in journal if r['call_id'] == proof['text_call_id'] and 'response' in r)
    reordered = [r for r in journal if r is not delayed] + [delayed]
    assert not pilot.palette_evidence(reordered, row['events'])['fallback_verified']
    assert all('oracle' not in p.get('state', {}) for p in payloads)


@pytest.mark.parametrize('mode', ['guess', 'unknown'])
async def test_route_followup_does_not_repair_guesses_or_unknown_usage(chromium_required, monkeypatch, tmp_path, mode):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_vision_route as pilot
    calls, _ = install_route_http(monkeypatch, 'palette_unknown' if mode == 'unknown' else None, guess=mode == 'guess')
    frozen = pilot.prepare(tmp_path / mode, followup=True)
    case = next(c for c in frozen['cases'] if c['id'] == 'grid-fallback-1')
    row = await pilot.run_task(case, 'jt', tmp_path / mode, jev_credential='fixture', peer_credential='fixture')
    assert calls == ['jev'] and row['cleanup_confirmed']
    assert row['visual_captures'] == 0
    assert not row['fallback_verified'] and not row['strict_completed']
    if mode == 'guess':
        assert row['goal_completed']
        assert len(row['palette_guesses']) == 1
        assert row['page_state']['trail'] == ['pick:a']
        assert row['capped_completion_ms'] == 120000
    else:
        assert row['usage']['unknown_calls'] == 1
        assert not row['page_state']['trail']


async def test_route_followup_absent_guess_retains_blue_terminal_state(chromium_required, monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_vision_route as pilot
    calls, _ = install_route_http(monkeypatch, guess=True)
    frozen = pilot.prepare(tmp_path / 'absent-guess', followup=True)
    case = next(c for c in frozen['cases'] if c['id'] == 'grid-fallback_absent-1')
    row = await pilot.run_task(case, 'jt', tmp_path / 'absent-guess', jev_credential='fixture', peer_credential='fixture')
    assert calls == ['jev'] and row['cleanup_confirmed']
    assert row['page_state']['trail'] == ['pick:a']
    assert row['page_state']['result'] == 'selected:blue'
    assert not row['negative_passed'] and not row['exit_correct']
    assert not row['fallback_verified'] and len(row['palette_guesses']) == 1


async def test_route_followup_full_matrix_keeps_old_tasks_and_new_fallbacks(chromium_required, monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_vision_route as pilot
    calls, _ = install_route_http(monkeypatch)
    frozen = pilot.prepare(tmp_path / 'matrix', followup=True)
    result = await pilot.run_batch(tmp_path / 'matrix', frozen['sha256'], jev_credential='fixture', peer_credential='fixture')
    assert result['completed'] and len(result['rows']) == 36
    assert len(calls) == 66
    assert all(r['strict_completed'] for r in result['rows'] if r['scenario'] in {'positive', 'fallback'})
    assert all(r['negative_passed'] for r in result['rows'] if r['scenario'] not in {'positive', 'fallback'})
    gap_jt = [r for r in result['rows'] if r['arm'] == 'jt' and r['scenario'].startswith('fallback')]
    assert len(gap_jt) == 6 and all(r['fallback_verified'] for r in gap_jt)
    assert all(not r['palette_guesses'] for r in result['rows'])
    assert all(r['cleanup_confirmed'] for r in result['rows'])


@pytest.fixture
def product_python():
    value = os.environ.get('TANK_REAL_PRODUCT_PYTHON')
    if not value:
        pytest.skip('Set TANK_REAL_PRODUCT_PYTHON to an isolated sqlite-web 0.8.1 environment')
    assert Path(value).is_file()
    return Path(value)


@pytest.fixture
def linkding_root():
    value = os.environ.get('TANK_LINKDING_ROOT')
    if not value:
        pytest.skip('Set TANK_LINKDING_ROOT to the qualified linkding 1.47.0 installation')
    root = Path(value)
    assert root.is_absolute() and (root / '.venv/bin/python').is_file()
    return root


async def test_calibration_sql_initialization_drains_repeated_cancellation(monkeypatch, tmp_path, product_python):
    import threading
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_calibration_route as pilot
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    original = pilot.shared.create_database
    def blocked(path, records):
        entered.set()
        release.wait(1)
        original(path, records)
        finished.set()
    monkeypatch.setattr(pilot.shared, 'create_database', blocked)
    case = {'seed': [{'id': n, 'title': 'Draft', 'notes': 'Keep'} for n in range(1, 5)]}
    task = asyncio.create_task(pilot.SQLiteAdapter().initialize(tmp_path, product_python, case))
    try:
        await asyncio.sleep(.05)
        assert entered.is_set() and not task.done()
        task.cancel()
        await asyncio.sleep(.01)
        task.cancel()
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()
        assert len(pilot.shared.database_state(tmp_path / 'fixture.db')['records']) == 4
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


def test_calibration_prepare_freezes_complete_goals_and_96_trials(monkeypatch, tmp_path, linkding_root, product_python, legacy_product_fingerprints):
    import json
    import httpx
    import httpx2
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_calibration_route as pilot
    def forbidden(*args, **kwargs):
        raise AssertionError('preparation allocated HTTP or a server')
    monkeypatch.setattr(httpx.AsyncClient, '__init__', forbidden)
    monkeypatch.setattr(httpx2.AsyncClient, '__init__', forbidden)
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', forbidden)
    frozen = pilot.prepare(tmp_path / 'calibration', sql_python=product_python, link_root=linkding_root)
    assert len(frozen['cases']) == 48 and len(frozen['schedule']) == 96
    assert len({c['cluster_id'] for c in frozen['cases']}) == 24
    assert frozen['max_candidates'] == 64 and frozen['formal_confirmation'] is False
    for case in frozen['cases']:
        keys = {f['key'] for f in case['goal']['completion']}
        assert 'status:Records' in keys
        assert ('status:List records' if case['product'] == 'linkding' else 'status:List rows') in keys
        if case['negative'] == 'revoked':
            records = json.loads(case['goal']['completion'][0]['value'])
            assert next(r['title'] for r in records if r['id'] == case['target']) == case['goal']['inputs'][0]['value']
    assert pilot.load_freeze(tmp_path / 'calibration', frozen['sha256']) == frozen
    (tmp_path / 'calibration/freeze.json').write_text(json.dumps({**frozen, 'max_candidates': 65}))
    with pytest.raises(ValueError):
        pilot.load_freeze(tmp_path / 'calibration', frozen['sha256'])


def test_linkding_product_prepare_freezes_qualified_tasks_without_clients(monkeypatch, tmp_path, linkding_root):
    import json
    import httpx
    import httpx2
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_linkding_route as pilot
    def forbidden(*args, **kwargs):
        raise AssertionError('preparation allocated HTTP or a server')
    monkeypatch.setattr(httpx.AsyncClient, '__init__', forbidden)
    monkeypatch.setattr(httpx2.AsyncClient, '__init__', forbidden)
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', forbidden)
    frozen = pilot.prepare(tmp_path / 'linkding', app_root=linkding_root)
    assert len(frozen['cases']) == 2 and len(frozen['schedule']) == 4
    assert [c['target'] for c in frozen['cases']] == [1, 2]
    assert [s['arm'] for s in frozen['schedule']] == ['v', 'jt', 'jt', 'v']
    assert len(frozen['app']['source_files']) == 446
    assert frozen['app']['versions']['django'] == '6.0.7'
    assert frozen['app']['environment_files'] and frozen['source_sha256']
    assert pilot.load_freeze(tmp_path / 'linkding', frozen['sha256']) == frozen
    with pytest.raises(FileExistsError):
        pilot.prepare(tmp_path / 'linkding', app_root=linkding_root)
    (tmp_path / 'linkding/freeze.json').write_text(json.dumps({**frozen, 'seconds_per_task': 121}))
    with pytest.raises(ValueError):
        pilot.load_freeze(tmp_path / 'linkding', frozen['sha256'])


def test_real_product_prepare_has_no_clients_or_server(monkeypatch, tmp_path, product_python):
    import httpx
    import httpx2
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_real_product_route as pilot
    def forbidden(*args, **kwargs):
        raise AssertionError('preparation allocated HTTP or a server')
    monkeypatch.setattr(httpx.AsyncClient, '__init__', forbidden)
    monkeypatch.setattr(httpx2.AsyncClient, '__init__', forbidden)
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', forbidden)
    frozen = pilot.prepare(tmp_path / 'product', app_python=product_python)
    assert len(frozen['cases']) == 6 and len(frozen['schedule']) == 12
    assert frozen['app']['versions']['sqlite-web'] == '0.8.1'
    assert frozen['app']['files'] and frozen['source_sha256']
    assert pilot.load_freeze(tmp_path / 'product', frozen['sha256']) == frozen
    with pytest.raises(FileExistsError):
        pilot.prepare(tmp_path / 'product', app_python=product_python)
    import json
    (tmp_path / 'product/freeze.json').write_text(json.dumps({**frozen, 'seconds_per_task': 121}))
    with pytest.raises(ValueError):
        pilot.load_freeze(tmp_path / 'product', frozen['sha256'])


def install_product_http(monkeypatch, failure=None):
    import base64
    import json
    import httpx
    import httpx2
    from benchmarks.computer_use import jev_vision_route as base
    calls, packets = [], []
    def answer(payload):
        visual = 'messages' in payload
        packet = json.loads(payload['messages'][1]['content'][0]['text']) if visual else payload
        packets.append(packet)
        offered = {k: v for k, v in packet['questions']['next_action']['criteria'].items() if isinstance(v, dict)}
        intent = packet['state']['goal']['intent']
        selected = next((k for k, v in offered.items() if v['label'] == 'Retry'), None)
        if selected is None:
            selected = next((k for k, v in offered.items() if v['operation'] == 'fill'), None)
        if packet['state']['goal']['goal_id'].startswith('cal-'):
            import re
            identity = packet['state']['goal']['outcomes'][0]['conditions'][0]['key'].removeprefix('status:Editor seen:')
            target = identity.rsplit('/', 1)[-1]
            if failure == 'wrong_record':
                target = '1' if target != '1' else '4'
            if selected is None:
                selected = next((k for k, v in offered.items() if v['label'] == 'Allow updating this column. [name=chk_title]'
                                 and v['current_value'] == 'false'), None)
            if selected is None:
                selected = next((k for k, v in offered.items() if v['role'] == 'button' and v['label'] in ('Update', 'Save')), None)
            if selected is None:
                selected = next((k for k, v in offered.items() if v['label'] == 'Edit' and (
                    any(kind == 'row' and name.split()[0] == target for kind, name in v['ancestors'])
                    or any(re.search(r'/bookmarks/' + target + r'/edit(?:\?|$)', f['value']) for f in v['effect']))), None)
            offered = offered if selected is not None else {}
        if selected is None and packet['state']['goal']['scope'] == 'linkding':
            target = '2' if 'item-2' in intent else '1'
            if failure == 'wrong_record':
                target = '1' if target == '2' else '2'
            selected = next((k for k, v in offered.items() if v['label'] == 'Save' and v['role'] == 'button'), None)
            if selected is None:
                selected = next((k for k, v in offered.items() if v['label'] == 'Edit'
                                 and any(f'/bookmarks/{target}/edit?' in f['value'] for f in v['effect'])), None)
        if selected is None and intent.startswith('Create'):
            selected = next((k for k, v in offered.items() if v['label'] == 'Insert' and v['role'] == 'button'), None) or next((k for k, v in offered.items() if v['label'] == 'Insert'), None)
        if selected is None and not intent.startswith('Create'):
            checkbox_label = 'Allow updating this column. [name=chk_title]' if intent.startswith('Starting from') else 'include all columns'
            selected = next((k for k, v in offered.items() if v['label'] == checkbox_label and v['current_value'] == 'false'), None)
            if selected is None:
                selected = next((k for k, v in offered.items() if v['label'] == 'Update'), None)
            if selected is None:
                if intent.startswith('Starting from'):
                    target = '2' if 'id 2 ' in intent else '1'
                    if failure == 'wrong_record':
                        target = '1' if target == '2' else '2'
                    selected = next((k for k, v in offered.items() if v['label'] == 'Edit'
                                     and any(kind == 'row' and name.split()[0] == target for kind, name in v['ancestors'])), None)
                else:
                    token = base64.urlsafe_b64encode(b'[2]' if 'id 2 ' in intent else b'[1]').decode().rstrip('=')
                    selected = next((k for k, v in offered.items() if v['label'] == 'Edit' and any('/update/' + token + '/' in f['value'] for f in v['effect'])), None)
        choice = 'not-offered' if failure == 'invalid' else 'none' if failure == 'wrong' else selected or 'none'
        calls.append('peer' if visual else 'jev')
        if failure == 'cancel':
            raise asyncio.CancelledError
        if visual:
            result = {'id': 'fixture', 'object': 'chat.completion', 'created': 1, 'model': base.PEER['model'],
                      'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': json.dumps({'choice': choice})}}],
                      'usage': {'prompt_tokens': 7, 'completion_tokens': 3, 'total_tokens': 10}}
        else:
            result = {'model': base.JEV['model'], 'answers': {'next_action': {'type': 'choice', 'choice': choice,
                      'confidence': 1, 'probabilities': {k: float(k == choice) for k in packet['questions']['next_action']['criteria']}}},
                      'usage': {'input_tokens': 7, 'output_tokens': 3}}
        if failure == 'unknown':
            result.pop('usage')
        return result
    monkeypatch.setattr(httpx, 'AsyncHTTPTransport', lambda **kwargs: httpx.MockTransport(
        lambda request: httpx.Response(200, json=answer(json.loads(request.content)))))
    monkeypatch.setattr(httpx2, 'AsyncHTTPTransport', lambda **kwargs: httpx2.MockTransport(
        lambda request: httpx2.Response(200, json=answer(json.loads(request.content)))))
    return calls, packets


async def test_calibration_controller_completes_four_record_sql_list(chromium_required, monkeypatch, tmp_path, linkding_root, product_python, legacy_product_fingerprints):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_calibration_route as pilot
    calls, _ = install_product_http(monkeypatch)
    frozen = pilot.prepare(tmp_path / 'calibration', sql_python=product_python, link_root=linkding_root)
    case = next(c for c in frozen['cases'] if c['product'] == 'sqlite-web' and c['group'] == 'normal'
                and c['target'] == 4 and c['condition'] == 'cold')
    row = await pilot.run_task(case, 'jt', tmp_path / 'calibration', frozen=frozen,
                              jev_credential='fixture', peer_credential='fixture')
    assert row['strict_completed'] and row['cleanup_confirmed'], row
    assert len(row['database']['records']) == 4
    assert len(calls) == 4


async def test_calibration_reconciles_real_sdk_wire_usage(
    chromium_required, monkeypatch, tmp_path, linkding_root, product_python, legacy_qualification_host,
    legacy_product_fingerprints,
):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_audit as audit
    from benchmarks.computer_use import jev_calibration_route as calibration
    from benchmarks.computer_use import jev_fake_http
    from benchmarks.computer_use import jev_qualification as qualification
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit

    root = tmp_path / "qualification"
    frozen = qualification.prepare(root)
    case = next(
        c
        for c in frozen["cases"]
        if c["condition"] == "cold"
        and c["reserved_rank"] == 1
        and c["reserved_stratum"] == "sqlite-web/recovery-editor"
    )
    ledger = SpendLedger(SpendLimit(0, 0), record_only=True)
    try:
        with jev_fake_http.offline_http(
            jev_fake_http.reply, root / "transport.jsonl"
        ) as wire:
            wire["active_trial"] = case["id"] + "-jt"
            row = await calibration.run_task(
                case,
                "jt",
                root,
                frozen=frozen,
                ledger=ledger,
                jev_credential="qualification-fake",
                peer_credential="qualification-fake",
            )
            audit.audit_trial(case, row, root / row["id"])
            audit.audit_usage(row, ledger.snapshot(), wire["requests"])
            assert {r["provider"] for r in wire["requests"]} == {"jev", "peer"}
            assert wire["blocked_external"] == []
    finally:
        ledger.close()


@pytest.mark.parametrize("negative", [False, True])
async def test_calibration_raw_dispatch_and_cleanup_evidence(
    chromium_required, monkeypatch, tmp_path, linkding_root, product_python, negative,
    legacy_product_fingerprints,
):
    import json

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_calibration_route as pilot

    install_product_http(monkeypatch)
    root = tmp_path / "calibration"
    frozen = pilot.prepare(root, sql_python=product_python, link_root=linkding_root)
    case = next(
        c
        for c in frozen["cases"]
        if c["product"] == "sqlite-web"
        and c["condition"] == "cold"
        and (c["negative"] == "revoked" if negative else c["group"] == "normal")
    )
    row = await pilot.run_task(
        case,
        "jt",
        root,
        frozen=frozen,
        jev_credential="fixture",
        peer_credential="fixture",
    )
    path = root / row["id"]
    witness = [
        json.loads(line)
        for line in (path / "dispatch-witness.jsonl").read_text().splitlines()
    ]
    assert any(w["phase"] == "current" and w["current"] for w in witness)
    if negative:
        assert row["negative_passed"] and witness[-1]["phase"] == "blocked"
        assert witness[-1]["native_called"] is False
    else:
        assert row["strict_completed"] and witness[-1]["phase"] == "returned"
        assert witness[-1]["status"] == "sent"
    proof = json.loads((path / "cleanup-proof.json").read_text())
    assert proof["process_returncode"] is not None
    assert proof["channel_closed"] and proof["browser_closed"]
    assert proof["audit_failed"] is False
    import hashlib

    assert (
        proof["files"]["after.db"]
        == hashlib.sha256((path / "after.db").read_bytes()).hexdigest()
    )
    assert (
        proof["files"]["dispatch-witness.jsonl"]
        == hashlib.sha256((path / "dispatch-witness.jsonl").read_bytes()).hexdigest()
    )
    assert json.loads((path / "events.json").read_text()) == row["events"]
    assert "<html" in (path / "final.html").read_text().lower()


async def test_calibration_independent_audit_recomputes_goal_and_refuses_tamper(
    chromium_required, monkeypatch, tmp_path, linkding_root, product_python,
    legacy_product_fingerprints,
):
    import json

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import (
        jev_calibration_route as pilot,
        jev_audit as audit,
    )

    install_product_http(monkeypatch)
    root = tmp_path / "calibration"
    frozen = pilot.prepare(root, sql_python=product_python, link_root=linkding_root)
    case = next(
        c
        for c in frozen["cases"]
        if c["product"] == "sqlite-web"
        and c["group"] == "normal"
        and c["condition"] == "cold"
    )
    row = await pilot.run_task(
        case,
        "jt",
        root,
        frozen=frozen,
        jev_credential="fixture",
        peer_credential="fixture",
    )
    path = root / row["id"]
    row["strict_completed"] = False
    label = audit.audit_trial(case, row, path)
    assert label["strict_verified"] is True
    assert label["unexpected_action"] is False and label["critical_events"] == 0
    original_html = (path / "final.html").read_bytes()
    (path / "final.html").write_text("<html>wrong final page</html>")
    with pytest.raises(audit.EvidenceError):
        audit.audit_trial(case, row, path)
    (path / "final.html").write_bytes(original_html)
    captured = [
        json.loads(line) for line in (path / "calls.jsonl").read_text().splitlines()
    ]
    requests = [item for item in captured if "request" in item]
    packet = requests[0]["request"]
    if "messages" in packet:
        public = json.loads(packet["messages"][1]["content"][0]["text"])
        public["state"]["goal"]["intent"] = "different task"
        packet["messages"][1]["content"][0]["text"] = json.dumps(public)
    else:
        packet["state"]["goal"]["intent"] = "different task"
    row["calls"] = requests
    (path / "calls.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in captured)
    )
    proof = json.loads((path / "cleanup-proof.json").read_text())
    import hashlib

    proof["files"]["calls.jsonl"] = hashlib.sha256(
        (path / "calls.jsonl").read_bytes()
    ).hexdigest()
    (path / "cleanup-proof.json").write_text(json.dumps(proof))
    with pytest.raises(audit.EvidenceError):
        audit.audit_trial(case, row, path)


@pytest.mark.parametrize("product", ["sqlite-web", "linkding"])
@pytest.mark.parametrize("group", ["normal", "recovery", "missing", "revoked"])
async def test_calibration_independent_audit_covers_product_outcomes(
    chromium_required,
    monkeypatch,
    tmp_path,
    linkding_root,
    product_python,
    product,
    group,
    legacy_product_fingerprints,
):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import (
        jev_calibration_route as pilot,
        jev_audit as audit,
    )

    install_product_http(monkeypatch)
    root = tmp_path / "calibration"
    frozen = pilot.prepare(root, sql_python=product_python, link_root=linkding_root)
    case = next(
        c
        for c in frozen["cases"]
        if c["product"] == product
        and c["condition"] == "cold"
        and (
            c["negative"] == group
            if group in ("missing", "revoked")
            else c["group"] == group
        )
    )
    row = await pilot.run_task(
        case,
        "jt",
        root,
        frozen=frozen,
        jev_credential="fixture",
        peer_credential="fixture",
    )
    label = audit.audit_trial(case, row, root / row["id"])
    assert label["strict_verified"] is (group in ("normal", "recovery"))
    assert label["negative_verified"] is (group in ("missing", "revoked"))
    assert label["recovery_verified"] is (group == "recovery")
    assert label["critical_events"] == 0 and label["unexpected_action"] is False


async def test_calibration_known_goal_failure_is_not_a_safety_incident(
    chromium_required, monkeypatch, tmp_path, linkding_root, product_python,
    legacy_product_fingerprints,
):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import (
        jev_calibration_route as pilot,
        jev_audit as audit,
    )

    install_product_http(monkeypatch, "invalid")
    root = tmp_path / "calibration"
    frozen = pilot.prepare(root, sql_python=product_python, link_root=linkding_root)
    case = next(
        c
        for c in frozen["cases"]
        if c["product"] == "sqlite-web"
        and c["group"] == "normal"
        and c["condition"] == "cold"
    )
    row = await pilot.run_task(
        case,
        "jt",
        root,
        frozen=frozen,
        jev_credential="fixture",
        peer_credential="fixture",
    )
    assert not row["strict_completed"] and not any(
        h["method"] == "POST" for h in row["http"]
    )
    label = audit.audit_trial(case, row, root / row["id"])
    assert label["strict_verified"] is False
    assert label["unexpected_action"] is False and label["critical_events"] == 0


async def test_calibration_audit_detects_extra_changes_posts_and_wrong_fault(
    chromium_required, monkeypatch, tmp_path, linkding_root, product_python,
    legacy_product_fingerprints,
):
    import hashlib
    import json
    import sqlite3

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import (
        jev_calibration_route as pilot,
        jev_audit as audit,
    )

    install_product_http(monkeypatch)
    root = tmp_path / "calibration"
    frozen = pilot.prepare(root, sql_python=product_python, link_root=linkding_root)
    case = next(
        c
        for c in frozen["cases"]
        if c["product"] == "sqlite-web"
        and c["group"] == "recovery"
        and c["condition"] == "cold"
    )
    row = await pilot.run_task(
        case,
        "jt",
        root,
        frozen=frozen,
        jev_credential="fixture",
        peer_credential="fixture",
    )
    path = root / row["id"]

    def reseal(name):
        proof = json.loads((path / "cleanup-proof.json").read_text())
        proof["files"][name] = hashlib.sha256((path / name).read_bytes()).hexdigest()
        (path / "cleanup-proof.json").write_text(json.dumps(proof))

    original_db = (path / "after.db").read_bytes()
    with sqlite3.connect(path / "after.db") as db:
        db.execute(
            "UPDATE work_items SET title='unrequested change' WHERE id!=?",
            (case["target"],),
        )
    reseal("after.db")
    label = audit.audit_trial(case, row, path)
    assert label["strict_verified"] is False and label["unexpected_action"] is True
    assert label["critical_events"] > 0
    (path / "after.db").write_bytes(original_db)
    reseal("after.db")
    with sqlite3.connect(path / "after.db") as db:
        db.execute(
            "INSERT INTO _writes (operation,id) VALUES ('update',?)", (case["target"],)
        )
    reseal("after.db")
    assert audit.audit_trial(case, row, path)["unexpected_action"] is True
    (path / "after.db").write_bytes(original_db)
    reseal("after.db")
    original_http = (path / "http.jsonl").read_text()
    http = [json.loads(line) for line in original_http.splitlines()]
    post = next(h for h in http if h["method"] == "POST")
    (path / "http.jsonl").write_text(original_http + json.dumps(post) + "\n")
    reseal("http.jsonl")
    assert audit.audit_trial(case, row, path)["unexpected_action"] is True
    next(h for h in http if h.get("injected"))["path"] = "/unregistered-fault"
    (path / "http.jsonl").write_text("".join(json.dumps(h) + "\n" for h in http))
    reseal("http.jsonl")
    with pytest.raises(audit.EvidenceError):
        audit.audit_trial(case, row, path)


async def test_calibration_dispatch_evidence_write_failure_prevents_native_send(
    chromium_required, monkeypatch, tmp_path, linkding_root, product_python,
    legacy_product_fingerprints,
):
    import json

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import (
        jev_calibration_route as pilot,
        jev_audit as audit,
    )

    install_product_http(monkeypatch)
    root = tmp_path / "calibration"
    frozen = pilot.prepare(root, sql_python=product_python, link_root=linkding_root)
    case = next(
        c
        for c in frozen["cases"]
        if c["product"] == "sqlite-web"
        and c["group"] == "normal"
        and c["condition"] == "cold"
    )
    original = Path.open

    def fail(path, *args, **kwargs):
        if path.name == "dispatch-witness.jsonl" and args and args[0] == "a":
            raise OSError("fixture evidence disk failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail)
    row = await pilot.run_task(
        case,
        "jt",
        root,
        frozen=frozen,
        jev_credential="fixture",
        peer_credential="fixture",
    )
    assert row["strict_completed"] is False and row["cleanup_confirmed"] is True
    assert not any(h["method"] == "POST" for h in row["http"])
    assert audit.physical(
        root / row["id"] / "before.db", "sqlite-web"
    ) == audit.physical(root / row["id"] / "after.db", "sqlite-web")
    proof = json.loads((root / row["id"] / "cleanup-proof.json").read_text())
    assert proof["files"]["dispatch-witness.jsonl"] is None
    with pytest.raises(audit.EvidenceError):
        audit.audit_trial(case, row, root / row["id"])


async def test_supplemental_native_cancellation_during_cleanup_is_preserved(
    chromium_required, monkeypatch, tmp_path, product_python, linkding_root, legacy_qualification_host,
    legacy_product_fingerprints,
):
    import asyncio
    import json

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_native_qualification as native
    from benchmarks.computer_use import jev_qualification as qualification
    from tank_backend.agents.task_runtime import TaskRuntime

    root = tmp_path / "qualification"
    frozen = qualification.prepare(root)
    entered, release = asyncio.Event(), asyncio.Event()
    original = TaskRuntime.aclose
    original_case = native.run_case
    attempted = []

    async def close(runtime):
        await original(runtime)
        entered.set()
        await release.wait()

    async def run_case(case, *args):
        attempted.append(case["id"])
        if len(attempted) > 1:
            raise RuntimeError("second native goal started after cancellation")
        return await original_case(case, *args)

    monkeypatch.setattr(TaskRuntime, "aclose", close)
    monkeypatch.setattr(native, "run_case", run_case)
    pending = asyncio.create_task(native.run(root, frozen["sha256"]))
    await asyncio.wait_for(entered.wait(), 20)
    pending.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await pending
    result = json.loads((root / "native/result.json").read_text())
    assert len(result["rows"]) == 96
    assert sum(r["attempted"] for r in result["rows"]) == len(attempted) == 1
    assert sum(r["status"] == "not_run" for r in result["rows"]) == 95
    assert result["stop_reason"] == "cancelled" and result["completed"] is False
    row = json.loads((root / "native" / attempted[0] / "row.json").read_text())
    assert row["status"] == "cancelled" and row["qualified"] is False
    assert row["cleanup"] is True


@pytest.mark.parametrize("product", ["sqlite-web", "linkding"])
@pytest.mark.parametrize("negative", [False, True])
async def test_supplemental_native_case_has_zero_model_calls(
    chromium_required,
    monkeypatch,
    tmp_path,
    product_python,
    linkding_root,
    product,
    negative,
    legacy_qualification_host,
    legacy_product_fingerprints,
):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_qualification as qualification
    from benchmarks.computer_use import jev_native_qualification as native
    from tank_backend.agents.task_runtime import TaskRuntime

    def forbidden(*args, **kwargs):
        raise AssertionError("native qualification must not configure model clients")

    monkeypatch.setattr(TaskRuntime, "configure_decision_model", forbidden)
    monkeypatch.setattr(TaskRuntime, "configure_visual_model", forbidden)
    root = tmp_path / "qualification"
    frozen = qualification.prepare(root)
    case = next(
        c
        for c in frozen["cases"]
        if c["product"] == product
        and c["condition"] == "cold"
        and (c["negative"] == "revoked" if negative else c["group"] == "normal")
    )
    output = root / "native"
    output.mkdir()
    row = await native.run_case(case, output, frozen)
    assert row["qualified"] and row["cleanup"] and row["model_calls"] == 0, row
    assert all(o["capture"] == "accepted" for o in row["observations"])


async def test_calibration_controller_recovers_first_sql_list_get(chromium_required, monkeypatch, tmp_path, linkding_root, product_python, legacy_product_fingerprints):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_calibration_route as pilot
    calls, _ = install_product_http(monkeypatch)
    frozen = pilot.prepare(tmp_path / 'calibration', sql_python=product_python, link_root=linkding_root)
    case = next(c for c in frozen['cases'] if c['product'] == 'sqlite-web' and c['fault_stage'] == 'list'
                and c['target'] == 4 and c['condition'] == 'cold')
    row = await pilot.run_task(case, 'jt', tmp_path / 'calibration', frozen=frozen,
                              jev_credential='fixture', peer_credential='fixture')
    assert row['strict_completed'] and row['recovery_completed'] and row['cleanup_confirmed'], row
    assert sum(h['injected'] for h in row['http']) == 1
    assert len(calls) == 5


def test_calibration_cli_freezes_before_credential_access(monkeypatch, tmp_path, linkding_root, product_python, capsys, legacy_product_fingerprints):
    import dotenv
    import json
    import sys
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_calibration_route as pilot
    def forbidden(*args, **kwargs):
        raise AssertionError('credentials read before approved executable freeze')
    monkeypatch.setattr(dotenv, 'dotenv_values', forbidden)
    output = tmp_path / 'cli-calibration'
    monkeypatch.setattr(sys, 'argv', ['calibration', '--output', str(output), '--sql-python', str(product_python),
                                    '--link-root', str(linkding_root)])
    pilot.main()
    assert json.loads(capsys.readouterr().out)['tasks'] == 96
    monkeypatch.setattr(sys, 'argv', ['calibration', '--output', str(output), '--run', '--approved-sha256', 'wrong'])
    with pytest.raises(ValueError):
        pilot.main()


async def test_calibration_all_96_trials_through_real_controller(chromium_required, monkeypatch, tmp_path, linkding_root, product_python, legacy_product_fingerprints):
    import hashlib
    import json
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_calibration_route as pilot
    calls, packets = install_product_http(monkeypatch)
    output = tmp_path / 'calibration'
    frozen = pilot.prepare(output, sql_python=product_python, link_root=linkding_root)
    for name, digest in frozen['source_sha256'].items():
        data = (Path(__file__).parents[3] / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest
        destination = output / 'source' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    result = await pilot.run_batch(output, frozen['sha256'], jev_credential='fixture', peer_credential='fixture')
    assert result['completed'] and len(result['rows']) == 96
    assert sum(r['strict_completed'] for r in result['rows']) == 80
    assert sum(r['negative_passed'] for r in result['rows']) == 16
    assert all(r['calibration_success'] and r['cleanup_confirmed'] for r in result['rows'])
    assert all('oracle' not in json.dumps(packet) for packet in packets)
    assert result['spend']['batch']['known_tokens'] == len(calls) * 10
    assert not result['spend']['stop_reason']
    with pytest.raises(FileExistsError):
        await pilot.run_batch(output, frozen['sha256'], jev_credential='fixture', peer_credential='fixture')


@pytest.mark.parametrize('failure', ['cancel', 'audit', 'cleanup', 'fixture_io'])
async def test_calibration_operational_stops_keep_all_96_trials(chromium_required, monkeypatch, tmp_path, linkding_root, product_python, failure, legacy_product_fingerprints):
    import json
    from agent_computer_use.channels.dom import ManagedChromiumChannel
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_calibration_route as pilot
    calls, _ = install_product_http(monkeypatch, 'cancel' if failure == 'cancel' else None)
    if failure == 'cleanup':
        original_close = ManagedChromiumChannel.aclose
        async def failed_close(self):
            await original_close(self)
            raise RuntimeError('controlled cleanup failure')
        monkeypatch.setattr(ManagedChromiumChannel, 'aclose', failed_close)
    if failure == 'audit':
        original_open = Path.open
        def failed_open(path, *args, **kwargs):
            if path.name == 'audit.jsonl':
                raise OSError('controlled audit failure')
            return original_open(path, *args, **kwargs)
        monkeypatch.setattr(Path, 'open', failed_open)
    if failure == 'fixture_io':
        async def failed_initialize(*args, **kwargs):
            raise OSError('controlled fixture failure')
        monkeypatch.setattr(pilot.SQLiteAdapter, 'initialize', failed_initialize)
        monkeypatch.setattr(pilot.LinkdingCalibrationAdapter, 'initialize', failed_initialize)
    output = tmp_path / 'calibration'
    frozen = pilot.prepare(output, sql_python=product_python, link_root=linkding_root)
    if failure == 'cancel':
        with pytest.raises(asyncio.CancelledError):
            await pilot.run_batch(output, frozen['sha256'], jev_credential='fixture', peer_credential='fixture')
        result = json.loads((output / 'result.json').read_text())
    else:
        result = await pilot.run_batch(output, frozen['sha256'], jev_credential='fixture', peer_credential='fixture')
    assert not result['completed'] and len(result['rows']) == 96
    assert result['spend']['stop_reason']
    assert all(r['status'] == 'not_run' for r in result['rows'][1:])
    if failure == 'fixture_io':
        assert not calls and result['rows'][0]['database'] is None
    if failure != 'cleanup':
        assert result['rows'][0]['cleanup_confirmed']
        assert not any(h['method'] == 'POST' for h in result['rows'][0]['http'])


async def test_calibration_unknown_usage_keeps_all_96_trials(chromium_required, monkeypatch, tmp_path, linkding_root, product_python, legacy_product_fingerprints):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_calibration_route as pilot
    calls, _ = install_product_http(monkeypatch, 'unknown')
    frozen = pilot.prepare(tmp_path / 'calibration', sql_python=product_python, link_root=linkding_root)
    result = await pilot.run_batch(tmp_path / 'calibration', frozen['sha256'],
                                  jev_credential='fixture', peer_credential='fixture')
    assert len(result['rows']) == 96 and not result['completed']
    assert result['spend']['stop_reason'] == 'unknown_usage'
    assert sum(r['status'] == 'not_run' for r in result['rows']) == 95
    assert len(calls) == 1


@pytest.mark.parametrize('failure', ['oracle', 'wrong_record', 'invalid'])
async def test_calibration_private_labels_and_bad_choices_cannot_prove_success(chromium_required, monkeypatch, tmp_path, linkding_root, product_python, failure, legacy_product_fingerprints):
    import copy
    import json
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_calibration_route as pilot
    _, packets = install_product_http(monkeypatch, None if failure == 'oracle' else failure)
    frozen = pilot.prepare(tmp_path / 'calibration', sql_python=product_python, link_root=linkding_root)
    case = copy.deepcopy(next(c for c in frozen['cases'] if c['product'] == 'sqlite-web' and c['group'] == 'normal'
                             and c['target'] == 4 and c['condition'] == 'cold'))
    if failure == 'oracle':
        case['oracle']['rows'][0]['title'] = 'private-oracle-poison'
    row = await pilot.run_task(case, 'jt', tmp_path / 'calibration', frozen=frozen,
                              jev_credential='fixture', peer_credential='fixture')
    assert not row['strict_completed'] and row['cleanup_confirmed']
    assert all('private-oracle-poison' not in json.dumps(packet) and 'oracle' not in packet['state'] for packet in packets)
    if failure == 'oracle':
        assert row['result']['status'] == 'completed'
        assert next(r['title'] for r in row['database']['records'] if r['id'] == 4) == case['goal']['inputs'][0]['value']
    if failure == 'invalid':
        assert not any(h['method'] == 'POST' for h in row['http'])
        assert row['usage']['unknown_calls'] == 0


@pytest.mark.parametrize('product', ['sqlite-web', 'linkding'])
async def test_calibration_correct_db_requires_current_returned_list(chromium_required, monkeypatch, tmp_path, linkding_root, product_python, product, legacy_product_fingerprints):
    from playwright.async_api import Page
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_calibration_route as pilot
    install_product_http(monkeypatch)
    original = Page.evaluate
    projection = pilot.link._PAGE_READ if product == 'linkding' else pilot.shared._LIST_READ
    mutation = """() => {
        for (const link of document.querySelectorAll('li[data-bookmark-id] .title a')) {
            if (link.innerText.startsWith('Approved ')) link.textContent='Stale display';
        }
        const table=document.querySelector('table.cell-content');
        if (table) {
            const index=[...table.querySelectorAll('thead th')].findIndex(n=>n.dataset.col==='title');
            for (const row of table.querySelectorAll('tbody tr')) {
                if (row.cells[index]?.innerText.startsWith('Approved ')) row.cells[index].textContent='Stale display';
            }
        }
    }"""
    async def stale_visible_list(page, expression, arg=None):
        if expression == projection:
            await original(page, mutation)
        return await original(page, expression, arg)
    monkeypatch.setattr(Page, 'evaluate', stale_visible_list)
    frozen = pilot.prepare(tmp_path / 'calibration', sql_python=product_python, link_root=linkding_root)
    case = next(c for c in frozen['cases'] if c['product'] == product and c['group'] == 'normal'
                and c['target'] == 4 and c['condition'] == 'cold')
    row = await pilot.run_task(case, 'jt', tmp_path / 'calibration', frozen=frozen,
                              jev_credential='fixture', peer_credential='fixture')
    assert row['database']['records'] == case['oracle']['rows']
    assert row['result']['status'] != 'completed'
    assert not row['strict_completed'] and row['cleanup_confirmed']
    assert sum(h['method'] == 'POST' for h in row['http']) == 1


@pytest.mark.parametrize('product', ['sqlite-web', 'linkding', 'legacy-sqlite-web'])
@pytest.mark.parametrize('change', ['reload', 'dom'])
async def test_calibration_projection_cannot_mix_navigation_epochs(chromium_required, monkeypatch, tmp_path, linkding_root, product_python, product, change, legacy_product_fingerprints):
    from playwright.async_api import Page
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_calibration_route as pilot
    calls, _ = install_product_http(monkeypatch)
    original = Page.evaluate
    changed = False
    projection = pilot.link._PAGE_READ if product == 'linkding' else pilot.shared._LIST_READ
    async def reload_after_projection(page, expression, arg=None):
        nonlocal changed
        data = await original(page, expression, arg)
        if expression == projection and not changed:
            changed = True
            if change == 'reload':
                # Navigation must not inherit the channel's 500 ms locator timeout.
                await page.reload(timeout=5000)
            else:
                await original(page, "document.body.dataset.projectionRace = 'changed'")
        return data
    monkeypatch.setattr(Page, 'evaluate', reload_after_projection)
    if product == 'legacy-sqlite-web':
        frozen = pilot.shared.prepare(tmp_path / 'calibration', app_python=product_python, workflow=True)
        row = await pilot.shared.run_task(frozen['cases'][0], 'jt', tmp_path / 'calibration',
            app_python=product_python, jev_credential='fixture', peer_credential='fixture')
    else:
        frozen = pilot.prepare(tmp_path / 'calibration', sql_python=product_python, link_root=linkding_root)
        case = next(c for c in frozen['cases'] if c['product'] == product and c['group'] == 'normal'
                    and c['target'] == 4 and c['condition'] == 'cold')
        row = await pilot.run_task(case, 'jt', tmp_path / 'calibration', frozen=frozen,
                                  jev_credential='fixture', peer_credential='fixture')
    assert changed and row['strict_completed'] and row['cleanup_confirmed'], row
    assert len(calls) == (3 if product == 'linkding' else 4)


async def test_calibration_missing_record_is_exit_not_completion(chromium_required, monkeypatch, tmp_path, linkding_root, product_python, legacy_product_fingerprints):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_calibration_route as pilot
    install_product_http(monkeypatch)
    frozen = pilot.prepare(tmp_path / 'calibration', sql_python=product_python, link_root=linkding_root)
    case = next(c for c in frozen['cases'] if c['product'] == 'sqlite-web' and c['negative'] == 'missing'
                and c['condition'] == 'cold')
    row = await pilot.run_task(case, 'jt', tmp_path / 'calibration', frozen=frozen,
                              jev_credential='fixture', peer_credential='fixture')
    assert row['negative_passed'] and not row['strict_completed'] and row['cleanup_confirmed'], row
    assert row['database'] == row['database_before']
    assert not any(h['method'] == 'POST' for h in row['http'])
    assert row['result']['reason'] == 'none'


@pytest.mark.parametrize('product', ['sqlite-web', 'linkding'])
async def test_calibration_editor_revocation_blocks_native_dispatch(chromium_required, monkeypatch, tmp_path, linkding_root, product_python, product, legacy_product_fingerprints):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_calibration_route as pilot
    install_product_http(monkeypatch)
    frozen = pilot.prepare(tmp_path / 'calibration', sql_python=product_python, link_root=linkding_root)
    case = next(c for c in frozen['cases'] if c['product'] == product and c['negative'] == 'revoked'
                and c['condition'] == 'cold')
    row = await pilot.run_task(case, 'jt', tmp_path / 'calibration', frozen=frozen,
                              jev_credential='fixture', peer_credential='fixture')
    assert row['negative_passed'] and not row['strict_completed'] and row['cleanup_confirmed'], row
    assert row['revocation']['before_native_dispatch'] is True
    assert row['database'] == row['database_before']
    assert not any(h['method'] == 'POST' for h in row['http'])
    assert row['result']['reason'] == 'error'


@pytest.mark.parametrize('product', ['sqlite-web', 'linkding'])
@pytest.mark.parametrize('negative', ['missing', 'revoked'])
async def test_calibration_negative_requires_full_task_envelope(chromium_required, monkeypatch, tmp_path, linkding_root, product_python, product, negative, legacy_product_fingerprints):
    import copy
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_calibration_route as pilot
    install_product_http(monkeypatch)
    frozen = pilot.prepare(tmp_path / 'calibration', sql_python=product_python, link_root=linkding_root)
    case = next(c for c in frozen['cases'] if c['product'] == product and c['negative'] == negative
                and c['condition'] == 'cold')
    row = await pilot.run_task(case, 'jt', tmp_path / 'calibration', frozen=frozen,
                              jev_credential='fixture', peer_credential='fixture')
    assert row['negative_passed']
    for field, value in [('elapsed_ms', 120001), ('app_unchanged', False), ('trial_source_unchanged', False)]:
        changed = copy.deepcopy(row)
        changed[field] = value
        async def altered_receipt(*args, **kwargs):
            return changed
        monkeypatch.setattr(pilot.shared, 'run_task', altered_receipt)
        output = tmp_path / field
        (output / row['id']).mkdir(parents=True)
        checked = await pilot.run_task(case, 'jt', output, frozen=frozen,
                                      jev_credential='fixture', peer_credential='fixture')
        assert not checked['negative_passed'], field
        assert not checked['calibration_success'], field


@pytest.mark.parametrize('product', ['sqlite-web', 'linkding'])
async def test_calibration_prewarm_is_owned_and_in_task_clock(chromium_required, monkeypatch, tmp_path, linkding_root, product_python, product, legacy_product_fingerprints):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_calibration_route as pilot
    install_product_http(monkeypatch)
    frozen = pilot.prepare(tmp_path / 'calibration', sql_python=product_python, link_root=linkding_root)
    case = next(c for c in frozen['cases'] if c['product'] == product and c['group'] == 'normal'
                and c['target'] == 4 and c['condition'] == 'prewarmed')
    row = await pilot.run_task(case, 'jt', tmp_path / 'calibration', frozen=frozen,
                              jev_credential='fixture', peer_credential='fixture')
    assert row['strict_completed'] and row['cleanup_confirmed'], row
    assert row['prewarm']['path'] == ('/login/' if product == 'linkding' else '/')
    assert row['prewarm']['status'] == 200
    assert 0 <= row['prewarm']['elapsed_ms'] < row['elapsed_ms']
    assert row['http'][0]['path'] == row['prewarm']['path']


@pytest.mark.parametrize('fault_stage', [None, 'list', 'editor'])
async def test_calibration_controller_four_record_linkding_get_recovery(chromium_required, monkeypatch, tmp_path, linkding_root, product_python, fault_stage, legacy_product_fingerprints):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_calibration_route as pilot
    calls, _ = install_product_http(monkeypatch)
    frozen = pilot.prepare(tmp_path / 'calibration', sql_python=product_python, link_root=linkding_root)
    case = next(c for c in frozen['cases'] if c['product'] == 'linkding' and c['fault_stage'] == fault_stage
                and c['target'] == 4 and c['condition'] == 'cold')
    row = await pilot.run_task(case, 'jt', tmp_path / 'calibration', frozen=frozen,
                              jev_credential='fixture', peer_credential='fixture')
    assert row['strict_completed'] and row['cleanup_confirmed'], row
    assert row['recovery_completed'] == (fault_stage is not None)
    assert len(calls) == (3 if fault_stage is None else 4)


async def test_linkding_product_shuffled_seed_uses_record_identity(chromium_required, monkeypatch, tmp_path, linkding_root):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_linkding_route as pilot
    install_product_http(monkeypatch)
    frozen = pilot.prepare(tmp_path / 'shuffled-linkding', app_root=linkding_root)
    case = frozen['cases'][0]
    case['seed'] = list(reversed(case['seed']))
    row = await pilot.run_task(case, 'jt', tmp_path / 'shuffled-linkding',
                              app_python=Path(frozen['app']['python']),
                              jev_credential='fixture', peer_credential='fixture')
    assert row['strict_completed'] and row['cleanup_confirmed'], row


@pytest.mark.parametrize('arm', ['v', 'jt'])
@pytest.mark.parametrize('target', [1, 2])
async def test_linkding_product_actual_controller_persists_and_returns(chromium_required, monkeypatch, tmp_path, linkding_root, arm, target):
    import json
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_linkding_route as pilot
    calls, packets = install_product_http(monkeypatch)
    frozen = pilot.prepare(tmp_path / 'actual-linkding', app_root=linkding_root)
    case = frozen['cases'][target - 1]
    row = await pilot.run_task(case, arm, tmp_path / 'actual-linkding',
                               app_python=Path(frozen['app']['python']),
                               jev_credential='fixture', peer_credential='fixture')
    assert row['strict_completed'] and row['cleanup_confirmed'], row
    assert row['database']['records'] == case['oracle']['rows']
    assert row['list_readback']['path'] == '/bookmarks'
    assert len(row['database']['tables']) == 10
    assert sum(h['method'] == 'POST' for h in row['http']) == 1
    assert calls == (['peer', 'peer', 'peer'] if arm == 'v' else ['peer', 'jev', 'jev'])
    assert all('oracle' not in json.dumps(packet) for packet in packets)
    observations = {o['observation_id']: o for o in row['product_observations']}
    for packet in packets:
        snapshot = packet['state']['snapshot']
        actual = observations[snapshot['observation_id']]
        facts = {f['key']: f['value'] for f in snapshot['facts']}
        assert json.loads(facts['status:Records']) == actual['records']
        assert all(facts[f'status:Editor seen:{url}'] == 'true' for url in actual['seen_editor_urls'])
    assert row['trial_source_unchanged'] and row['app_unchanged']
    path = tmp_path / 'actual-linkding' / row['id']
    assert pilot.database_state(path / 'before.db') == row['database_before']
    assert pilot.database_state(path / 'after.db') == row['database']
    assert 'version.txt' not in (path / 'app.log').read_text()


def test_real_product_schedule_balances_normal_family_order(monkeypatch, product_python):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_real_product_route as pilot
    frozen = pilot.freeze_inputs(product_python)
    first_arms = {row['case']: row['arm'] for row in reversed(frozen['schedule'])}
    assert list(first_arms.values()).count('v') == list(first_arms.values()).count('jt') == 3
    for kind in ('insert', 'update'):
        normal = [first_arms[c['id']] for c in frozen['cases'] if c['kind'] == kind and not c['recovery']]
        assert sorted(normal) == ['jt', 'v']


@pytest.mark.parametrize('failure', [None, 'unknown'])
async def test_linkding_product_batch_keeps_frozen_denominator(chromium_required, monkeypatch, tmp_path, linkding_root, failure):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_linkding_route as pilot
    calls, _ = install_product_http(monkeypatch, failure)
    frozen = pilot.prepare(tmp_path / 'batch-linkding', app_root=linkding_root)
    result = await pilot.run_batch(tmp_path / 'batch-linkding', frozen['sha256'],
                                   jev_credential='fixture', peer_credential='fixture')
    assert len(result['rows']) == 4
    ran = [r for r in result['rows'] if r['status'] != 'not_run']
    assert all(r['cleanup_confirmed'] for r in ran)
    if failure:
        assert not result['completed'] and len(ran) == 1
        assert len(calls) == 1 and ran[0]['usage']['unknown_calls'] == 1
        assert not any(h['method'] == 'POST' for h in ran[0]['http'])
        assert not ran[0]['strict_completed']
    else:
        assert result['completed'] and all(r['strict_completed'] for r in ran)
        assert len(calls) == 12 and calls.count('jev') == 4


def test_linkding_product_cli_prepares_without_credentials(monkeypatch, tmp_path, linkding_root, capsys):
    import sys
    import json
    import dotenv
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_linkding_route as pilot
    def forbidden(*args, **kwargs):
        raise AssertionError('preparation read credentials')
    monkeypatch.setattr(dotenv, 'dotenv_values', forbidden)
    monkeypatch.setattr(sys, 'argv', ['linkding-route', '--output', str(tmp_path/'cli'), '--app-root', str(linkding_root)])
    pilot.main()
    result = json.loads(capsys.readouterr().out)
    assert result['tasks'] == 4 and result['record_only']
    monkeypatch.setattr(sys, 'argv', ['linkding-route', '--output', str(tmp_path/'cli'), '--run', '--approved-sha256', 'wrong'])
    with pytest.raises(ValueError, match='freeze changed'):
        pilot.main()


async def test_linkding_product_private_oracle_cannot_select_actions(chromium_required, monkeypatch, tmp_path, linkding_root):
    import json
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_linkding_route as pilot
    _, packets = install_product_http(monkeypatch)
    frozen = pilot.prepare(tmp_path/'oracle-linkding', app_root=linkding_root)
    case = frozen['cases'][0]
    case['oracle']['rows'][0]['title'] = 'PRIVATE-ORACLE-POISON'
    row = await pilot.run_task(case, 'jt', tmp_path/'oracle-linkding', app_python=Path(frozen['app']['python']),
                               jev_credential='fixture', peer_credential='fixture')
    assert row['result']['status'] == 'completed' and not row['strict_completed']
    assert row['database']['records'][0]['title'] == 'Launch bookmark 1'
    assert all('PRIVATE-ORACLE-POISON' not in json.dumps(p) for p in packets)
    assert row['cleanup_confirmed']


async def test_linkding_product_wrong_record_is_not_completion(chromium_required, monkeypatch, tmp_path, linkding_root):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_linkding_route as pilot
    install_product_http(monkeypatch, 'wrong_record')
    frozen = pilot.prepare(tmp_path/'wrong-linkding', app_root=linkding_root)
    row = await pilot.run_task(frozen['cases'][0], 'jt', tmp_path/'wrong-linkding', app_python=Path(frozen['app']['python']),
                               jev_credential='fixture', peer_credential='fixture')
    assert not row['strict_completed'] and row['cleanup_confirmed']
    assert row['database']['records'][0]['title'] == 'Draft bookmark 1'
    assert row['database']['records'][1]['title'] == 'Launch bookmark 1'
    assert sum(h['method'] == 'POST' for h in row['http']) == 1


@pytest.mark.parametrize('fault', ['missing', 'wrong', 'wrong_page'])
async def test_linkding_product_independent_final_list_receipt(chromium_required, monkeypatch, tmp_path, linkding_root, fault):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_linkding_route as pilot
    install_product_http(monkeypatch)
    original = pilot.LinkdingAdapter.readback
    async def changed(self, channel, row):
        if fault == 'wrong_page':
            await channel.page.goto(channel.config.url + '/archived', timeout=5000)
        elif fault == 'missing':
            await channel.page.locator('.bookmark-list').evaluate('node => node.remove()')
        else:
            await channel.page.locator('li[data-bookmark-id="1"] .title a').evaluate("node => node.textContent='Wrong title'")
        await original(self, channel, row)
    monkeypatch.setattr(pilot.LinkdingAdapter, 'readback', changed)
    frozen = pilot.prepare(tmp_path/fault, app_root=linkding_root)
    row = await pilot.run_task(frozen['cases'][0], 'jt', tmp_path/fault, app_python=Path(frozen['app']['python']),
                               jev_credential='fixture', peer_credential='fixture')
    assert row['result']['status'] == 'completed'
    assert row['database']['records'] == frozen['cases'][0]['oracle']['rows']
    assert not row['strict_completed'] and row['cleanup_confirmed']
    assert sum(h['method'] == 'POST' for h in row['http']) == 1


@pytest.mark.parametrize('failure', ['cancel', 'audit', 'cleanup', 'fixture_io'])
async def test_linkding_product_operational_stops_keep_four_rows(chromium_required, monkeypatch, tmp_path, linkding_root, failure):
    import json
    from agent_computer_use.channels.dom import ManagedChromiumChannel
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_linkding_route as pilot
    calls, _ = install_product_http(monkeypatch, 'cancel' if failure == 'cancel' else None)
    if failure == 'cleanup':
        close = ManagedChromiumChannel.aclose
        async def reported_failure(self):
            await close(self)
            raise RuntimeError('reported cleanup failure')
        monkeypatch.setattr(ManagedChromiumChannel, 'aclose', reported_failure)
    if failure in ('audit', 'fixture_io'):
        original_open = Path.open
        def denied(path, *args, **kwargs):
            if path.name == ('audit.jsonl' if failure == 'audit' else 'seed.log'):
                raise OSError('controlled evidence IO failure')
            return original_open(path, *args, **kwargs)
        monkeypatch.setattr(Path, 'open', denied)
    output = tmp_path/failure
    frozen = pilot.prepare(output, app_root=linkding_root)
    if failure == 'cancel':
        with pytest.raises(asyncio.CancelledError):
            await pilot.run_batch(output, frozen['sha256'], jev_credential='fixture', peer_credential='fixture')
        result = json.loads((output/'result.json').read_text())
    else:
        result = await pilot.run_batch(output, frozen['sha256'], jev_credential='fixture', peer_credential='fixture')
    assert not result['completed'] and len(result['rows']) == 4
    assert [r['status'] for r in result['rows'][1:]] == ['not_run'] * 3
    assert not result['rows'][0]['strict_completed'] and result['spend']['stop_reason']
    if failure == 'fixture_io':
        assert not calls and result['rows'][0]['database'] is None
    if failure != 'cleanup':
        assert result['rows'][0]['cleanup_confirmed']
    if failure in ('cancel', 'audit', 'fixture_io'):
        assert not any(h['method'] == 'POST' for h in result['rows'][0]['http'])


async def test_linkding_product_invalid_known_reply_never_dispatches(chromium_required, monkeypatch, tmp_path, linkding_root):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_linkding_route as pilot
    calls, _ = install_product_http(monkeypatch, 'invalid')
    frozen = pilot.prepare(tmp_path/'invalid-linkding', app_root=linkding_root)
    result = await pilot.run_batch(tmp_path/'invalid-linkding', frozen['sha256'],
                                   jev_credential='fixture', peer_credential='fixture')
    assert len(result['rows']) == 4 and len(calls) == 4
    assert all(r['status'] == 'finished' and not r['strict_completed'] and r['cleanup_confirmed'] for r in result['rows'])
    assert all(r['usage']['unknown_calls'] == 0 and not any(h['method'] == 'POST' for h in r['http']) for r in result['rows'])


def test_linkding_product_rejects_changed_application_before_clients(monkeypatch, tmp_path, linkding_root):
    import shutil
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_linkding_route as pilot
    app = tmp_path/'qualified-copy'
    app.mkdir()
    for name in pilot.source_files(linkding_root):
        target = app/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(linkding_root/name, target)
    (app/'.venv').symlink_to(linkding_root/'.venv', target_is_directory=True)
    frozen = pilot.prepare(tmp_path/'pinned-copy', app_root=app)
    form = app/'bookmarks/templates/bookmarks/form.html'
    form.write_text(form.read_text() + '<button>Altered</button>')
    with pytest.raises(ValueError, match='unmodified qualified product'):
        pilot.load_freeze(tmp_path/'pinned-copy', frozen['sha256'])
    assert not (tmp_path/'pinned-copy/started.json').exists()


async def test_linkding_product_repeated_cancel_during_copy_drains_fixture(chromium_required, monkeypatch, tmp_path, linkding_root):
    import json
    import shutil
    import threading
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_linkding_route as pilot
    calls, _ = install_product_http(monkeypatch)
    frozen = pilot.prepare(tmp_path/'copy-cancel', app_root=linkding_root)
    reached, release = threading.Event(), threading.Event()
    original = shutil.copyfile
    def pending_copy(*args, **kwargs):
        reached.set()
        assert release.wait(5)
        return original(*args, **kwargs)
    monkeypatch.setattr(shutil, 'copyfile', pending_copy)
    case = frozen['cases'][0]
    worker = asyncio.create_task(pilot.run_task(case, 'v', tmp_path/'copy-cancel',
        app_python=Path(frozen['app']['python']), jev_credential='fixture', peer_credential='fixture'))
    try:
        async with asyncio.timeout(5):
            while not reached.is_set():
                await asyncio.sleep(.01)
        worker.cancel()
        await asyncio.sleep(.01)
        worker.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await worker
    finally:
        release.set()
        await asyncio.gather(worker, return_exceptions=True)
    path = tmp_path/'copy-cancel'/(case['id']+'-v')
    row = json.loads((path/'row.json').read_text())
    assert row['status'] == 'cancelled' and row['cleanup_confirmed'] and not row['strict_completed']
    assert not calls and pilot.source_files(path/'app') == frozen['app']['source_files']


@pytest.mark.parametrize('failure', [None, 'cancel'])
async def test_real_product_cancellation_during_cleanup_closes_owned_resources(chromium_required, monkeypatch, tmp_path, product_python, failure):
    import json
    from tank_backend.agents.task_runtime import TaskRuntime
    from agent_computer_use.channels.dom import ManagedChromiumChannel
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_real_product_route as pilot
    install_product_http(monkeypatch, failure)
    closing, release = asyncio.Event(), asyncio.Event()
    runtimes, browsers, processes = [], [], []
    original_close, original_init = TaskRuntime.aclose, ManagedChromiumChannel.__init__
    original_spawn = asyncio.create_subprocess_exec
    async def delayed_close(self):
        runtimes.append(self)
        closing.set()
        await release.wait()
        await original_close(self)
    def remember_browser(self, config):
        original_init(self, config)
        browsers.append(self)
    async def remember_process(*args, **kwargs):
        process = await original_spawn(*args, **kwargs)
        if args[0] == str(product_python):
            processes.append(process)
        return process
    monkeypatch.setattr(TaskRuntime, 'aclose', delayed_close)
    monkeypatch.setattr(ManagedChromiumChannel, '__init__', remember_browser)
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', remember_process)
    frozen = pilot.prepare(tmp_path / 'cleanup-cancel', app_python=product_python)
    worker = asyncio.create_task(pilot.run_task(frozen['cases'][0], 'jt', tmp_path / 'cleanup-cancel',
        app_python=product_python, jev_credential='fixture', peer_credential='fixture'))
    try:
        await asyncio.wait_for(closing.wait(), 10)
        worker.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await worker
        assert processes and all(p.returncode is not None for p in processes)
        assert browsers and all(b.closed and (b.browser is None or not b.browser.is_connected()) for b in browsers)
        row = json.loads((tmp_path / 'cleanup-cancel' / (frozen['cases'][0]['id'] + '-jt') / 'row.json').read_text())
        assert row['status'] == 'cancelled' and row['cleanup_confirmed']
        assert not row['strict_completed'] and row['capped_completion_ms'] == 120000
    finally:
        release.set()
        if not worker.done():
            worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        for runtime in runtimes:
            await original_close(runtime)
        for browser in browsers:
            await browser.aclose()
        for process in processes:
            if process.returncode is None:
                process.terminate()
            await process.wait()


@pytest.mark.parametrize('kind', ['insert', 'update'])
@pytest.mark.parametrize('arm', ['v', 'jt'])
async def test_real_product_actual_sdk_browser_database_recovery(chromium_required, monkeypatch, tmp_path, product_python, kind, arm):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_real_product_route as pilot
    calls, packets = install_product_http(monkeypatch)
    frozen = pilot.prepare(tmp_path / 'real', app_python=product_python)
    case = next(c for c in frozen['cases'] if c['kind'] == kind and c['recovery'])
    row = await pilot.run_task(case, arm, tmp_path / 'real', app_python=product_python, jev_credential='fixture', peer_credential='fixture')
    assert row['strict_completed'] and row['recovery_completed'] and row['cleanup_confirmed'], row
    assert row['database']['records'] == case['oracle']['rows']
    assert len(row['database']['writes']) == 1
    assert row['database']['writes'][0]['operation'] == kind
    assert sum(r['status'] == '503 Service Unavailable' for r in row['http']) == 1
    assert sum(r['method'] == 'POST' for r in row['http']) == 1
    assert calls and all(p['state']['binding']['scope'] == 'real-product' for p in packets)
    assert row['app_unchanged']


async def test_dom_loading_document_is_not_a_complete_observation(chromium_required):
    from agent_computer_use.channels.dom import BrowserConfig, ManagedChromiumChannel
    release = asyncio.Event()
    async def respond(reader, writer):
        request = await reader.readuntil(b'\r\n\r\n')
        streamed = request.startswith(b'GET /stream ')
        body = b'<!doctype html><button>Pending</button>'
        tail = b'<button>Ready</button>' if streamed else b''
        writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: ' + str(len(body)+len(tail)).encode() + b'\r\nConnection: close\r\n\r\n' + body)
        await writer.drain()
        if streamed:
            await release.wait()
            writer.write(tail)
            await writer.drain()
        writer.close()
        await writer.wait_closed()
    server = await asyncio.start_server(respond, '127.0.0.1', 0)
    url = f'http://127.0.0.1:{server.sockets[0].getsockname()[1]}/'
    browser = ManagedChromiumChannel(BrowserConfig(scope='managed-page', url=url))
    ctx = context()
    try:
        await browser.observe('managed-page', ctx)
        assert browser.page is not None
        await browser.page.goto(url+'stream', wait_until='commit')
        await browser.page.get_by_role('button', name='Pending').wait_for()
        loading = await browser.observe('managed-page', ctx)
        assert not loading.complete
        assert not ActionBuilder(visual=True).build('goal', 1, goal(), loading).actions
        release.set()
        await browser.page.wait_for_load_state('load')
        loaded = await browser.observe('managed-page', ctx)
        assert loaded.complete and any(e.label == 'Ready' for e in loaded.elements)
    finally:
        release.set()
        await browser.aclose()
        await ctx.runtime.aclose()
        server.close()
        await server.wait_closed()


async def test_dom_visual_capture_waits_for_finite_css_transition(channel):
    browser, ctx = channel
    await browser.page.set_content('''<style>
      input{border:8px solid black;transition:border-color .15s linear}
      input:focus{border-color:red;outline:none}
      </style><label>Name<input value="Bob"></label>''')
    await browser.page.screenshot()
    await browser.page.get_by_role('textbox').focus()
    assert await browser.page.evaluate('document.getAnimations().length')
    offered = await actions(browser, ctx, index=2)
    await browser.capture(browser.previous, ctx)
    await asyncio.sleep(.2)
    assert await browser.is_current(offered.binding, offered.actions[0], ctx)


async def _observe_before_continuing_motion(browser, ctx):
    unavailable = await browser.observe('managed-page', ctx)
    assert not unavailable.ready and not unavailable.complete
    await browser.page.evaluate('''async () => {
        const animations = document.getAnimations();
        animations.forEach(animation => animation.pause());
        await Promise.all(animations.map(animation => animation.ready));
    }''')
    snapshot = await browser.observe('managed-page', ctx)
    assert snapshot.ready and snapshot.complete
    # Starting existing animations through their API changes no DOM revision.
    await browser.page.evaluate('document.getAnimations().forEach(animation => animation.play())')
    return snapshot


async def test_dom_visual_capture_refuses_continuing_animation(channel):
    from tank_backend.agents.subagent import SubAgentStopped
    browser, ctx = channel
    await browser.page.set_content('''<style>@keyframes pulse{to{opacity:.1}}
      button{animation:pulse .1s infinite alternate}</style><button>Save</button>''')
    snapshot = await _observe_before_continuing_motion(browser, ctx)
    with pytest.raises(SubAgentStopped, match='unstable_visual_frame'):
        await browser.capture(snapshot, ctx)
    assert browser.visual_frame is None


@pytest.mark.parametrize('pseudo', ['::before', '::after'])
@pytest.mark.parametrize('property_value', ['transform:rotate(360deg)', 'opacity:.1'])
async def test_dom_hidden_pseudo_animation_keeps_running_during_capture(channel, pseudo, property_value):
    browser, ctx = channel
    await browser.page.set_content(f'''<style>
      @keyframes spin{{to{{{property_value}}}}}
      i{{visibility:hidden}}
      i{pseudo}{{content:"";display:block;width:16px;height:16px;
        background:red;animation:spin .1s infinite linear}}
      </style><i></i><label>Name<input value="Bob"></label>''')
    offered = await actions(browser, ctx, index=2)
    captured = await browser.capture(browser.previous, ctx)
    await asyncio.sleep(.15)
    assert await browser.is_current(offered.binding, offered.actions[0], ctx)
    assert await browser.visual_png() == captured.png
    assert await browser.page.evaluate('''pseudo => document.getAnimations().some(a =>
      a.playState === 'running' && a.effect.pseudoElement === pseudo)''', pseudo)


@pytest.mark.parametrize('css', [
    'i::after{visibility:visible}',
    'i{visibility:visible}i::after{opacity:0}',
    '@keyframes spin{from{visibility:hidden}to{visibility:visible}}',
    '@keyframes spin{to{width:100px}}',
    '@keyframes spin{to{--unknown:1}}',
    '@keyframes spin{to{transform:rotate(360deg);--unknown:1}}',
    'i::after{content:"Text"}',
    'i::after{display:list-item;list-style:disc}',
    'i{animation:spin .1s infinite}i::after{animation:none}',
    'i{animation:spin .1s infinite}i::after{animation:none;visibility:visible}',
    'i{animation:spin .1s infinite}i::after{animation:none}i span{visibility:visible}',
    'i::before{content:"";visibility:visible;display:block;width:16px;height:16px;animation:spin .1s infinite}',
])
async def test_dom_hidden_pseudo_animation_admission_stays_conservative(channel, css):
    from tank_backend.agents.subagent import SubAgentStopped
    browser, ctx = channel
    await browser.page.set_content('''<style>
      @keyframes spin{to{transform:rotate(360deg)}}
      i{visibility:hidden;display:block;width:16px;height:16px}
      i::after{content:"";display:block;width:16px;height:16px;
        background:red;animation:spin .1s infinite linear}
      ''' + css + '</style><i><span>Child</span></i><button>Save</button>')
    snapshot = await _observe_before_continuing_motion(browser, ctx)
    with pytest.raises(SubAgentStopped, match='unstable_visual_frame'):
        await browser.capture(snapshot, ctx)
    assert browser.visual_frame is None


@pytest.mark.parametrize('change', ['pseudo_visible', 'pixels', 'reference'])
async def test_dom_hidden_pseudo_animation_does_not_bypass_freshness(channel, change):
    from tank_backend.agents.subagent import SubAgentStopped
    browser, ctx = channel
    events = []
    class Observer:
        def on_event(self, kind, metadata):
            if kind == 'computer_use_freshness':
                events.append(metadata)
    object.__setattr__(ctx, 'observer', Observer())
    await browser.page.set_content('''<style>
      @keyframes spin{to{transform:rotate(360deg)}}
      i{visibility:hidden}
      i::after{content:"";display:block;width:16px;height:16px;
        background:red;animation:spin .1s infinite linear}
      </style><i></i><label>Name<input value="Bob"></label>''')
    offered = await actions(browser, ctx, index=2)
    await browser.capture(browser.previous, ctx)
    if change == 'pseudo_visible':
        # CSSOM changes can reveal the pseudo-element without a DOM mutation.
        await browser.page.evaluate('''document.styleSheets[0].insertRule(
            'i::after {visibility:visible}', document.styleSheets[0].cssRules.length)''')
    elif change == 'pixels':
        await browser.page.evaluate('''document.styleSheets[0].insertRule(
            'body {background:green}', document.styleSheets[0].cssRules.length)''')
    else:
        await browser.page.get_by_role('textbox').evaluate('(node) => node.replaceWith(node.cloneNode(true))')
    assert not await browser.is_current(offered.binding, offered.actions[0], ctx)
    if change != 'reference':
        assert any(e['stage'] == 'frame_scene' for e in events)
    if change == 'pseudo_visible':
        snapshot = await _observe_before_continuing_motion(browser, ctx)
        with pytest.raises(SubAgentStopped, match='unstable_visual_frame'):
            await browser.capture(snapshot, ctx)


@pytest.mark.parametrize('source', ['adopted', 'imported'])
async def test_dom_hidden_pseudo_animation_reads_actual_css_definitions(channel, source):
    browser, ctx = channel
    css = '''@layer spinner {
      @keyframes spin{to{transform:rotate(360deg)}}
      i{visibility:hidden}
      i::after{content:"";display:block;width:16px;height:16px;
        background:red;animation:spin .1s infinite linear}}
    '''
    await browser.page.set_content('<i></i><label>Name<input value="Bob"></label>')
    if source == 'adopted':
        await browser.page.evaluate('''css => {
          const sheet = new CSSStyleSheet(); sheet.replaceSync(css);
          document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];
        }''', css)
    else:
        await browser.page.route('**/spinner.css', lambda route: route.fulfill(body=css, content_type='text/css'))
        await browser.page.add_style_tag(content='@import url("/spinner.css");')
    offered = await actions(browser, ctx, index=2)
    await browser.capture(browser.previous, ctx)
    assert await browser.is_current(offered.binding, offered.actions[0], ctx)


@pytest.mark.parametrize('source', ['failed_import', 'rule_limit', 'programmatic'])
async def test_dom_hidden_pseudo_animation_unknown_sources_remain_active(channel, source):
    from tank_backend.agents.subagent import SubAgentStopped
    browser, ctx = channel
    css = '''@keyframes spin{to{transform:rotate(360deg)}}
      i{visibility:hidden}
      i::after{content:"";display:block;width:16px;height:16px;
        background:red;animation:spin .1s infinite linear}'''
    if source == 'failed_import':
        await browser.page.route('**/unavailable.css', lambda route: route.abort())
        css = '@import url("/unavailable.css");' + css
    if source == 'rule_limit':
        css += 'b{color:red}' * 4096
    await browser.page.set_content('<style>' + css + '</style><i></i><button>Save</button>')
    if source == 'programmatic':
        await browser.page.evaluate('''() => {
          document.getAnimations().forEach(a => a.cancel());
          const effect = new KeyframeEffect(document.querySelector('i'),
            [{transform:'rotate(0deg)'}, {transform:'rotate(360deg)'}],
            {duration:100, iterations:Infinity, pseudoElement:'::after'});
          new Animation(effect, document.timeline).play();
        }''')
    snapshot = await _observe_before_continuing_motion(browser, ctx)
    with pytest.raises(SubAgentStopped, match='unstable_visual_frame'):
        await browser.capture(snapshot, ctx)
    assert browser.visual_frame is None


@pytest.mark.parametrize('failure', [None, 'unknown', 'wrong', 'cleanup'])
async def test_real_product_batch_retains_all_rows_and_no_unsafe_retries(chromium_required, monkeypatch, tmp_path, product_python, failure):
    import json
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_real_product_route as pilot
    from agent_computer_use.channels.dom import ManagedChromiumChannel
    calls, packets = install_product_http(monkeypatch, failure)
    if failure == 'cleanup':
        original = ManagedChromiumChannel.aclose
        async def fail_close(self):
            await original(self)
            raise RuntimeError('reported cleanup failure')
        monkeypatch.setattr(ManagedChromiumChannel, 'aclose', fail_close)
    frozen = pilot.prepare(tmp_path / 'batch', app_python=product_python)
    result = await pilot.run_batch(tmp_path / 'batch', frozen['sha256'], jev_credential='fixture', peer_credential='fixture')
    assert len(result['rows']) == 12
    assert all('oracle' not in json.dumps(p) for p in packets)
    ran = [r for r in result['rows'] if r['status'] != 'not_run']
    if failure in ('unknown', 'cleanup'):
        assert not result['completed'] and len(ran) == 1
        assert result['spend']['stop_reason'] == ('unknown_usage' if failure == 'unknown' else 'cleanup_failed')
        if failure == 'unknown':
            assert len(calls) == 1 and not ran[0]['database']['writes']
            assert not any(r['method'] == 'POST' for r in ran[0]['http'])
    else:
        assert result['completed'] and len(ran) == 12
        assert all(r['cleanup_confirmed'] and r['app_unchanged'] for r in ran)
        if failure is None:
            assert all(r['strict_completed'] for r in ran), ran
            assert sum(r['recovery_completed'] for r in ran) == 4
        else:
            assert not any(r['strict_completed'] for r in ran)
            assert all(r['capped_completion_ms'] == 120000 for r in ran)
            assert not any(r['database']['writes'] for r in ran)
    assert result['spend'] == json.loads((tmp_path / 'batch/spend.jsonl').read_text().splitlines()[-1])
    with pytest.raises(FileExistsError):
        await pilot.run_batch(tmp_path / 'batch', frozen['sha256'], jev_credential='fixture', peer_credential='fixture')


async def test_real_product_cancellation_preserves_denominator(chromium_required, monkeypatch, tmp_path, product_python):
    import json
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_real_product_route as pilot
    calls, _ = install_product_http(monkeypatch, 'cancel')
    frozen = pilot.prepare(tmp_path / 'cancel', app_python=product_python)
    with pytest.raises(asyncio.CancelledError):
        await pilot.run_batch(tmp_path / 'cancel', frozen['sha256'], jev_credential='fixture', peer_credential='fixture')
    result = json.loads((tmp_path / 'cancel/result.json').read_text())
    assert len(result['rows']) == 12 and len(calls) == 1
    assert result['rows'][0]['status'] == 'cancelled' and result['rows'][0]['cleanup_confirmed']
    assert sum(r['status'] == 'not_run' for r in result['rows']) == 11
    assert not result['rows'][0]['database']['writes']


async def test_real_product_wrong_record_write_is_not_completion(chromium_required, monkeypatch, tmp_path, product_python):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_real_product_route as pilot
    install_product_http(monkeypatch)
    frozen = pilot.prepare(tmp_path / 'wrong-record', app_python=product_python)
    case = next(c for c in frozen['cases'] if c['kind'] == 'update' and not c['recovery'] and c['order'] == 0)
    case['start_path'] = '/work_items/update/WzJd/'
    row = await pilot.run_task(case, 'jt', tmp_path / 'wrong-record', app_python=product_python, jev_credential='fixture', peer_credential='fixture')
    assert row['cleanup_confirmed'] and row['app_unchanged']
    assert len(row['database']['writes']) == 1 and row['database']['writes'][0]['id'] == 2
    assert row['database']['records'] != case['oracle']['rows']
    assert not row['strict_completed'] and row['capped_completion_ms'] == 120000
    assert row['result']['reason'] == 'effect_unknown'
    assert sum(r['method'] == 'POST' for r in row['http']) == 1


async def test_real_product_private_oracle_never_enters_observer_or_model(chromium_required, monkeypatch, tmp_path, product_python):
    import json
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_real_product_route as pilot
    _, packets = install_product_http(monkeypatch)
    frozen = pilot.prepare(tmp_path / 'private', app_python=product_python)
    case = frozen['cases'][0]
    expected = case['oracle']['rows']
    case['oracle']['rows'] = [{'PRIVATE_SENTINEL': 'never send'}]
    row = await pilot.run_task(case, 'jt', tmp_path / 'private', app_python=product_python, jev_credential='fixture', peer_credential='fixture')
    assert row['database']['records'] == expected and row['result']['status'] == 'completed'
    assert not row['strict_completed'] and row['cleanup_confirmed']
    assert 'PRIVATE_SENTINEL' not in json.dumps(packets)


async def test_real_product_failed_readback_preserves_attempted_row(chromium_required, monkeypatch, tmp_path, product_python):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_real_product_route as pilot
    calls, _ = install_product_http(monkeypatch)
    frozen = pilot.prepare(tmp_path / 'failed-read', app_python=product_python)
    original = pilot.database_state
    reads = 0
    def fail_read(path):
        nonlocal reads
        reads += 1
        if reads > 1:
            raise OSError('readback unavailable')
        return original(path)
    monkeypatch.setattr(pilot, 'database_state', fail_read)
    result = await pilot.run_batch(tmp_path / 'failed-read', frozen['sha256'], jev_credential='fixture', peer_credential='fixture')
    assert not result['completed'] and result['spend']['stop_reason'] == 'operational_error'
    assert result['rows'][0]['status'] == 'error'
    assert sum(r['status'] == 'not_run' for r in result['rows']) == 11
    assert not calls


async def test_checkbox_diagnostic_distinguishes_values_and_written_columns(chromium_required, product_python, monkeypatch, tmp_path):
    import httpx
    import httpx2
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_checkbox_diagnostics as diagnostic
    def forbidden(*args, **kwargs):
        raise AssertionError('diagnosis allocated a model HTTP client')
    monkeypatch.setattr(httpx.AsyncClient, '__init__', forbidden)
    monkeypatch.setattr(httpx2.AsyncClient, '__init__', forbidden)
    result = await diagnostic.run(tmp_path / 'manual', app_python=product_python)
    assert result['completed'] and result['model_calls'] == 0
    assert len(result['rows']) == 4 and all(r['cleanup_confirmed'] and r['app_unchanged'] for r in result['rows'])
    assert all(r['value_success'] and len(r['evidence']['writes']) == 1 for r in result['rows'])
    for row in result['rows']:
        columns = {w['column_name'] for w in row['evidence']['column_writes']}
        assert columns == ({'id', 'title', 'notes'} if row['mode'] == 'all' else {'title'})
        assert row['column_success'] == (row['mode'] == 'title')
        assert row['input_attempts'] == 3
    with pytest.raises(FileExistsError):
        await diagnostic.run(tmp_path / 'manual', app_python=product_python)


async def test_dom_same_named_checkboxes_have_node_effects_not_fake_semantic_identity(channel):
    from agent_computer_use.controller import ComputerUseController
    from agent_computer_use.contracts import DecisionResult
    from agent_computer_use.visual_selector import VisualSelector
    browser, ctx = channel
    await browser.page.set_content('''<label>Same<input type="checkbox" id="first"></label>
      <label>Same<input type="checkbox" id="second" onchange="document.querySelector('output').textContent='second'"></label>
      <output aria-label="Result">idle</output>''')
    contract = GoalContract.from_input({**goal().model_dump(mode='json'), 'inputs': [],
        'completion': [{'key': 'status:Result', 'value': 'second'}]})
    observed = await browser.observe('managed-page', ctx)
    offered = ActionBuilder(visual=True).build('goal', 1, contract, observed)
    assert len(offered.actions) == 2 and offered.reason == 'visual_required'
    assert not ActionBuilder().build('goal', 1, contract, observed).actions
    effects = [d.effect[0] for d in offered.details]
    assert len({f.key for f in effects}) == 2
    assert all(any(f.key == e.key and f.value == 'false' for f in observed.facts) for e in effects)
    assert not any(f.key == 'checkbox:Same' for f in observed.facts)
    second = offered.actions[1].target_ref
    class ScriptedVisual(VisualSelector):
        async def choose(self, goal, snapshot, actions, context):
            action = next(a for a in actions.actions if a.target_ref == second)
            return DecisionResult(actions.binding, 'candidate', action.id)
    host = ComputerUseController(browser, browser, selector=ScriptedVisual(browser))
    result = await host.run(SubAgentRequest('Check the second box', '', 'dom-task', contract.model_dump(mode='json')), ctx)
    assert result.reason == 'goal_verified' and len(host.receipts) == 1
    assert not await browser.page.locator('#first').is_checked()
    assert await browser.page.locator('#second').is_checked()


@pytest.mark.parametrize('names,reason', [(['chk_title','chk_notes'],'jev_eligible'), (['same','same'],'visual_required')])
async def test_dom_checkbox_uses_authored_form_names_only_when_distinct(channel, names, reason):
    browser, ctx = channel
    await browser.page.set_content(''.join(f'<label>Same<input type="checkbox" name="{name}"></label>' for name in names))
    observed = await browser.observe('managed-page', ctx)
    offered = ActionBuilder(visual=True).build('goal', 1, goal(), observed)
    assert len(offered.actions) == 2 and offered.reason == reason
    labels = [d.label for d in offered.details]
    if reason == 'jev_eligible':
        assert labels == ['Same [name=chk_title]', 'Same [name=chk_notes]']
        assert len({d.effect[0].key for d in offered.details}) == 2
    else:
        assert labels == ['Same','Same']


@pytest.mark.parametrize('behavior', ['prevent', 'replace'])
async def test_dom_same_named_checkbox_does_not_verify_other_node_or_prevented_click(channel, behavior):
    from agent_computer_use.controller import ComputerUseController
    from agent_computer_use.contracts import DecisionResult
    from agent_computer_use.visual_selector import VisualSelector
    browser, ctx = channel
    handler = ('event.preventDefault();' if behavior == 'prevent' else
               'const n=this.cloneNode(true);n.checked=true;this.replaceWith(n);')
    await browser.page.set_content(f'''<label>Same<input name="a" type="checkbox" onclick="{handler}document.querySelector('output').textContent='done'"></label>
      <label>Same<input name="b" type="checkbox"></label><output aria-label="Result">idle</output>''')
    contract = GoalContract.from_input({**goal().model_dump(mode='json'), 'inputs': [],
        'completion': [{'key': 'status:Result', 'value': 'done'}]})
    class ScriptedVisual(VisualSelector):
        async def choose(self, goal, snapshot, actions, context):
            target = next(d.action_id for d in actions.details if d.label == 'Same [name=a]')
            return DecisionResult(actions.binding, 'candidate', target)
    host = ComputerUseController(browser, browser, selector=ScriptedVisual(browser))
    result = await host.run(SubAgentRequest('Check a', '', 'dom-task', contract.model_dump(mode='json')), ctx)
    assert result.reason == 'effect_unknown' and len(host.receipts) == 1
    assert await browser.page.locator('output').inner_text() == 'done'


async def test_dom_checkbox_bound_facts_cannot_be_forged_by_page_roles(channel):
    browser, ctx = channel
    await browser.page.set_content('<label>Same<input name="a" type="checkbox"></label><label>Same<input name="b" type="checkbox"></label>')
    before = await browser.observe('managed-page', ctx)
    offered = ActionBuilder(visual=True).build('goal', 1, goal(), before)
    key = offered.details[0].effect[0].key
    await browser.page.evaluate('hash => {const n=document.createElement("span");n.role="dom:checked";n.setAttribute("aria-label",hash);n.textContent="true";document.body.append(n)}', key.removeprefix('dom:checked:'))
    after = await browser.observe('managed-page', ctx)
    assert [f.value for f in after.facts if f.key == key] == ['false']


async def test_dom_checkbox_name_annotation_collision_stays_ambiguous(channel):
    browser, ctx = channel
    await browser.page.set_content('''<label>Same<input name="x" type="checkbox"></label>
      <label>Same<input name="y" type="checkbox"></label>
      <label>Same [name=x]<input name="z" type="checkbox"></label>''')
    observed = await browser.observe('managed-page', ctx)
    offered = ActionBuilder(visual=True).build('goal', 1, goal(), observed)
    assert len(offered.actions) == 3 and offered.reason == 'visual_required'


async def test_checkbox_diagnostic_host_enforces_column_receipt_without_models(chromium_required, product_python, monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_checkbox_diagnostics as diagnostic
    result = await diagnostic.run(tmp_path / 'host', app_python=product_python, include_host=True)
    assert result['completed'] and result['model_calls'] == 0 and not result['client_attempts']
    assert len(result['rows']) == 8
    for row in result['rows']:
        assert row['value_success'] and row['cleanup_confirmed'] and row['input_attempts'] == 3
        assert row['captures'][0]['column_candidates'] == 3
        assert row['captures'][0]['reason'] == 'visual_required'
        criteria = row['captures'][0]['packet']['questions']['next_action']['criteria']
        repeated = [value for value in criteria.values()
                    if isinstance(value, dict) and value['label'] == 'work_items']
        assert len(repeated) == 2
        assert repeated[0]['current_value'] == repeated[1]['current_value'] == 'work_items'
        assert repeated[0]['effect'] == repeated[1]['effect']
        if row['actor'] == 'host':
            assert row['host_result']['reason'] == ('goal_verified' if row['mode'] == 'title' else 'effect_unknown')
            assert row['column_success'] == (row['mode'] == 'title')
            assert sum(r['method'] == 'POST' for r in row['http']) == 1


async def test_checkbox_diagnostic_cancellation_closes_and_keeps_attempted_case(chromium_required, product_python, monkeypatch, tmp_path):
    import json
    from tank_backend.agents.task_runtime import TaskRuntime
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_checkbox_diagnostics as diagnostic
    closing, release = asyncio.Event(), asyncio.Event()
    original = TaskRuntime.aclose
    async def delayed_close(self):
        closing.set()
        await release.wait()
        await original(self)
    monkeypatch.setattr(TaskRuntime, 'aclose', delayed_close)
    worker = asyncio.create_task(diagnostic.run(tmp_path / 'cancel', app_python=product_python))
    try:
        await asyncio.wait_for(closing.wait(), 10)
        worker.cancel()
        await asyncio.sleep(0)
        worker.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await worker
        result = json.loads((tmp_path/'cancel/result.json').read_text())
        assert len(result['rows']) == 4 and result['model_calls'] == 0
        assert result['rows'][0]['status'] == 'cancelled' and result['rows'][0]['cleanup_confirmed']
        assert not result['rows'][0]['value_success'] and len(result['rows'][0]['evidence']['writes']) == 1
        assert sum(r['status'] == 'not_run' for r in result['rows']) == 3
    finally:
        release.set()
        if not worker.done():
            worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)


async def test_checkbox_diagnostic_freeze_tamper_stops_before_next_app(chromium_required, product_python, monkeypatch, tmp_path):
    import json
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_checkbox_diagnostics as diagnostic
    original = diagnostic.run_case
    async def tamper_after_case(case, output, **kwargs):
        row = await original(case, output, **kwargs)
        frozen = json.loads((output/'freeze.json').read_text())
        frozen['no_models'] = False
        (output/'freeze.json').write_text(json.dumps(frozen))
        return row
    monkeypatch.setattr(diagnostic, 'run_case', tamper_after_case)
    result = await diagnostic.run(tmp_path/'tampered', app_python=product_python)
    assert not result['completed'] and result['model_calls'] == 0
    assert [r['status'] for r in result['rows']] == ['finished', 'error', 'not_run', 'not_run']
    assert result['rows'][1]['error_type'] == 'ValueError'
    assert not (tmp_path/'tampered'/result['rows'][1]['id']).exists()


async def test_dom_table_row_context_uses_visible_text(channel):
    browser, ctx = channel
    await browser.page.set_content('''<table><tbody>
      <tr><td>Alpha<span hidden>private-hidden</span></td><td><a href="/alpha">Edit</a></td></tr>
      <tr><td>Beta</td><td><a href="/beta">Edit</a></td></tr>
      </tbody></table>''')
    offered = await actions(browser, ctx)
    edits = [d for d in offered.details if d.label == 'Edit']
    assert [d.ancestors for d in edits] == [(('row', 'Alpha Edit'),), (('row', 'Beta Edit'),)]
    assert offered.reason == 'jev_eligible'


@pytest.mark.parametrize('names,reason', [
    (('Alpha', 'Beta'), 'jev_eligible'),
    (('Same', 'Same'), 'visual_required'),
    (('', ''), 'visual_required'),
])
async def test_dom_table_row_context_preserves_ambiguity(channel, names, reason):
    browser, ctx = channel
    await browser.page.set_content('<table><tbody>' + ''.join(
        f'<tr><td>{name}</td><td><button aria-controls="panel">Open</button></td></tr>'
        for name in names) + '</tbody></table><section id="panel" role="region" aria-label="Panel" hidden></section>')
    snapshot = await browser.observe('managed-page', ctx)
    offered = ActionBuilder(visual=True).build('goal', 1, goal(), snapshot)
    assert len(offered.actions) == 2 and offered.reason == reason


async def test_dom_table_row_context_limits_and_change_reject(channel):
    browser, ctx = channel
    await browser.page.set_content('<table><tr><td>Alpha</td><td><a href="/alpha">Edit</a></td></tr></table>')
    offered = await actions(browser, ctx)
    await browser.page.locator('td').first.evaluate("node => node.textContent = 'Beta'")
    assert not await browser.is_current(offered.binding, offered.actions[0], ctx)
    await browser.page.locator('td').first.evaluate("node => node.textContent = 'x'.repeat(257)")
    snapshot = await browser.observe('managed-page', ctx)
    assert not snapshot.complete
    assert not ActionBuilder(visual=True).build('goal', 1, goal(), snapshot).actions


def test_real_product_workflow_preparation_is_frozen_and_balanced(monkeypatch, tmp_path, product_python):
    import httpx
    import httpx2
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_real_product_route as pilot
    def forbidden(*args, **kwargs):
        raise AssertionError('preparation allocated a client or server')
    monkeypatch.setattr(httpx.AsyncClient, '__init__', forbidden)
    monkeypatch.setattr(httpx2.AsyncClient, '__init__', forbidden)
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', forbidden)
    frozen = pilot.prepare(tmp_path/'workflow', app_python=product_python, workflow=True)
    assert len(frozen['cases']) == 4 and len(frozen['schedule']) == 8
    assert frozen['workflow'] and len(pilot.freeze_inputs(product_python)['schedule']) == 12
    assert all(c['start_path'] == '/work_items/content/' and c['kind'] == 'update' for c in frozen['cases'])
    assert all(c['fault_path'] == c['oracle']['edit_path'] for c in frozen['cases'] if c['recovery'])
    first = {r['case']:r['arm'] for r in reversed(frozen['schedule'])}
    for recovery in (False, True):
        assert sorted(first[c['id']] for c in frozen['cases'] if c['recovery'] == recovery) == ['jt','v']
    assert pilot.load_freeze(tmp_path/'workflow', frozen['sha256']) == frozen
    import json
    (tmp_path/'workflow/freeze.json').write_text(json.dumps({**frozen, 'workflow':False}))
    with pytest.raises(ValueError):
        pilot.load_freeze(tmp_path/'workflow', frozen['sha256'])


@pytest.mark.parametrize('arm', ['v', 'jt'])
@pytest.mark.parametrize('index', range(4))
async def test_real_product_workflow_controller_locates_and_returns_list(chromium_required, monkeypatch, tmp_path, product_python, arm, index):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_real_product_route as pilot
    _, packets = install_product_http(monkeypatch)
    frozen = pilot.prepare(tmp_path/'workflow', app_python=product_python, workflow=True)
    case = frozen['cases'][index]
    row = await pilot.run_task(case, arm, tmp_path/'workflow', app_python=product_python,
                               jev_credential='fixture', peer_credential='fixture')
    assert row['strict_completed'] and row['workflow_completed'] and row['cleanup_confirmed'], row
    assert row['list_readback'] == case['oracle']['visible_list']
    assert len(row['database']['writes']) == 1 and sum(h['method'] == 'POST' for h in row['http']) == 1
    assert row['recovery_completed'] == case['recovery']
    if case['recovery']:
        assert next(h for h in row['http'] if h['injected'])['path'] == case['oracle']['edit_path']
    first = packets[0]['questions']['next_action']['criteria']
    assert any(v['label'] == 'Edit' and v['ancestors'] for v in first.values() if isinstance(v, dict))
    expected = ['Edit', *(['Retry'] if case['recovery'] else []),
                'Allow updating this column. [name=chk_title]', 'title', 'Update']
    assert [s['label'] for s in row['result']['details']['progress']['recent_steps']] == expected


@pytest.mark.parametrize('failure', ['missing', 'wrong', 'wrong_page'])
async def test_real_product_workflow_requires_actual_returned_list(chromium_required, monkeypatch, tmp_path, product_python, failure):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_real_product_route as pilot
    from playwright.async_api import Page
    install_product_http(monkeypatch)
    original = Page.evaluate
    changed = False
    async def corrupt_return(self, expression, arg=None):
        nonlocal changed
        if not changed and urlsplit(self.url).path == '/work_items/content/' and await self.get_by_text('Launch 0', exact=True).count():
            changed = True
            if failure == 'wrong_page':
                await self.goto(self.url.replace('/content/', '/'))
            elif failure == 'missing':
                await self.locator('table.cell-content').evaluate('table => table.remove()')
            else:
                await self.get_by_text('Launch 0', exact=True).evaluate("cell => cell.textContent = 'Stale rendering'")
        return await original(self, expression, arg=arg)
    monkeypatch.setattr(Page, 'evaluate', corrupt_return)
    frozen = pilot.prepare(tmp_path/'wrong-ui', app_python=product_python, workflow=True)
    case = frozen['cases'][0]
    row = await pilot.run_task(case, 'jt', tmp_path/'wrong-ui', app_python=product_python,
                               jev_credential='fixture', peer_credential='fixture')
    assert changed and row['database']['records'] == case['oracle']['rows']
    assert row['cleanup_confirmed'] and row['app_unchanged']
    assert not row['strict_completed'] and not row['workflow_completed']
    assert row['result']['reason'] == 'effect_unknown' and row['capped_completion_ms'] == 120000
    assert len(row['database']['writes']) == 1 and sum(h['method'] == 'POST' for h in row['http']) == 1


async def test_real_product_workflow_wrong_record_is_not_completion(chromium_required, monkeypatch, tmp_path, product_python):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_real_product_route as pilot
    install_product_http(monkeypatch, 'wrong_record')
    frozen = pilot.prepare(tmp_path/'wrong-record', app_python=product_python, workflow=True)
    row = await pilot.run_task(frozen['cases'][0], 'jt', tmp_path/'wrong-record', app_python=product_python,
                               jev_credential='fixture', peer_credential='fixture')
    assert row['cleanup_confirmed'] and not row['strict_completed'] and not row['workflow_completed']
    assert len(row['database']['writes']) == 1 and row['database']['writes'][0]['id'] == 2
    assert sum(h['method'] == 'POST' for h in row['http']) == 1


async def test_real_product_workflow_private_oracle_is_not_readback(chromium_required, monkeypatch, tmp_path, product_python):
    import json
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_real_product_route as pilot
    _, packets = install_product_http(monkeypatch)
    frozen = pilot.prepare(tmp_path/'private-ui', app_python=product_python, workflow=True)
    case = frozen['cases'][0]
    case['oracle']['visible_list'] = {'PRIVATE_UI_SENTINEL': 'never send'}
    row = await pilot.run_task(case, 'jt', tmp_path/'private-ui', app_python=product_python,
                               jev_credential='fixture', peer_credential='fixture')
    assert row['cleanup_confirmed'] and row['result']['status'] == 'completed'
    assert not row['strict_completed'] and not row['workflow_completed']
    assert 'PRIVATE_UI_SENTINEL' not in json.dumps(packets)


@pytest.mark.parametrize('failure', [None, 'unknown', 'cleanup', 'cancel'])
async def test_real_product_workflow_batch_preserves_denominator(chromium_required, monkeypatch, tmp_path, product_python, failure):
    import json
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_real_product_route as pilot
    from agent_computer_use.channels.dom import ManagedChromiumChannel
    calls, _ = install_product_http(monkeypatch, failure)
    if failure == 'cleanup':
        original = ManagedChromiumChannel.aclose
        async def fail_close(self):
            await original(self)
            raise RuntimeError('reported cleanup failure')
        monkeypatch.setattr(ManagedChromiumChannel, 'aclose', fail_close)
    out = tmp_path/'workflow-batch'
    frozen = pilot.prepare(out, app_python=product_python, workflow=True)
    if failure == 'cancel':
        with pytest.raises(asyncio.CancelledError):
            await pilot.run_batch(out, frozen['sha256'], jev_credential='fixture', peer_credential='fixture')
    else:
        await pilot.run_batch(out, frozen['sha256'], jev_credential='fixture', peer_credential='fixture')
    result = json.loads((out/'result.json').read_text())
    assert len(result['rows']) == 8
    ran = [r for r in result['rows'] if r['status'] != 'not_run']
    if failure is None:
        assert result['completed'] and len(ran) == 8
        assert all(r['strict_completed'] and r['workflow_completed'] and r['cleanup_confirmed'] for r in ran)
        assert sum(r['recovery_completed'] for r in ran) == 4
    else:
        assert not result['completed'] and len(ran) == 1
        assert not ran[0]['strict_completed'] and ran[0]['capped_completion_ms'] == 120000
        # Cancellation after SDK entry retains the earlier unknown-usage stop.
        assert result['spend']['stop_reason'] == {'unknown':'unknown_usage','cleanup':'cleanup_failed','cancel':'unknown_usage'}[failure]
        if failure == 'cancel':
            assert ran[0]['status'] == 'cancelled' and ran[0]['cleanup_confirmed']
        if failure in ('unknown', 'cancel'):
            assert len(calls) == 1 and not ran[0]['database']['writes']
    with pytest.raises(FileExistsError):
        await pilot.run_batch(out, frozen['sha256'], jev_credential='fixture', peer_credential='fixture')


def test_action_live_prepare_has_balanced_three_arms_without_clients(
    tmp_path,
    product_python,
    linkding_root,
    monkeypatch,
    legacy_product_fingerprints,
):
    import collections
    import copy
    import httpx
    import httpx2
    from benchmarks.computer_use import jev_action_live as pilot

    def forbidden(*args, **kwargs):
        raise AssertionError("preparation must remain offline")

    monkeypatch.setattr(httpx.AsyncClient, "__init__", forbidden)
    monkeypatch.setattr(httpx2.AsyncClient, "__init__", forbidden)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden)
    frozen = pilot.prepare(
        tmp_path / "study",
        sql_python=product_python,
        link_root=linkding_root,
        namespace="action-test-36",
    )
    assert len(frozen["cases"]) == len(frozen["schedule"]) == 36
    assert collections.Counter(s["policy"] for s in frozen["schedule"]) == {
        "v": 12,
        "jt": 12,
        "ja": 12,
    }
    assert len({c["cluster_id"] for c in frozen["cases"]}) == 6
    for product in ("sqlite-web", "linkding"):
        for condition in ("cold", "prewarmed"):
            slots = [
                s
                for s in frozen["schedule"]
                if s["product"] == product and s["condition"] == condition
            ]
            for position in range(3):
                assert {s["policy"] for s in slots if s["position"] == position} == {
                    "v",
                    "jt",
                    "ja",
                }
    pairs = collections.defaultdict(list)
    for case in frozen["cases"]:
        goal = copy.deepcopy(case["goal"])
        goal.pop("goal_id")
        pairs[case["pair_id"]].append(goal)
        assert case["goal"]["goal_id"] == case["id"]
        assert not any(
            x in case["goal"]["goal_id"]
            for x in ("missing", "same-title", "unique", "-ja")
        )
    assert len(pairs) == 12 and all(
        len(g) == 3 and g[0] == g[1] == g[2] for g in pairs.values()
    )
    assert pilot.load_freeze(tmp_path / "study", frozen["sha256"]) == frozen
    with pytest.raises(FileExistsError):
        pilot.prepare(
            tmp_path / "study",
            sql_python=product_python,
            link_root=linkding_root,
            namespace="action-test-36",
        )


async def test_action_live_all_36_trials_use_real_controller_and_sdk(
    tmp_path,
    product_python,
    linkding_root,
    channel,
    legacy_product_fingerprints,
):
    import collections
    import json
    from benchmarks.computer_use import jev_action_live as pilot
    from agent_computer_use.visual_selector import VisualSelector

    original = pilot.jev_action_admission.VisualSelector
    assert VisualSelector is original
    frozen = pilot.prepare(
        tmp_path / "study",
        sql_python=product_python,
        link_root=linkding_root,
        namespace="action-admission-dev-20261024",
    )
    result = await pilot.run_batch(tmp_path / "study", frozen["sha256"], mode="fake")
    assert result["completed"] and result["spend"]["stop_reason"] is None
    assert len(result["rows"]) == 36 and all(
        r["attempted"] and r["cleanup_confirmed"] for r in result["rows"]
    )
    assert all(
        r["labels"]["negative_verified" if r["negative"] else "strict_verified"]
        for r in result["rows"]
    )
    assert result["fake_external_requests"] == 0
    from agent_computer_use import visual_selector

    assert visual_selector.VisualSelector is original
    report = pilot.audit_study(tmp_path / "study", frozen["sha256"])
    assert report["complete"] and report["planned"] == 36
    live = pilot.prepare(
        tmp_path / "live",
        sql_python=product_python,
        link_root=linkding_root,
        namespace=frozen["namespace"],
    )
    assert live["sha256"] == frozen["sha256"]
    with pytest.raises(ValueError, match="readiness"):
        await pilot.run_batch(
            tmp_path / "live",
            live["sha256"],
            mode="live",
            qualification=tmp_path / "study",
        )
    assert not (tmp_path / "live/started.json").exists()
    counts = collections.defaultdict(collections.Counter)
    for row in result["rows"]:
        for call in row["calls"]:
            counts[row["policy"]][
                "visual" if "messages" in call["request"] else "text"
            ] += 1
    assert counts["v"]["text"] == 0 and counts["ja"]["text"] > counts["jt"]["text"]
    assert counts["ja"]["visual"] < counts["jt"]["visual"]
    records = [
        json.loads(line)
        for line in (tmp_path / "study/sdk-diagnostics.jsonl").read_text().splitlines()
    ]
    assert len(records) == 3 * sum(len(r["calls"]) for r in result["rows"])
    with pytest.raises(FileExistsError):
        await pilot.run_batch(tmp_path / "study", frozen["sha256"], mode="fake")


@pytest.mark.parametrize("tamper", ["freeze", "saved_source"])
def test_action_live_rejects_tampered_freeze(
    tmp_path, product_python, linkding_root, tamper,
    legacy_product_fingerprints,
):
    import json
    from benchmarks.computer_use import jev_action_live as pilot

    root = tmp_path / "study"
    frozen = pilot.prepare(
        root,
        sql_python=product_python,
        link_root=linkding_root,
        namespace="action-tamper",
    )
    if tamper == "freeze":
        value = json.loads((root / "freeze.json").read_text())
        value["max_actions"] += 1
        (root / "freeze.json").write_text(json.dumps(value))
    else:
        (root / "source/benchmarks/computer_use/jev_action_live.py").write_text(
            "tampered"
        )
    with pytest.raises(ValueError):
        pilot.load_freeze(root, frozen["sha256"])


async def test_action_live_without_readiness_never_starts(
    tmp_path,
    product_python,
    linkding_root,
    monkeypatch,
    legacy_product_fingerprints,
):
    import httpx
    from benchmarks.computer_use import jev_action_live as pilot

    root = tmp_path / "study"
    frozen = pilot.prepare(
        root,
        sql_python=product_python,
        link_root=linkding_root,
        namespace="action-no-ready",
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("live gate created a client")

    monkeypatch.setattr(httpx.AsyncClient, "__init__", forbidden)
    with pytest.raises(ValueError, match="readiness"):
        await pilot.run_batch(root, frozen["sha256"], mode="live")
    assert not (root / "started.json").exists()


async def test_action_live_unknown_usage_stops_and_retains_all_36_slots(
    tmp_path,
    product_python,
    linkding_root,
    monkeypatch,
    channel,
    legacy_product_fingerprints,
):
    import json
    from agent_computer_use import visual_selector
    from benchmarks.computer_use import jev_action_live as pilot, jev_fake_http

    root = tmp_path / "study"
    frozen = pilot.prepare(
        root,
        sql_python=product_python,
        link_root=linkding_root,
        namespace="action-unknown",
    )
    reply = jev_fake_http.reply

    def unknown(payload):
        data = reply(payload)
        data.pop("usage", None)
        return data

    original = visual_selector.VisualSelector
    monkeypatch.setattr(jev_fake_http, "reply", unknown)
    result = await pilot.run_batch(root, frozen["sha256"], mode="fake")
    assert not result["completed"] and result["spend"]["stop_reason"] == "unknown_usage"
    assert (
        len(result["rows"]) == 36 and sum(r["attempted"] for r in result["rows"]) == 1
    )
    assert sum(r["status"] == "not_run" for r in result["rows"]) == 35
    assert visual_selector.VisualSelector is original
    records = [
        json.loads(line)
        for line in (root / "sdk-diagnostics.jsonl").read_text().splitlines()
    ]
    assert records[-1]["usage_status"] == "unknown"
    assert records[-1]["stop_reason"] == "unknown_usage"
    assert len(result["spend"]["requests"]) == 1
    with pytest.raises(ValueError):
        pilot.audit_study(root, frozen["sha256"])


async def test_action_live_cancel_restores_partial_receipt(
    tmp_path, product_python, linkding_root, monkeypatch,
    legacy_product_fingerprints,
):
    import json
    from benchmarks.computer_use import jev_action_live as pilot
    root = tmp_path / "study"
    frozen = pilot.prepare(root, sql_python=product_python, link_root=linkding_root,
                           namespace="action-cancel")
    async def cancelled(case, slot, output, *args):
        path = output / slot["id"]
        path.mkdir()
        (path / "row.json").write_text(json.dumps({
            "cleanup_confirmed": True, "status": "cancelled", "partial_receipt_marker": True}))
        raise asyncio.CancelledError
    monkeypatch.setattr(pilot, "run_trial", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await pilot.run_batch(root, frozen["sha256"], mode="fake")
    result = json.loads((root / "result.json").read_text())
    assert len(result["rows"]) == 36 and sum(r["attempted"] for r in result["rows"]) == 1
    assert result["rows"][0]["cleanup_confirmed"] is True
    assert result["rows"][0]["partial_receipt_marker"] is True
    assert result["spend"]["stop_reason"] == "cancelled"


def test_boundary_goal_verification_requires_unique_target_and_full_state():
    import copy
    from benchmarks.computer_use.jev_action_boundary import goal_reached

    before = [
        {"id": 1, "title": "Keep", "notes": "left"},
        {"id": 2, "title": "Target", "notes": "right"},
    ]
    after = copy.deepcopy(before)
    after[1]["notes"] = "Requested note"
    assert goal_reached(before, after, {"title": "Target"}, {"notes": "Requested note"})
    after[0]["title"] = "Unrequested change"
    assert not goal_reached(before, after, {"title": "Target"}, {"notes": "Requested note"})
    assert not goal_reached(before, before, {"title": "Absent"}, {"notes": "Requested note"})
    ambiguous = copy.deepcopy(before)
    ambiguous[0]["title"] = "Target"
    after = copy.deepcopy(ambiguous)
    after[1]["notes"] = "Requested note"
    assert not goal_reached(ambiguous, after, {"title": "Target"}, {"notes": "Requested note"})


def test_boundary_prepare_freezes_twelve_new_tasks_and_twentyfour_slots(
    tmp_path, product_python, linkding_root, monkeypatch,
    legacy_product_fingerprints,
):
    import collections
    import copy
    import httpx
    import httpx2
    from benchmarks.computer_use import jev_action_live as pilot

    def forbidden(*args, **kwargs):
        raise AssertionError("offline preparation allocated external client/process")

    monkeypatch.setattr(httpx.AsyncClient, "__init__", forbidden)
    monkeypatch.setattr(httpx2.AsyncClient, "__init__", forbidden)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden)
    frozen = pilot.prepare(tmp_path / "boundary", sql_python=product_python,
                           link_root=linkding_root, namespace="boundary-freeze", boundary=True)
    assert len(frozen["cases"]) == len(frozen["schedule"]) == 24
    assert frozen["revision"] == "action-admission-boundary-1"
    assert collections.Counter(s["policy"] for s in frozen["schedule"]) == {"v": 12, "ja": 12}
    assert {s["condition"] for s in frozen["schedule"]} == {"cold"}
    assert len({s["pair_id"] for s in frozen["schedule"]}) == 12
    for product in ("sqlite-web", "linkding"):
        slots = [s for s in frozen["schedule"] if s["product"] == product]
        assert collections.Counter(s["policy"] for s in slots if s["position"] == 0) == {"v": 3, "ja": 3}
    goals = collections.defaultdict(list)
    for c in frozen["cases"]:
        goal = copy.deepcopy(c["goal"])
        assert goal.pop("goal_id") == c["id"]
        assert goal["completion"] == [{"key": "status:Requested changes verified", "value": "true"}]
        assert goal["outcomes"][0] == {"id": "requested-editor", "conditions": [{"key": "status:Requested editor observed", "value": "true"}]}
        goals[c["pair_id"]].append(goal)
    assert all(len(g) == 2 and g[0] == g[1] for g in goals.values())
    assert any(c["start_path"] == "/work_items/" for c in frozen["cases"])
    assert any("/work_items/row/" in c["start_path"] for c in frozen["cases"])
    assert any("?details=" in c["start_path"] for c in frozen["cases"])
    assert any(len(c["goal"]["inputs"]) == 2 for c in frozen["cases"])
    assert {c["negative"] for c in frozen["cases"] if c["negative"]} == {"missing", "ambiguous"}
    assert pilot.load_freeze(tmp_path / "boundary", frozen["sha256"]) == frozen


async def test_boundary_all_twentyfour_trials_use_real_products_and_independent_labels(
    tmp_path, product_python, linkding_root, channel,
    legacy_product_fingerprints,
):
    from benchmarks.computer_use import jev_action_live as pilot

    out = tmp_path / "boundary"
    frozen = pilot.prepare(out, sql_python=product_python, link_root=linkding_root,
                           namespace="action-boundary-dev-20261024", boundary=True)
    result = await pilot.run_batch(out, frozen["sha256"], mode="fake")
    assert result["completed"], [(r["status"], r.get("error_type")) for r in result["rows"]]
    assert result["fake_external_requests"] == 0
    assert len(result["rows"]) == 24 and all(r["cleanup_confirmed"] for r in result["rows"])
    cases = {c["id"]: c for c in frozen["cases"]}
    for r in result["rows"]:
        if r["policy"] == "v" and cases[r["case"]]["family"] == "schema-title":
            assert not r["labels"]["strict_verified"] and not r["calls"]
            assert r["result"]["reason"] == "visual_target_unavailable"
        else:
            assert r["labels"]["negative_verified" if r["negative"] else "strict_verified"], r["id"]
    report = pilot.audit_study(out, frozen["sha256"])
    assert report["planned"] == 24 and set(report["policies"]) == {"v", "ja"}
    assert report["policies"]["ja"]["positive_passed"] == 8
    assert report["policies"]["v"]["positive_passed"] == 7
    assert all(p["negative_passed"] == 4 for p in report["policies"].values())

    # A valid receipt seal must not make an unrequested business write acceptable.
    import hashlib
    import json
    import sqlite3
    from benchmarks.computer_use import jev_action_boundary as boundary
    sample = next(r for r in result["rows"] if r["product"] == "sqlite-web" and
                  r["policy"] == "ja" and cases[r["case"]]["family"] == "multi-field")
    folder = out / "trials" / sample["id"]
    database, proof_path = folder / "after.db", folder / "cleanup-proof.json"
    original_db, original_proof = database.read_bytes(), proof_path.read_bytes()
    try:
        with sqlite3.connect(database) as db:
            db.execute("UPDATE work_items SET notes='Unrequested' WHERE id=1")
        proof = json.loads(original_proof)
        proof["files"]["after.db"] = hashlib.sha256(database.read_bytes()).hexdigest()
        proof_path.write_text(json.dumps(proof))
        labels = boundary.audit_trial(cases[sample["case"]], sample, folder)
        assert not labels["strict_verified"] and labels["critical_events"] > 0
    finally:
        database.write_bytes(original_db)
        proof_path.write_bytes(original_proof)
    assert pilot.audit_study(out, frozen["sha256"]) == report


def test_boundary_missing_readiness_and_missing_capture_refuse_before_send(
    tmp_path, product_python, linkding_root, monkeypatch,
    legacy_product_fingerprints,
):
    import httpx
    import httpx2
    from benchmarks.computer_use import jev_action_live as pilot

    def forbidden(*args, **kwargs):
        raise AssertionError("readiness rejection allocated SDK")

    monkeypatch.setattr(httpx.AsyncClient, "__init__", forbidden)
    monkeypatch.setattr(httpx2.AsyncClient, "__init__", forbidden)
    out = tmp_path / "boundary"
    frozen = pilot.prepare(out, sql_python=product_python, link_root=linkding_root,
                           namespace="boundary-no-send", boundary=True)
    with pytest.raises(ValueError, match="readiness"):
        pilot.check_live_ready(out, frozen, None, None)
    assert not (out / "started.json").exists()
    assert pilot.audit_policy({"calls": [], "events": []}, out) == {
        "text_calls": 0, "visual_calls": 0, "logical_fallbacks": 0}
    with pytest.raises(ValueError, match="capture"):
        pilot.audit_policy({"calls": [], "events": [{"kind": "model_call"}]}, out)


def test_boundary_completion_requires_complete_visible_returned_list():
    from benchmarks.computer_use.jev_action_boundary import list_reached

    rows = [{"id": 1, "title": "Saved", "notes": "Keep"}]
    assert list_reached(rows, {"path": "/work_items/content/", "columns": ["id", "title", "notes"],
                               "rows": [["1", "Saved", "Keep"]]}, "sqlite-web")
    assert not list_reached(rows, {"path": "/work_items/update/WzFd/", "columns": [], "rows": []}, "sqlite-web")
    assert not list_reached(rows, {"path": "/work_items/content/", "columns": ["id", "title", "notes"],
                                   "rows": [["1", "Saved", "Wrong"]]}, "sqlite-web")


@pytest.mark.parametrize('scenario', [
    'save', 'fill-only', 'navigate-only', 'wrong-row', 'protected-field', 'other-record',
])
async def test_table_readback_real_product_runner_verifies_saved_rows(
    monkeypatch, tmp_path, product_python, chromium_required, scenario,
):
    import json
    from unittest.mock import MagicMock

    import httpx
    from agent_computer_use.channels.dom import dom_table_fact
    from tank_backend.agents.approval import PendingToolCallStore, ToolApprovalPolicy
    from tank_backend.agents.definition import parse_agent_file
    from tank_backend.agents.resources import DesktopResource
    from tank_backend.agents.runner import AgentRunner
    from tank_backend.config.app_config import AppConfig
    from tank_backend.pipeline.bus import Bus
    from tank_backend.plugin.manifest import read_manifest_from_yaml
    from tank_backend.plugin.registry import ExtensionRegistry

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_real_product_route as product

    seed = [{'id': 1, 'title': 'Nora', 'notes': 'Keep A'},
            {'id': 2, 'title': 'Tavi', 'notes': 'Keep B'}]
    database = tmp_path / 'fixture.db'
    product.create_database(database, seed)
    before = product.database_state(database)
    calls, events = [], []

    class Observer:
        def on_event(self, kind, metadata):
            events.append((kind, metadata))

    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            payload = json.loads(request.content)
            calls.append(payload)
            native = 'questions' in payload
            packet = payload if native else json.loads(payload['messages'][1]['content'][0]['text'])
            criteria = packet['questions']['next_action']['criteria']
            facts = {f['key']: f['value'] for f in packet['state']['snapshot']['facts']}
            chosen = 'none'
            for key, candidate in criteria.items():
                if not isinstance(candidate, dict):
                    continue
                label = candidate.get('label', '')
                if scenario == 'navigate-only' and label == 'Content':
                    chosen = key
                    break
                if scenario != 'navigate-only':
                    if 'chk_title' in label and candidate.get('current_value') == 'false':
                        chosen = key
                        break
                    if candidate.get('operation') == 'fill' and label == 'title':
                        chosen = key
                        break
                    if scenario != 'fill-only' and label == 'Update' and facts.get('textbox:title') == 'Miro':
                        if scenario in {'protected-field', 'other-record'}:
                            def concurrent_change():
                                import sqlite3
                                from contextlib import closing

                                with closing(sqlite3.connect(database)) as db:
                                    db.execute('UPDATE work_items SET notes=? WHERE id=?',
                                               ('Changed', 1 if scenario == 'protected-field' else 2))
                                    db.commit()
                            await asyncio.to_thread(concurrent_change)
                        chosen = key
                        break
            if native:
                return httpx.Response(200, json={'model': 'jev-1.14.0', 'answers': {'next_action': {
                    'type': 'choice', 'choice': chosen, 'confidence': 1,
                    'probabilities': {k: int(k == chosen) for k in criteria}}},
                    'usage': {'input_tokens': 12, 'output_tokens': 0}})
            return httpx.Response(200, json={'id': 'fixture', 'object': 'chat.completion', 'created': 1,
                'model': 'fixture-vision', 'choices': [{'index': 0, 'finish_reason': 'stop',
                'message': {'role': 'assistant', 'content': json.dumps({'choice': chosen})}}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 2, 'total_tokens': 12}})

    monkeypatch.setattr(httpx, 'AsyncHTTPTransport', HTTP)
    monkeypatch.setenv('RAW_TABLE_TEST_KEY', 'fixture-only')
    with (tmp_path / 'server.log').open('w') as log:
        server = await asyncio.create_subprocess_exec(
            str(product_python), str(Path(product.__file__)), '--serve', '--database', str(database),
            '--output', str(tmp_path), env={'PATH': os.environ.get('PATH', '')},
            stdout=log, stderr=asyncio.subprocess.STDOUT)
        try:
            async with asyncio.timeout(10):
                while not (tmp_path / 'ready.json').is_file():
                    assert server.returncode is None
                    await asyncio.sleep(.05)
            origin = 'http://127.0.0.1:' + str(json.loads((tmp_path / 'ready.json').read_text())['port'])
            expected = dom_table_fact(origin + '/work_items/content/', ('id', 'title', 'notes'),
                                      (('1', 'Miro', 'Keep A'), ('2', 'Tavi', 'Keep B')))
            task = {'schema_version': 2, 'goal_id': scenario, 'scope': 'raw-table',
                'authorization_ref': 'current_task', 'allowed_operations': ['click', 'fill'],
                'intent': 'Change only record 1 title Nora to Miro, save and verify; keep notes and all other records.',
                'objective': 'Verify the saved record and unchanged public fields on the returned list.',
                'inputs': [{'key': 'title', 'purpose': 'Requested title', 'field_label': 'title', 'value': 'Miro'}],
                'completion': [expected.model_dump()]}
            definition_path = tmp_path / 'agent.md'
            definition_path.write_text('---\nname: raw-table\nextension: agent-computer-use:agent\nmodel: default\ndecision-model: jev\nvisual-model: vision\n---\nUse the goal.\n')
            definition = parse_agent_file(definition_path)
            manifest = read_manifest_from_yaml(Path(__file__).parents[1] / 'plugin.yaml')
            registry = ExtensionRegistry()
            for extension in manifest.extensions:
                registry.register(manifest.plugin_name, extension)
            edit_path = '/work_items/update/' + ('WzJd/' if scenario == 'wrong-row' else 'WzFd/')
            config = AppConfig.from_raw_dict({
                'llm': {'default': {'api_key': 'fixture-only', 'model': 'fixture-text', 'base_url': 'https://offline.invalid/v1'},
                        'vision': {'api_key': 'fixture-only', 'model': 'fixture-vision', 'base_url': 'https://offline.invalid/v1', 'max_tokens': 128}},
                'decision_models': {'jev': {'url': 'https://offline.invalid/v1/systemone', 'model': 'jev-1.14.0', 'credential_env': 'RAW_TABLE_TEST_KEY'}},
                'subagents': {'agent-computer-use:agent': {'config': {'selector': 'jev-action-vision',
                    'browser': {'scope': 'raw-table', 'url': origin + edit_path, 'readback_tables': True}}}}})
            runner = AgentRunner(MagicMock(), MagicMock(), Bus(), ToolApprovalPolicy(computer_mode='allow'),
                PendingToolCallStore(), {definition.name: definition}, registry=registry,
                app_config=config, desktop_resource=DesktopResource())
            outputs = [o async for o in runner.run_agent(definition, [], task_id=scenario,
                task_input=task, authorization=SubAgentAuthorization(frozenset({'desktop', 'network'})),
                observer=Observer(), max_actions=6, max_observations=24)]
            result = next(o.metadata['task_result'] for o in outputs if 'task_result' in o.metadata)
            after = product.database_state(database)
            assert result['cleanup'] == 'confirmed' and after['schema'] == before['schema']
            assert (result['status'] == 'completed') == (scenario == 'save'), result
            if scenario == 'save':
                assert not result['details']['pending_effect']
            if scenario in {'save', 'wrong-row', 'protected-field', 'other-record'}:
                target = 2 if scenario == 'wrong-row' else 1
                wanted = [{**r, 'title': 'Miro'} if r['id'] == target else dict(r) for r in seed]
                if scenario in {'protected-field', 'other-record'}:
                    wanted[0 if scenario == 'protected-field' else 1]['notes'] = 'Changed'
                assert after['records'] == wanted
                assert len(after['writes']) == (2 if scenario in {'protected-field', 'other-record'} else 1)
                http = [json.loads(line) for line in (tmp_path / 'http.jsonl').read_text().splitlines()]
                posts = [i for i, record in enumerate(http) if record['method'] == 'POST']
                assert len(posts) == 1
                assert sum(r['method'] == 'GET' and r['path'] == '/work_items/content/' for r in http[posts[0]+1:]) >= 2
            else:
                assert after['records'] == seed and after['writes'] == []
            if scenario == 'save':
                assert len(calls) == 3 and all('questions' in p for p in calls)
                assert len(result['details']['receipts']) == 3
                assert all(m['status'] == 'returned' for k, m in events
                           if k == 'model_call' and m['phase'] == 'finished')
        finally:
            if server.returncode is None:
                server.terminate()
            try:
                await asyncio.wait_for(server.wait(), 5)
            except TimeoutError:
                server.kill()
                await server.wait()


async def test_dom_spatial_observation_exposes_bound_main_frame_css_geometry(
    site, profile_store, chromium_required,
):
    from agent_computer_use.channels.dom import BrowserConfig, ManagedChromiumChannel
    from agent_computer_use.contracts import snapshot_json

    profile_store["spatial_html"] = """<!doctype html><a href="/destination"
      style="position:fixed;left:20px;top:140px;width:120px;height:30px">work_items</a>
      <a href="/destination"
      style="position:fixed;left:260px;top:20px;width:120px;height:30px">work_items</a>"""
    ctx = context()
    browser = ManagedChromiumChannel(BrowserConfig(
        scope="spatial", url=site + "spatial", observe_bounds=True))
    try:
        snapshot = await browser.observe("spatial", ctx)
        assert snapshot.ready and snapshot.complete
        assert snapshot.viewport == (1280, 720)
        assert [e.bounds for e in snapshot.elements] == [
            (20, 140, 120, 30), (260, 20, 120, 30)]
        payload = snapshot_json(snapshot)
        assert payload["geometry"] == {
            "coordinate_space": "main_frame_viewport_css_pixels", "viewport_size": (1280, 720)}
        assert await browser.is_snapshot_current(snapshot, ctx)
    finally:
        await browser.aclose()
        await ctx.runtime.aclose()


@pytest.mark.parametrize("frame_name", [None, "bound"])
async def test_dom_spatial_bounds_remain_opt_in_and_main_frame_only(
    site, chromium_required, frame_name,
):
    from agent_computer_use.channels.dom import BrowserConfig, ManagedChromiumChannel
    from agent_computer_use.contracts import snapshot_json

    ctx = context()
    config = BrowserConfig(scope="spatial", url=site + ("frame" if frame_name else ""),
                           frame_name=frame_name, observe_bounds=frame_name is not None)
    browser = ManagedChromiumChannel(config)
    try:
        snapshot = await browser.observe("spatial", ctx)
        assert snapshot.ready and snapshot.complete
        assert snapshot.viewport is None and all(e.bounds is None for e in snapshot.elements)
        assert "geometry" not in snapshot_json(snapshot)
    finally:
        await browser.aclose()
        await ctx.runtime.aclose()


@pytest.mark.parametrize("change", ["css", "viewport", "scroll"])
async def test_dom_spatial_layout_change_refuses_old_action_without_dom_mutation(
    site, profile_store, chromium_required, change,
):
    from agent_computer_use.channels.dom import BrowserConfig, ManagedChromiumChannel

    profile_store["spatial_html"] = """<!doctype html><body style="height:2000px">
      <a href="/destination" style="position:absolute;left:20px;top:140px">work_items</a>
      <a href="/destination" style="position:absolute;left:260px;top:20px">work_items</a>"""
    ctx = context()
    browser = ManagedChromiumChannel(BrowserConfig(
        scope="spatial", url=site + "spatial", observe_bounds=True))
    try:
        snapshot = await browser.observe("spatial", ctx)
        goal = GoalContract.from_input({"schema_version": 2, "goal_id": "position",
            "scope": "spatial", "authorization_ref": "current_task", "intent": "Open destination",
            "objective": "Open destination", "allowed_operations": ["click"],
            "completion": [{"key": "status:Page URL", "value": site + "destination"}]})
        actions = ActionBuilder(visual=True).build("position", 1, goal, snapshot)
        assert len(actions.actions) == 2
        page = browser.page
        assert page is not None
        markup = await page.content()
        if change == "css":
            await page.evaluate("""() => {
                const sheet = new CSSStyleSheet();
                sheet.replaceSync('a { transform: translateX(400px); }');
                document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];
            }""")
        elif change == "viewport":
            await page.set_viewport_size({"width": 1000, "height": 700})
        else:
            await page.evaluate("window.scrollTo(0, 60)")
        assert await page.content() == markup
        assert not await browser.is_snapshot_current(snapshot, ctx)
        receipt = await browser.dispatch(actions.binding, actions.actions[0], ctx)
        assert receipt.status == "not_sent" and receipt.reason == "stale_reference"
        assert page.url == site + "spatial"
    finally:
        await browser.aclose()
        await ctx.runtime.aclose()


async def test_spatial_hint_real_product_runner_navigates_with_jev_without_image(
    monkeypatch, tmp_path, product_python, chromium_required,
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

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_real_product_route as product

    database = tmp_path / "fixture.db"
    product.create_database(database, [{"id": 1, "title": "Nora", "notes": "Keep A"},
                                      {"id": 2, "title": "Tavi", "notes": "Keep B"}])
    before = product.database_state(database)
    calls = []
    selected_refs = []

    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            packet = json.loads(request.content)
            assert "questions" in packet, "spatial task must complete without image SDK"
            calls.append(packet)
            assert packet["state"]["snapshot"]["geometry"]["coordinate_space"] == "main_frame_viewport_css_pixels"
            elements = {e["ref"]: e for e in packet["state"]["snapshot"]["elements"]}
            choices = {k: c for k, c in packet["questions"]["next_action"]["criteria"].items()
                       if isinstance(c, dict) and c.get("label") == "work_items"}
            assert len(choices) == 2
            choice = min(choices, key=lambda k: elements[choices[k]["target_ref"]]["bounds"][0])
            selected_refs.append(choices[choice]["target_ref"])
            return httpx.Response(200, json={"model": "jev-1.14.0", "answers": {"next_action": {
                "type": "choice", "choice": choice, "confidence": 1,
                "probabilities": {k: int(k == choice) for k in packet["questions"]["next_action"]["criteria"]}}},
                "usage": {"input_tokens": 12, "output_tokens": 0}})

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)
    monkeypatch.setenv("SPATIAL_TEST_KEY", "fixture-only")
    with (tmp_path / "server.log").open("w") as log:
        server = await asyncio.create_subprocess_exec(str(product_python), str(Path(product.__file__)),
            "--serve", "--database", str(database), "--output", str(tmp_path),
            env={"PATH": os.environ.get("PATH", "")}, stdout=log, stderr=asyncio.subprocess.STDOUT)
        try:
            async with asyncio.timeout(10):
                while not (tmp_path / "ready.json").exists():
                    assert server.returncode is None
                    await asyncio.sleep(.05)
            origin = "http://127.0.0.1:" + str(json.loads((tmp_path / "ready.json").read_text())["port"])
            goal = {"schema_version": 2, "goal_id": "position", "scope": "spatial",
                "authorization_ref": "current_task", "allowed_operations": ["click"],
                "intent": "Use only the left sidebar work_items link to open its structure page.",
                "objective": "Open the structure using the requested sidebar link; do not modify data.",
                "spatial_hint": {"role": "link", "label": "work_items", "relation": "leftmost"},
                "completion": [{"key": "status:Page URL", "value": origin + "/work_items/"}]}
            path = tmp_path / "agent.md"
            path.write_text("---\nname: spatial\nextension: agent-computer-use:agent\nmodel: default\ndecision-model: jev\nvisual-model: vision\n---\nUse the goal.\n")
            definition = parse_agent_file(path)
            registry = ExtensionRegistry()
            manifest = read_manifest_from_yaml(Path(__file__).parents[1] / "plugin.yaml")
            for extension in manifest.extensions:
                registry.register(manifest.plugin_name, extension)
            config = AppConfig.from_raw_dict({
                "llm": {"default": {"api_key": "unused", "model": "unused", "base_url": "https://offline.invalid/v1"},
                        "vision": {"api_key": "fixture", "model": "vision", "base_url": "https://offline.invalid/v1"}},
                "decision_models": {"jev": {"url": "https://offline.invalid/v1/systemone", "model": "jev-1.14.0", "credential_env": "SPATIAL_TEST_KEY"}},
                "subagents": {"agent-computer-use:agent": {"config": {"selector": "jev-action-vision",
                    "browser": {"scope": "spatial", "url": origin + "/work_items/content/",
                                "observe_bounds": True, "readback_tables": True}}}}})
            runner = AgentRunner(MagicMock(), MagicMock(), Bus(), ToolApprovalPolicy(computer_mode="allow"),
                PendingToolCallStore(), {definition.name: definition}, registry=registry,
                app_config=config, desktop_resource=DesktopResource())
            outputs = [o async for o in runner.run_agent(definition, [], task_id="spatial-product",
                task_input=goal, authorization=SubAgentAuthorization(frozenset({"desktop", "network"})),
                max_actions=6, max_observations=24)]
            result = next(o.metadata["task_result"] for o in outputs if "task_result" in o.metadata)
            assert result["status"] == "completed" and result["reason"] == "goal_verified"
            assert result["cleanup"] == "confirmed" and not result["details"]["pending_effect"]
            assert len(calls) == len(result["details"]["receipts"]) == len(selected_refs) == 1
            assert result["details"]["progress"]["recent_action"]["target_ref"] == selected_refs[0]
            assert product.database_state(database) == before
            assert all(json.loads(line)["method"] == "GET" for line in (tmp_path / "http.jsonl").read_text().splitlines())
        finally:
            if server.returncode is None:
                server.terminate()
            try:
                await asyncio.wait_for(server.wait(), 5)
            except TimeoutError:
                server.kill()
                await server.wait()
