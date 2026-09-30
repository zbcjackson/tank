"""One task-owned Chromium page; native objects never enter domain messages."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tank_backend.agents.subagent import SubAgentContext, SubAgentStopped

from ..contracts import Action, Binding, DispatchReceipt, Element, Fact, Snapshot

if TYPE_CHECKING:
    from playwright.async_api import Browser, Frame, Locator, Page, Playwright, Route


class BrowserConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    scope: str = Field(min_length=1, max_length=256)
    url: str = Field(max_length=4096)
    frame_name: str | None = Field(default=None, min_length=1, max_length=256)

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


class DOMView(BaseModel):
    elements: list[DOMElement]
    complete: bool
    revision: int


# The selector registry stores actual DOM objects, not text/index selectors that
# silently resolve to a replacement node after re-render. Both scripts run in the
# same frame's main world. This is identity bookkeeping, not a page-code sandbox.
_ENGINE = r"""({
    query(root, selector) { return this.queryAll(root, selector)[0] || null; },
    queryAll(root, selector) {
        const key = NAMESPACE;
        if (!globalThis[key]) {
            const state = {ids: new WeakMap(), refs: new Map(), next: 0, revision: 0};
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
    let complete = nodes.length <= 4096;
    const elements = [];
    const text = value => (value || '').replace(/\s+/g, ' ').trim();
    for (const node of nodes.slice(0, 4096)) {
        if (node.shadowRoot) complete = false;
        const tag = node.tagName.toLowerCase();
        const role = node.getAttribute('role') || ({button: 'button', textarea: 'textbox',
            input: ['button', 'submit', 'reset'].includes(node.type) ? 'button' :
                ['text', 'search', 'email', 'url', 'tel', 'password'].includes(node.type) ?
                'textbox' : '', a: node.hasAttribute('href') ? 'link' : '',
            output: 'status'}[tag] || '');
        if (!role) continue;
        const style = getComputedStyle(node);
        if (!node.getClientRects().length || style.visibility === 'hidden' ||
            node.closest('[aria-hidden="true"], [hidden], [inert]')) continue;
        const labelled = (node.getAttribute('aria-labelledby') || '').split(/\s+/)
            .map(id => document.getElementById(id)?.textContent || '').join(' ');
        const label = text(labelled || node.getAttribute('aria-label') ||
            [...(node.labels || [])].map(e => e.textContent).join(' ') ||
            (tag === 'input' && role === 'button' ? node.value : node.textContent));
        const value = role === 'textbox' ? node.value ?? node.textContent : node.textContent;
        if (label.length > 512 || (value || '').length > 4096 || role.length > 128)
            complete = false;
        if (!state.ids.has(node)) state.ids.set(node, PREFIX + (++state.next));
        const ref = state.ids.get(node);
        state.refs.set(ref, node);
        elements.push({ref, role: role.slice(0, 128), label: label.slice(0, 512),
            value: (value || '').slice(0, 4096),
            enabled: !node.matches(':disabled') && node.getAttribute('aria-disabled') !== 'true',
            editable: role === 'textbox' && !node.readOnly &&
                (tag === 'input' || tag === 'textarea' || node.isContentEditable),
            focused: document.activeElement === node});
        if (elements.length >= 256) { complete = false; break; }
    }
    return {elements, complete, revision: state.revision};
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
                  .replace("PREFIX", json.dumps(self.namespace)))
        data = await frame.locator(f"{self.engine}=*").evaluate_all(script)
        self.check(context)
        return DOMView.model_validate(data)

    async def observe(self, scope: str, context: SubAgentContext) -> Snapshot:
        self.check(context)
        if scope != self.config.scope:
            raise SubAgentStopped("scope_mismatch")
        await self.start(context)
        frame = self.bound_frame()
        navigation = self.navigation
        view = await self.read(frame, context)
        if navigation != self.navigation:
            raise SubAgentStopped("navigation_changed")
        elements = []
        for item in view.elements:
            actions: tuple[Literal["click", "fill"], ...] = ()
            if item.role in {"button", "link"}:
                actions = ("click",)
            elif item.editable:
                actions = ("fill",)
            elements.append(Element(item.ref, item.role, item.label, actions, item.enabled,
                                    "control" if actions else "text_region", "dom",
                                    item.value, item.focused))
        keys = Counter(f"{item.role}:{item.label}" for item in view.elements)
        facts = tuple(Fact(key=key, value=item.value) for item in view.elements
                      if item.label and len(key := f"{item.role}:{item.label}") <= 128
                      and keys[key] == 1)
        self.generation += 1
        snapshot = Snapshot(uuid4().hex, scope, self.generation, tuple(elements), facts,
                            complete=view.complete)
        self.previous, self.view = snapshot, view
        self.observed_navigation = navigation
        return snapshot

    async def is_current(
        self, binding: Binding, action: Action, context: SubAgentContext,
    ) -> bool:
        self.check(context)
        snapshot = self.previous
        if (snapshot is None or not snapshot.complete
                or (binding.scope, binding.observation_id, binding.generation) !=
                (snapshot.scope, snapshot.observation_id, snapshot.generation)
                or self.observed_navigation != self.navigation):
            return False
        element = next((item for item in snapshot.elements if item.ref == action.target_ref), None)
        if (element is None or not element.enabled or action.operation not in element.actions
                or (action.operation == "fill") != (action.value is not None)):
            return False
        frame = self.bound_frame()
        current = await self.read(frame, context)
        return current == self.view and self.navigation == self.observed_navigation

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
        if not await self.is_current(binding, action, context):
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
