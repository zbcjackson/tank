"""One task-owned Chromium page; native objects never enter domain messages."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from hashlib import sha256
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tank_backend.agents.subagent import SubAgentContext, SubAgentStopped

from ..contracts import Action, Binding, DispatchReceipt, Element, Fact, Snapshot

DOM_TABLE_PREFIX = "status:DOM table:"


def dom_table_fact(
    url: str, columns: tuple[str, ...], rows: tuple[tuple[str, ...], ...],
) -> Fact:
    """Exact public results on one page, not evidence about unobserved storage."""
    BrowserConfig.validate_url(url)
    if (not 1 <= len(columns) <= 32 or len(set(columns)) != len(columns)
            or any(not column.strip() for column in columns) or len(rows) > 64
            or any(len(row) != len(columns) for row in rows)):
        raise ValueError("A bounded table with unique named columns is required")
    return Fact(
        key=DOM_TABLE_PREFIX + json.dumps(columns, ensure_ascii=False, separators=(",", ":")),
        value=json.dumps({"url": url, "columns": columns, "rows": rows},
                         ensure_ascii=False, separators=(",", ":")),
    )

if TYPE_CHECKING:
    from playwright.async_api import Browser, Frame, Locator, Page, Playwright, Route
    from ..visual_selector import VisualFrame


class BrowserConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    scope: str = Field(min_length=1, max_length=256)
    url: str = Field(max_length=4096)
    frame_name: str | None = Field(default=None, min_length=1, max_length=256)
    readback_tables: bool = False

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if (parts.scheme not in {"http", "https"} or not parts.hostname
                or parts.username is not None):
            raise ValueError("Browser requires an explicit HTTP(S) URL without credentials")
        _ = parts.port
        return value


class DOMElement(BaseModel):
    ref: str
    role: str
    label: str
    value: str
    enabled: bool
    editable: bool
    focused: bool
    ancestors: tuple[tuple[str, str], ...] = ()
    click_effect: tuple[Fact, ...] = ()
    submits: bool = False
    input_type: str = "text"
    control_name: str = ""


class DOMView(BaseModel):
    elements: list[DOMElement]
    complete: bool
    revision: int
    tables: tuple[Fact, ...] = ()


# The selector registry stores actual DOM objects, not text/index selectors that
# silently resolve to a replacement node after re-render. Both scripts run in the
# same frame's main world. This is identity bookkeeping, not a page-code sandbox.
_ENGINE = r"""({
    query(root, selector) { return this.queryAll(root, selector)[0] || null; },
    queryAll(root, selector) {
        const key = NAMESPACE;
        if (!globalThis[key]) {
            const documentId = [...crypto.getRandomValues(new Uint32Array(4))].join('-');
            const state = {ids: new WeakMap(), refs: new Map(), next: 0, revision: 0, documentId};
            new MutationObserver(() => state.revision++).observe(document,
                {subtree: true, childList: true, attributes: true, characterData: true});
            globalThis[key] = state;
        }
        if (selector === '*') return [...root.querySelectorAll('*')];
        const node = globalThis[key].refs.get(selector);
        return node && node.isConnected && root.contains(node) ? [node] : [];
    }
})"""

_READ = r"""nodes => {
    const state = globalThis[NAMESPACE];
    state.refs.clear();
    let complete = nodes.length <= 4096 && document.readyState !== 'loading' &&
        document.documentElement?.getAttribute('aria-busy') !== 'true';
    const elements = [];
    const text = value => (value || '').replace(/\s+/g, ' ').trim();
    const name = node => text((node.getAttribute('aria-labelledby') || '').split(/\s+/)
            .map(id => document.getElementById(id)?.textContent || '').join(' ') ||
        node.getAttribute('aria-label'));
    const regions = nodes.filter(n => n.matches('form, dialog, [role="region"], [role="dialog"]') && name(n));
    for (const node of nodes.slice(0, 4096)) {
        if (node.shadowRoot) complete = false;
        const tag = node.tagName.toLowerCase();
        const role = node.getAttribute('role') || ({button: 'button', textarea: 'textbox',
            input: ['button', 'submit', 'reset'].includes(node.type) ? 'button' :
                node.type === 'checkbox' ? 'checkbox' :
                ['text', 'search', 'email', 'url', 'tel', 'password'].includes(node.type) ?
                'textbox' : '', a: node.hasAttribute('href') ? 'link' : '',
            output: 'status', form: name(node) ? 'region' : '', dialog: 'dialog'}[tag] || '');
        if (!role) continue;
        const style = getComputedStyle(node);
        if (!node.getClientRects().length || style.visibility === 'hidden' ||
            node.closest('[aria-hidden="true"], [hidden], [inert]')) continue;
        const labelled = (node.getAttribute('aria-labelledby') || '').split(/\s+/)
            .map(id => document.getElementById(id)?.textContent || '').join(' ');
        const label = text(labelled || node.getAttribute('aria-label') ||
            [...(node.labels || [])].map(e => e.textContent).join(' ') ||
            (tag === 'input' && role === 'button' ? node.value : node.innerText ?? node.textContent));
        const value = tag === 'input' && node.type === 'checkbox' ? String(node.checked) :
            role === 'textbox' ? node.value ?? node.textContent : node.innerText ?? node.textContent;
        const ancestors = [];
        for (let parent = node.parentElement; parent; parent = parent.parentElement) {
            if (name(parent)) ancestors.push([parent.tagName.toLowerCase(), name(parent)]);
            else if (parent.matches('tr') && parent.closest('table')) {
                const rowText = text(parent.innerText);
                if (rowText) ancestors.push(['row', rowText]);
            }
        }
        if (ancestors.length > 8 || ancestors.some(a => a[1].length > 256)) complete = false;
        const controlled = (node.getAttribute('aria-controls') || '').trim();
        const target = controlled && document.getElementById(controlled);
        const targetName = target && name(target);
        const targetRole = target && (target.getAttribute('role') ||
            (target.tagName.toLowerCase() === 'dialog' ? 'dialog' : 'region'));
        let click_effect = targetName && targetName.length <= 113 &&
            ['region', 'dialog'].includes(targetRole) &&
            regions.filter(r => name(r) === targetName).length === 1 && regions.includes(target) ?
            [{key: 'visible:' + targetRole + ':' + targetName, value: 'true'}] : [];
        if (!click_effect.length && tag === 'a' && node.hasAttribute('href') &&
            !node.hasAttribute('download') && !document.querySelector('base[target]') &&
            ['', '_self'].includes((node.target || '').toLowerCase())) {
            let destination;
            try { destination = new URL(node.href, location.href); } catch (_) {}
            if (destination && destination.origin === location.origin &&
                ['http:', 'https:'].includes(destination.protocol) &&
                destination.href !== location.href && destination.href.length <= 4096)
                click_effect = [{key: 'status:Page URL', value: destination.href}];
        }
        if (label.length > 512 || (value || '').length > 4096 || role.length > 128)
            complete = false;
        if (!state.ids.has(node))
            state.ids.set(node, PREFIX + state.documentId + ':' + (++state.next));
        const ref = state.ids.get(node);
        state.refs.set(ref, node);
        elements.push({ref, role: role.slice(0, 128), label: label.slice(0, 512),
            value: (value || '').slice(0, 4096),
            enabled: !node.matches(':disabled') && node.getAttribute('aria-disabled') !== 'true',
            editable: role === 'textbox' && !node.readOnly &&
                (tag === 'input' || tag === 'textarea' || node.isContentEditable),
            focused: document.activeElement === node,
            ancestors: ancestors.slice(0, 8).map(a => [a[0], a[1].slice(0, 256)]), click_effect,
            submits: !!node.form && node.type === 'submit',
            input_type: tag === 'input' ? node.type : 'text',
            control_name: tag === 'input' && node.type === 'checkbox' && node.name.length <= 128 ? node.name : ''});
        if (elements.length >= 256) { complete = false; break; }
    }
    const tables = [];
    const signatures = [];
    const visible = node => {
        if (!node.getClientRects().length || getComputedStyle(node).visibility !== 'visible' ||
            node.closest('[aria-hidden="true"], [hidden], [inert]')) return false;
        for (let parent = node; parent; parent = parent.parentElement)
            if (getComputedStyle(parent).opacity === '0') return false;
        return true;
    };
    const editing = elements.some(e => e.editable && e.enabled && state.refs.get(e.ref).closest('form'));
    if (TABLE_READBACK && complete && !editing) for (const table of nodes.filter(n => n.tagName === 'TABLE')) {
        if (!visible(table) || table.parentElement?.closest('table') || table.querySelector('table') || table.tHead?.rows.length !== 1 ||
            table.tFoot?.rows.length) continue;
        const headers = [...table.tHead.rows[0].cells];
        const named = headers.map((cell, index) => ({cell, index, name: text(cell.innerText)}))
            .filter(h => h.name);
        const columns = named.map(h => h.name);
        const key = 'status:DOM table:' + JSON.stringify(columns);
        signatures.push(key);
        if (!named.length || named.length > 32 ||
            table.closest('[aria-busy="true"]') || table.querySelector('[aria-busy="true"]') ||
            new Set(named.map(h => h.name)).size !== named.length ||
            headers.some(c => !visible(c) || c.colSpan !== 1 || c.rowSpan !== 1 ||
                [...c.querySelectorAll('*')].some(child => !visible(child)))) continue;
        const body = [...table.tBodies].flatMap(section => [...section.rows]);
        if (body.length > 64 || body.some(row => !visible(row) || row.cells.length !== headers.length ||
            [...row.cells].some(c => c.colSpan !== 1 || c.rowSpan !== 1))) continue;
        const cells = body.flatMap(row => named.map(h => row.cells[h.index]));
        if (cells.some(c => c.colSpan !== 1 || c.rowSpan !== 1 || !visible(c) ||
            c.querySelector('input,textarea,select,button,[contenteditable]:not([contenteditable="false"]),[role="textbox"]') ||
            [...c.querySelectorAll('*')].some(child => !visible(child)))) continue;
        const rows = body.map(row => named.map(h => text(row.cells[h.index].innerText)));
        const value = JSON.stringify({url: location.href, columns, rows});
        if (key.length <= 128 && value.length <= 4096) tables.push({key, value});
    }
    return {elements, complete, revision: state.revision,
        tables: tables.filter(t => signatures.filter(key => key === t.key).length === 1)};
}"""


# Constructable stylesheets avoid the attribute mutations performed by
# Playwright's temporary caret="hide" styling. DOM revisions stay meaningful.
_HIDE_CARET = r"""namespace => {
    const state = globalThis[namespace];
    if (!state.caretSheet) {
        state.caretSheet = new CSSStyleSheet();
        state.caretSheet.replaceSync('input,textarea,[contenteditable] {caret-color: transparent !important}');
    }
    if (!document.adoptedStyleSheets.includes(state.caretSheet))
        document.adoptedStyleSheets = [...document.adoptedStyleSheets, state.caretSheet];
}"""


_SETTLE = """async () => {
            const hiddenPaint = animation => {
                const effect = animation.effect;
                if (!(animation instanceof CSSAnimation) || !(effect instanceof KeyframeEffect) ||
                    !(effect.target instanceof Element) ||
                    !['::before', '::after'].includes(effect.pseudoElement)) return false;
                const style = getComputedStyle(effect.target, effect.pseudoElement);
                // Empty generated content has no text/marker descendants that can override visibility.
                if (style.visibility !== 'hidden' || style.content !== '\"\"' ||
                    style.display.includes('list-item')) return false;
                const frames = effect.getKeyframes();
                const allowed = ['offset', 'computedOffset', 'easing', 'composite', 'transform', 'opacity'];
                if (!frames.some(f => 'transform' in f || 'opacity' in f) ||
                    !frames.every(f => Object.keys(f).every(k => allowed.includes(k)))) return false;
                // Chromium omits custom properties from getKeyframes(); also inspect CSS definitions.
                const properties = [];
                let remaining = 4096;
                const scan = rules => {
                    for (const rule of rules) {
                        if (--remaining < 0) throw new Error('css_rule_limit');
                        if (rule instanceof CSSKeyframesRule) {
                            if (rule.name !== animation.animationName) continue;
                            for (const keyframe of rule.cssRules) {
                                if (--remaining < 0) throw new Error('css_rule_limit');
                                properties.push(...keyframe.style);
                            }
                        } else if (rule instanceof CSSImportRule) scan(rule.styleSheet.cssRules);
                        else if (rule.cssRules) scan(rule.cssRules);
                    }
                };
                try {
                    for (const sheet of [...document.styleSheets, ...document.adoptedStyleSheets])
                        scan(sheet.cssRules);
                } catch (_) { return false; }
                return properties.length > 0 && properties.every(p => ['transform', 'opacity'].includes(p));
            };
            const active = () => document.getAnimations().filter(a =>
                (a.pending || a.playState === 'running') && !hiddenPaint(a));
            const animations = active();
            if (!animations.length) return true;
            let timer;
            await Promise.race([
                Promise.all(animations.map(a => a.finished.catch(() => {}))),
                new Promise(resolve => { timer = setTimeout(resolve, 250); })
            ]);
            clearTimeout(timer);
            return active().length === 0;
        }"""


class ManagedChromiumChannel:
    """Lazy isolated browser; constructed only from trusted host configuration.

    Navigation and resources are confined to the configured origin. A named frame
    must be unique; otherwise the main frame is used only on frame-free pages.
    Page facts are unique `role:label` values, never model completion assertions.
    """

    def __init__(self, config: BrowserConfig) -> None:
        self.config = config
        self.closed = False
        self.task_id: str | None = None
        self.playwright: Playwright | None = None
        self.starting: asyncio.Task[Playwright] | None = None
        self.browser: Browser | None = None
        self.page: Page | None = None
        self.frame: Frame | None = None
        self.navigation = 0
        self.generation = 0
        self.previous: Snapshot | None = None
        self.view: DOMView | None = None
        self.observed_navigation = -1
        self.namespace = "__tank_dom_" + uuid4().hex
        self.engine = "tank" + uuid4().hex
        self.closing: asyncio.Task[None] | None = None
        self.resource_lock = asyncio.Lock()
        self.visual_frame: VisualFrame | None = None

    def check(self, context: SubAgentContext) -> None:
        context.check("desktop")
        context.check("network")
        if self.closed:
            raise SubAgentStopped("channel_closed")
        if self.task_id not in (None, context.runtime.task_id):
            raise SubAgentStopped("task_mismatch")

    async def start(self, context: SubAgentContext) -> None:
        self.check(context)
        if self.page is not None:
            return
        self.task_id = context.runtime.task_id
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise SubAgentStopped("browser_dependency_unavailable") from None
        try:
            async with self.resource_lock:
                self.check(context)
                self.starting = asyncio.create_task(async_playwright().start())
                playwright = await asyncio.shield(self.starting)
                self.playwright = playwright
            self.check(context)
            await playwright.selectors.register(
                self.engine, _ENGINE.replace("NAMESPACE", json.dumps(self.namespace)),
                content_script=False,
            )
            self.check(context)
            self.browser = await playwright.chromium.launch(headless=True)
            self.check(context)
            browser_context = await self.browser.new_context(
                accept_downloads=False, service_workers="block",
            )
            self.check(context)
            browser_context.set_default_timeout(500)

            async def route(request: Route) -> None:
                try:
                    self.check(context)
                    parts, allowed = urlsplit(request.request.url), urlsplit(self.config.url)
                    if ((parts.scheme, parts.netloc) != (allowed.scheme, allowed.netloc)
                            or request.request.frame.page is not self.page):
                        await request.abort()
                    else:
                        await request.continue_()
                except (SubAgentStopped, asyncio.CancelledError, TimeoutError):
                    await request.abort()

            await browser_context.route("**/*", route)
            self.check(context)
            await browser_context.route_web_socket("**/*", lambda socket: socket.close())
            self.check(context)
            self.page = await browser_context.new_page()
            self.page.on("framenavigated", self.navigated)
            self.check(context)
            await self.page.goto(self.config.url, wait_until="load", timeout=5000)
            self.check(context)
        except BaseException:
            await self.aclose()
            raise

    def navigated(self, frame: Frame) -> None:
        self.navigation += 1

    def bound_frame(self) -> Frame:
        if self.browser is None or not self.browser.is_connected() or self.page is None:
            raise SubAgentStopped("browser_disconnected")
        if self.page.is_closed():
            raise SubAgentStopped("page_closed")
        frames = self.page.frames
        if self.config.frame_name is not None:
            frames = [frame for frame in frames if frame.name == self.config.frame_name]
        if len(frames) != 1:
            raise SubAgentStopped("frame_ambiguous")
        frame = frames[0]
        if frame.child_frames:
            raise SubAgentStopped("frame_ambiguous")
        if self.frame is not None and self.frame is not frame:
            raise SubAgentStopped("frame_replaced")
        self.frame = frame
        return frame

    async def read(self, frame: Frame, context: SubAgentContext) -> DOMView:
        self.check(context)
        script = (_READ.replace("NAMESPACE", json.dumps(self.namespace))
                  .replace("PREFIX", json.dumps(self.namespace))
                  .replace("TABLE_READBACK", json.dumps(self.config.readback_tables)))
        data = await frame.locator(f"{self.engine}=*").evaluate_all(script)
        self.check(context)
        return DOMView.model_validate(data)

    def unavailable_snapshot(self, scope: str) -> Snapshot:
        """Discard a read spanning documents; it grants no candidate references."""
        self.generation += 1
        snapshot = Snapshot(uuid4().hex, scope, self.generation, complete=False, ready=False)
        self.previous, self.view = snapshot, None
        self.visual_frame = None
        self.observed_navigation = -1
        return snapshot

    async def is_snapshot_current(self, snapshot: Snapshot, context: SubAgentContext) -> bool:
        """Revalidate DOM after an adapter's asynchronous business readback."""
        self.check(context)
        if snapshot != self.previous or self.observed_navigation != self.navigation:
            return False
        current = await self.read(self.bound_frame(), context)
        return current == self.view and self.observed_navigation == self.navigation

    async def observe(self, scope: str, context: SubAgentContext) -> Snapshot:
        return await self._observe(scope, context, refreshed=False)

    async def _observe(
        self, scope: str, context: SubAgentContext, *, refreshed: bool,
    ) -> Snapshot:
        self.check(context)
        self.visual_frame = None
        if scope != self.config.scope:
            raise SubAgentStopped("scope_mismatch")
        await self.start(context)
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        frame = self.bound_frame()
        # Full and SPA navigation can publish their URL before the DOM settles.
        async def ready() -> bool:
            async with asyncio.timeout(.5):
                await frame.wait_for_load_state("domcontentloaded", timeout=0)
                await frame.wait_for_function(
                    "() => document.documentElement?.getAttribute('aria-busy') !== 'true'",
                    timeout=0,
                )
                return await frame.evaluate(_SETTLE)

        pending = asyncio.create_task(ready())
        try:
            while not pending.done():
                await asyncio.wait({pending}, timeout=.01)
                self.check(context)
            if pending.result() is not True:
                return self.unavailable_snapshot(scope)
        except (PlaywrightTimeoutError, TimeoutError):
            self.check(context)
            return self.unavailable_snapshot(scope)
        finally:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        self.check(context)
        navigation = self.navigation
        view = await self.read(frame, context)
        if (navigation != self.navigation
                or view != await self.read(frame, context)
                or navigation != self.navigation):
            return self.unavailable_snapshot(scope)
        if view.tables and not refreshed:
            # Leaving the document guarantees a fresh GET even for fragment URLs.
            # reload() can resubmit a POST document and must not be used here.
            url = frame.url
            self.check(context)
            await frame.goto("about:blank", wait_until="load", timeout=5000)
            self.check(context)
            await frame.goto(url, wait_until="load", timeout=5000)
            self.check(context)
            return await self._observe(scope, context, refreshed=True)
        elements = []
        checked_facts = []
        keys = Counter(f"{item.role}:{item.label}" for item in view.elements)
        names = Counter(item.control_name for item in view.elements
                        if item.role == "checkbox" and item.input_type == "checkbox"
                        and item.control_name)
        for item in view.elements:
            actions: tuple[Literal["click", "fill"], ...] = ()
            click_effect = item.click_effect
            label = item.label
            if item.role in {"button", "link"}:
                actions = ("click",)
            elif (item.role == "checkbox" and item.input_type == "checkbox"
                  and item.label and len(item.label) <= 119):
                actions = ("click",)
                key = f"checkbox:{item.label}"
                if keys[key] != 1:
                    key = "dom:checked:" + sha256(item.ref.encode()).hexdigest()
                    checked_facts.append(Fact(key=key, value=item.value))
                    if item.control_name and names[item.control_name] == 1:
                        label += f" [name={item.control_name}]"
                click_effect = (Fact(key=key,
                                     value="false" if item.value == "true" else "true"),)
            elif item.editable:
                actions = ("fill",)
            elements.append(Element(item.ref, item.role, label, actions, item.enabled,
                                    "control" if actions else "text_region", "dom",
                                    item.value, item.focused, item.ancestors,
                                    click_effect=click_effect, submits=item.submits,
                                    input_type=item.input_type))
        facts = (Fact(key="status:Page URL", value=frame.url), *checked_facts) + tuple(
                      Fact(key=key, value=item.value) for item in view.elements
                      if item.label and len(key := f"{item.role}:{item.label}") <= 128
                      and key != "status:Page URL" and not key.startswith("dom:checked:")
                      and not key.startswith(DOM_TABLE_PREFIX)
                      and keys[key] == 1)
        facts += tuple(Fact(key=f"visible:{item.role}:{item.label}", value="true")
                       for item in view.elements if item.role in {"region", "dialog"}
                       and item.label and len(f"visible:{item.role}:{item.label}") <= 128
                       and keys[f"{item.role}:{item.label}"] == 1)
        facts += view.tables
        self.generation += 1
        snapshot = Snapshot(uuid4().hex, scope, self.generation, tuple(elements), facts,
                            complete=view.complete)
        self.previous, self.view = snapshot, view
        self.observed_navigation = navigation
        return snapshot

    async def capture(self, snapshot: Snapshot, context: SubAgentContext) -> VisualFrame:
        import io
        from PIL import Image
        from tank_backend.tools.computer_observation import Observation
        from ..visual_selector import VisualFrame

        self.check(context)
        frame = self.bound_frame()
        if (self.page is None or frame is not self.page.main_frame
                or snapshot != self.previous or await self.read(frame, context) != self.view):
            context.observe("computer_use_freshness", channel="dom", stage="capture_precheck",
                            observation_id=snapshot.observation_id)
            raise SubAgentStopped("visual_frame_unavailable")
        settled = await frame.evaluate(_SETTLE)
        self.check(context)
        if not settled:
            context.observe("computer_use_freshness", channel="dom", stage="capture_motion",
                            observation_id=snapshot.observation_id)
            raise SubAgentStopped("unstable_visual_frame")
        bounds = []
        for element in snapshot.elements:
            if not element.actions:
                continue
            rect = await frame.locator(f"{self.engine}={element.ref}").bounding_box()
            if rect is not None:
                bounds.append((element.ref, (rect["x"], rect["y"], rect["width"], rect["height"])))
        png = await self.visual_png()
        self.check(context)
        if (await self.read(frame, context) != self.view
                or self.observed_navigation != self.navigation):
            context.observe("computer_use_freshness", channel="dom", stage="capture_state",
                            observation_id=snapshot.observation_id)
            raise SubAgentStopped("stale_reference")
        with Image.open(io.BytesIO(png)) as image:
            width, height = image.size
        observation, png = Observation.capture(
            png, session_id=context.runtime.task_id, display_id=1,
            display_geometry=(1, 0, 0, width, height, width, height))
        captured = VisualFrame(snapshot.observation_id, observation, png, tuple(bounds))
        self.visual_frame = captured
        return captured

    async def visual_png(self) -> bytes:
        """Hide native carets consistently without changing DOM attributes/revisions."""
        assert self.page is not None
        await self.page.evaluate(_HIDE_CARET, self.namespace)
        return await self.page.screenshot(type="png", scale="css", caret="initial")

    async def is_current(
        self, binding: Binding, action: Action, context: SubAgentContext,
        *, check_image: bool = True,
    ) -> bool:
        self.check(context)
        snapshot = self.previous

        def refused(stage: str, **metadata: str) -> bool:
            context.observe("computer_use_freshness", channel="dom", stage=stage,
                observation_id=snapshot.observation_id if snapshot is not None else None,
                action_id=action.id, **metadata)
            return False

        if (snapshot is None or not snapshot.complete
                or (binding.scope, binding.observation_id, binding.generation) !=
                (snapshot.scope, snapshot.observation_id, snapshot.generation)):
            return refused("binding")
        if self.observed_navigation != self.navigation:
            return refused("navigation")
        element = next((item for item in snapshot.elements if item.ref == action.target_ref), None)
        if (element is None or not element.enabled or action.operation not in element.actions
                or (action.operation == "fill") != (action.value is not None)):
            return refused("selected_action")
        frame = self.bound_frame()
        current = await self.read(frame, context)
        if check_image and self.visual_frame is not None:
            import hashlib

            if self.page is None or self.visual_frame.observation_id != snapshot.observation_id:
                return refused("frame_identity")
            png = await self.visual_png()
            self.check(context)
            current_sha = hashlib.sha256(png).hexdigest()
            if current_sha != self.visual_frame.frame.image_sha256:
                return refused("frame_scene", expected_sha256=self.visual_frame.frame.image_sha256,
                               current_sha256=current_sha)
            current = await self.read(frame, context)
        if current != self.view:
            return refused("dom_state")
        if self.navigation != self.observed_navigation:
            return refused("navigation")
        return True

    def locator(self, action: Action) -> Locator:
        assert self.frame is not None
        return self.frame.locator(f"{self.engine}={action.target_ref}")

    async def dispatch(
        self, binding: Binding, action: Action, context: SubAgentContext,
    ) -> DispatchReceipt:
        from playwright.async_api import Error

        if not await self.is_current(binding, action, context):
            return DispatchReceipt(action.id, "not_sent", "stale_reference")
        locator = self.locator(action)
        try:
            # Even fill must receive pointer events: do not type through overlays.
            await locator.click(trial=True, timeout=250)
        except Error:
            return DispatchReceipt(action.id, "not_sent", "not_actionable")
        # The trial may change :hover pixels. Its existing DOM/navigation check
        # remains mandatory; compare the model's image before the trial above.
        if not await self.is_current(binding, action, context, check_image=False):
            return DispatchReceipt(action.id, "not_sent", "stale_reference")
        self.check(context)
        try:
            if action.operation == "click":
                pending = asyncio.create_task(locator.click(timeout=250))
            else:
                assert action.value is not None
                pending = asyncio.create_task(locator.fill(action.value, timeout=250))
            try:
                while not pending.done():
                    await asyncio.wait({pending}, timeout=0.01)
                    self.check(context)
                pending.result()
            except (asyncio.CancelledError, SubAgentStopped, TimeoutError):
                # Cancelling a Python await alone does not cancel a CDP command.
                # Terminate this owned browser before allowing cleanup to finish.
                await self.aclose()
                raise
            finally:
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
        except Error:
            return DispatchReceipt(action.id, "unknown", "browser_action_failed")
        return DispatchReceipt(action.id, "sent")

    async def aclose(self) -> None:
        if self.closing is None:
            self.closed = True
            self.closing = asyncio.create_task(self.close_resources())
        await asyncio.shield(self.closing)

    async def close_resources(self) -> None:
        self.closed = True
        self.visual_frame = None
        self.previous, self.view = None, None
        async with self.resource_lock:
            if self.starting is not None and self.playwright is None:
                # Cancellation must not abandon a driver before ownership transfers.
                results = await asyncio.gather(self.starting, return_exceptions=True)
                if not isinstance(results[0], BaseException):
                    self.playwright = results[0]
            try:
                if self.browser is not None:
                    await self.browser.close()
            finally:
                if self.playwright is not None:
                    await self.playwright.stop()
