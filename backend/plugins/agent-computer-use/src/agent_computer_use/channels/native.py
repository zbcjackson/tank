"""Explicitly bound macOS AX channel; native objects never enter model messages."""

from __future__ import annotations

import asyncio
import ctypes
import plistlib
import re
import time
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tank_backend.agents.subagent import SubAgentContext, SubAgentStopped
from tank_backend.tools.computer_ax import AXCandidate, ax_focused_pid, ax_press, ax_set_value
from tank_backend.tools.computer_native import run_native
from tank_backend.tools import computer_use_macos as macos

from .. import observation
from ..contracts import (
    Action, Binding, DispatchReceipt, Element, Fact, Snapshot, Target, TargetBinding, ValueChange,
)

if TYPE_CHECKING:
    from .apps import AppPlatform, MacOSPolicy


class Readout(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    role: str = Field(min_length=1, max_length=128)
    identifier: str | None = Field(default=None, min_length=1, max_length=128)
    label: str | None = Field(default=None, min_length=1, max_length=512)
    ancestor_identifier: str | None = Field(default=None, min_length=1, max_length=128)
    aggregation: Literal["single", "compact_text"] = "single"
    allow_empty: bool = False

    @model_validator(mode="after")
    def validate_aggregation(self) -> Readout:
        if self.aggregation == "compact_text" and self.role != "AXStaticText":
            raise ValueError("Display aggregation requires read-only AXStaticText")
        if self.allow_empty and (self.aggregation != "compact_text" or not self.ancestor_identifier):
            raise ValueError("Empty readout requires an explicit display region")
        return self

    @property
    def key(self) -> str:
        return "ax:value:" + self.name

    def matches(self, item: AXCandidate) -> bool:
        return (item.role == self.role
                and (self.identifier is None or self.identifier == item.identifier)
                and (self.ancestor_identifier is None
                     or self.ancestor_identifier in item.ancestor_identifiers)
                and (self.label is None or self.label in (item.title, item.description)))


class NativeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    scope: str = Field(min_length=1, max_length=256)
    bundle_id: str = Field(min_length=1, max_length=256)
    pid: int = Field(gt=0)
    process_start: str = Field(pattern=r"^[0-9]+:[0-9]+$", max_length=40)
    window_id: int = Field(gt=0)
    dispatch: Literal["ax_press", "quartz"] = "ax_press"
    labels: Literal["accessible_name", "identifier"] = "accessible_name"
    blocked_identifiers: tuple[str, ...] = Field(default=(), max_length=32)
    blocked_labels: tuple[str, ...] = Field(default=(), max_length=32)
    # Labels containing these terms lose click but keep fill (e.g. "Sender" fields).
    blocked_terms: tuple[str, ...] = Field(default=(), max_length=128)
    readouts: tuple[Readout, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def unique_readouts(self) -> NativeConfig:
        if len({r.name for r in self.readouts}) != len(self.readouts):
            raise ValueError("Readout names must be unique")
        if self.readouts and all(r.allow_empty for r in self.readouts):
            raise ValueError("At least one readout must require native evidence")
        return self


def names_term(label: str, terms: tuple[str, ...]) -> bool:
    """Whole-word match for ASCII terms, substring match for CJK terms."""
    # Identifier fallback labels are camelCase ("deleteButton", "AXDeleteButton"); split their words first.
    text = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", label).casefold().replace("\u2019", "'")
    for term in terms:
        term = term.casefold().replace("\u2019", "'")
        if term.isascii():
            if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text):
                return True
        elif term in text:
            return True
    return False


@dataclass(frozen=True)
class NativeWindow:
    pid: int
    process_start: str
    bundle_id: str
    window_id: int
    bounds: tuple[int, int, int, int]
    display_geometry: tuple[int, ...]


class ProcessInfo(ctypes.Structure):
    # Darwin sys/proc_info.h: struct proc_bsdinfo (PROC_PIDTBSDINFO, flavor 3).
    _fields_ = [(name, ctypes.c_uint32) for name in (
        "flags", "status", "xstatus", "pid", "ppid", "uid", "gid", "ruid", "rgid",
        "svuid", "svgid", "reserved",
    )] + [("comm", ctypes.c_char * 16), ("name", ctypes.c_char * 32)] + [
        (name, ctypes.c_uint32) for name in ("nfiles", "pgid", "pjobc", "tdev", "tpgid")
    ] + [("nice", ctypes.c_int32), ("started_seconds", ctypes.c_uint64),
         ("started_microseconds", ctypes.c_uint64)]


@dataclass(frozen=True)
class ProcessIdentity:
    start: str
    bundle_id: str


def process_identity(pid: int) -> ProcessIdentity:
    """Kernel birth time and executable bundle, with no NSRunningApplication cache."""
    library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    library.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                                    ctypes.c_void_p, ctypes.c_int]
    library.proc_pidinfo.restype = ctypes.c_int
    library.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    library.proc_pidpath.restype = ctypes.c_int

    def birth() -> str:
        info = ProcessInfo()
        if (library.proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info)) != ctypes.sizeof(info)
                or info.pid != pid):
            raise SubAgentStopped("process_unavailable")
        return f"{info.started_seconds}:{info.started_microseconds}"

    start = birth()
    path = ctypes.create_string_buffer(4096)
    if library.proc_pidpath(pid, path, len(path)) <= 0:
        raise SubAgentStopped("process_path_unavailable")
    executable = Path(path.value.decode("utf-8"))
    bundle = next((parent for parent in executable.parents if parent.suffix == ".app"), None)
    if bundle is None:
        raise SubAgentStopped("process_bundle_unavailable")
    with (bundle / "Contents/Info.plist").open("rb") as stream:
        identifier = plistlib.load(stream).get("CFBundleIdentifier")
    if not isinstance(identifier, str) or birth() != start:
        raise SubAgentStopped("process_changed")
    return ProcessIdentity(start, identifier)


def frontmost_window_id(pid: int) -> int | None:
    """On-screen layer-0 window ordered first for this process, if any."""
    quartz = macos._load_quartz()
    windows = [w for w in (quartz.CGWindowListCopyWindowInfo(
        quartz.kCGWindowListOptionOnScreenOnly, 0) or [])
        if w.get("kCGWindowOwnerPID") == pid and w.get("kCGWindowLayer") == 0]
    return int(windows[0]["kCGWindowNumber"]) if windows else None


def read_window(config: NativeConfig) -> NativeWindow:
    """Read OS identity and geometry; never launch, activate or attach by window title."""
    identity = process_identity(config.pid)
    if identity != ProcessIdentity(config.process_start, config.bundle_id):
        raise SubAgentStopped("process_changed")
    quartz = macos._load_quartz()
    windows = quartz.CGWindowListCopyWindowInfo(quartz.kCGWindowListOptionOnScreenOnly, 0) or []
    found = [w for w in windows if w.get("kCGWindowNumber") == config.window_id
             and w.get("kCGWindowOwnerPID") == config.pid and w.get("kCGWindowLayer") == 0]
    if len(found) != 1:
        raise SubAgentStopped("window_unavailable")
    app_windows = [w for w in windows if w.get("kCGWindowOwnerPID") == config.pid
                   and w.get("kCGWindowLayer") == 0]
    if (ax_focused_pid() != config.pid
            or not app_windows or app_windows[0].get("kCGWindowNumber") != config.window_id):
        raise SubAgentStopped("foreground_changed")
    rect = found[0]["kCGWindowBounds"]
    bounds = tuple(int(rect[k]) for k in ("X", "Y", "Width", "Height"))
    x, y, width, height = bounds
    geometry = macos._main_geometry(macos._active_displays())
    if not (0 <= x < x + width <= geometry[3] and 0 <= y < y + height <= geometry[4]):
        raise SubAgentStopped("unsupported_display")
    return NativeWindow(config.pid, config.process_start, config.bundle_id, config.window_id,
                        (x, y, width, height), geometry)


def pointer_target_is_exposed(window: NativeWindow, x: int, y: int) -> bool:
    quartz = macos._load_quartz()
    width, height = window.display_geometry[3], window.display_geometry[4]
    for item in quartz.CGWindowListCopyWindowInfo(quartz.kCGWindowListOptionOnScreenOnly, 0) or []:
        rect = item.get("kCGWindowBounds", {})
        covers_screen = (
            item.get("kCGWindowLayer", 0) != 0
            and rect.get("Width", 0) >= width
            and rect.get("Height", 0) >= height
        )
        if (item.get("kCGWindowAlpha", 1) > 0
                and not covers_screen
                and rect.get("X", 0) <= x < rect.get("X", 0) + rect.get("Width", 0)
                and rect.get("Y", 0) <= y < rect.get("Y", 0) + rect.get("Height", 0)):
            return item.get("kCGWindowNumber") == window.window_id
    return False


def inputs_idle() -> bool:
    quartz = macos._load_quartz()
    state = quartz.kCGEventSourceStateCombinedSessionState
    return not (any(quartz.CGEventSourceKeyState(state, key) for key in range(128))
                or any(quartz.CGEventSourceButtonState(state, button) for button in range(32)))


def release_uncertain_pointer() -> None:
    """Cleanup only the left button this channel may have left down."""
    quartz = macos._load_quartz()
    state = quartz.kCGEventSourceStateCombinedSessionState
    if quartz.CGEventSourceButtonState(state, 0):
        macos._mouse_button_macos("left", False)
        time.sleep(0.1)
    if quartz.CGEventSourceButtonState(state, 0):
        raise RuntimeError("Native pointer cleanup unconfirmed")


class NativeAXChannel:
    """Resolve a request target, then borrow that process/window for the task."""

    def __init__(
        self,
        policy: MacOSPolicy | None = None,
        *,
        platform: AppPlatform | None = None,
        roots: tuple[Path, ...] | None = None,
        config: NativeConfig | None = None,
    ) -> None:
        from .apps import DEFAULT_ROOTS, MacOSPolicy, SystemPlatform

        self.policy = policy if policy is not None else MacOSPolicy()
        self.platform = platform if platform is not None else SystemPlatform()
        self.roots = roots if roots is not None else DEFAULT_ROOTS
        self.config: NativeConfig | None = None
        self.completion_keys: frozenset[str] = frozenset()
        self.closed = False
        self.task_id: str | None = None
        self.window: NativeWindow | None = None
        self.source: observation.AXObservationSource | None = None
        self.previous: Snapshot | None = None
        self.lock = asyncio.Lock()
        self.readout_refs: dict[str, str] = {}
        self.pointer_uncertain = False
        self.launched = False
        if config is not None:
            self.apply_config(config)

    def apply_config(self, config: NativeConfig, *, launched: bool = False) -> None:
        self.config = config
        self.completion_keys = frozenset(r.key for r in config.readouts)
        self.readout_refs = {r.name: uuid4().hex for r in config.readouts}
        self.launched = launched
        self.window = None
        self.source = None
        self.previous = None

    async def bind(self, target: Target, scope: str, context: SubAgentContext) -> TargetBinding:
        from .apps import bind_application

        async with self.lock:
            self.check(context)
            if self.config is not None:
                raise SubAgentStopped("already_bound")

            def run() -> TargetBinding:
                bound = bind_application(
                    target.application, scope=scope, platform=self.platform,
                    profiles=dict(self.policy.profiles), roots=self.roots,
                    denied_bundles=frozenset(self.policy.denied_bundles),
                    blocked_terms=self.policy.blocked_terms,
                )
                self.apply_config(bound.config, launched=bound.launched)
                return bound.binding

            return await run_native(run)

    def check(self, context: SubAgentContext) -> None:
        context.check("desktop")
        context.runtime.check_open()
        if self.closed:
            raise SubAgentStopped("channel_closed")
        if self.task_id not in (None, context.runtime.task_id):
            raise SubAgentStopped("task_mismatch")

    def bound_window(self, context: SubAgentContext, *, follow: bool = False) -> NativeWindow:
        self.check(context)
        if self.config is None:
            raise SubAgentStopped("unbound_channel")
        try:
            window = read_window(self.config)
        except SubAgentStopped as exc:
            # Same-process frontmost may change while the old window is still listed
            # (foreground_changed) or already gone from the screen (window_unavailable).
            if not follow or exc.reason not in ("foreground_changed", "window_unavailable"):
                raise
            window = self.follow_window(context)
        self.check(context)
        return window

    def follow_window(self, context: SubAgentContext) -> NativeWindow:
        """Rebind to the same process's new frontmost window; never follow another app."""
        self.check(context)
        config = self.config
        if config is None:
            raise SubAgentStopped("unbound_channel")
        if ax_focused_pid() != config.pid:
            raise SubAgentStopped("foreground_changed")
        if process_identity(config.pid) != ProcessIdentity(config.process_start, config.bundle_id):
            raise SubAgentStopped("process_changed")
        new_id = frontmost_window_id(config.pid)
        if new_id is None or new_id == config.window_id:
            raise SubAgentStopped("foreground_changed")
        self.config = config.model_copy(update={"window_id": new_id})
        if self.source is not None:
            self.source.window_id = new_id
            self.source.targets.clear()
        self.window = None
        return read_window(self.config)

    async def observe(self, scope: str, context: SubAgentContext) -> Snapshot:
        async with self.lock:
            self.check(context)
            if self.config is None:
                raise SubAgentStopped("unbound_channel")
            if scope != self.config.scope:
                raise SubAgentStopped("scope_mismatch")
            self.task_id = context.runtime.task_id
            window = await run_native(lambda: self.bound_window(context, follow=True))
            self.check(context)
            if self.window and self.window.display_geometry != window.display_geometry:
                raise SubAgentStopped("display_changed")
            if self.source is None:
                self.source = observation.AXObservationSource(
                    window.window_id, window.display_geometry, scope,
                    use_identifiers=self.config.labels == "identifier")
            elif self.source.window_id != window.window_id:
                self.source.window_id = window.window_id
                if len(window.display_geometry) != 7:
                    raise SubAgentStopped("unsupported_display")
                self.source.display_geometry = cast(
                    tuple[int, int, int, int, int, int, int], window.display_geometry)
                self.source.targets.clear()
            snapshot = await self.source.observe(scope, context)
            self.check(context)
            if await run_native(self.bound_window, context) != window:
                raise SubAgentStopped("window_changed")
            self.check(context)
            facts, changes, regions = [], [], []
            complete = snapshot.complete
            for readout in self.config.readouts:
                matches = [(ref, item) for ref, item in self.source.targets if readout.matches(item)]
                if ((not matches and not readout.allow_empty)
                        or readout.aggregation == "single" and len(matches) != 1):
                    complete = False
                    continue
                if readout.aggregation == "single":
                    ref, item = matches[0]
                    value = item.value
                else:
                    if any(item.frame is None for _, item in matches):
                        complete = False
                        continue
                    ordered = sorted(matches, key=lambda pair: (pair[1].frame[1], pair[1].frame[0])
                                     if pair[1].frame is not None else (0, 0))
                    # Compact mathematical display text; single/document values remain exact.
                    value = "".join(c for _, item in ordered for c in item.value
                                    if not c.isspace() and unicodedata.category(c) != "Cf")
                    ref = self.readout_refs[readout.name]
                    if len(value) > 4096:
                        complete = False
                        continue
                    regions.append(Element(ref, "readout", readout.name, (), kind="text_region",
                                           source="ax", value=value))
                facts.append(Fact(key=readout.key, value=value))
                changes.append(ValueChange(readout.key, ref, value))
            targets = dict(self.source.targets)
            blocked = {e.ref for e in snapshot.elements
                       if not e.label or e.label in self.config.blocked_labels
                       or targets[e.ref].identifier in self.config.blocked_identifiers}
            clickable = {e.ref for e in snapshot.elements if "click" in e.actions and e.ref not in blocked
                         and not names_term(e.label, self.config.blocked_terms)}
            elements = tuple(replace(
                e, click_changes=tuple(changes) if e.ref in clickable else (),
                # Unverifiable clicks are offered only under danger-term filtering.
                click_observable=e.ref in clickable and not changes and bool(self.config.blocked_terms),
                actions=() if e.ref in blocked else tuple(
                    a for a in e.actions if a != "click" or e.ref in clickable),
                enabled=(True if "fill" in e.actions and targets[e.ref].enabled is None
                         and targets[e.ref].value_settable else e.enabled),
            ) for e in snapshot.elements) + tuple(regions)
            self.previous = replace(snapshot, elements=elements, facts=tuple(facts), complete=complete)
            self.window = window
            return self.previous

    def current(self, binding: Binding, action: Action, context: SubAgentContext) -> AXCandidate | None:
        self.check(context)
        snapshot, source, window, config = self.previous, self.source, self.window, self.config
        if (config is None or snapshot is None or source is None or window is None
                or not snapshot.complete
                or (binding.observation_id, binding.generation, binding.scope) !=
                (snapshot.observation_id, snapshot.generation, snapshot.scope)
                or read_window(config) != window):
            return None
        selected = next((e for e in snapshot.elements if e.ref == action.target_ref), None)
        if (selected is None or not selected.enabled or action.operation not in selected.actions
                or (action.operation == "fill") != (action.value is not None)):
            return None
        candidates, incomplete = source.scan()
        if incomplete:
            return None
        unique: list[AXCandidate] = []
        for item in candidates:
            if not any(item.element.native == other.element.native for other in unique):
                unique.append(item)
        if len(unique) != len(source.targets):
            return None
        target = None
        for ref, old in source.targets:
            fresh = next((item for item in unique if item.element.native == old.element.native), None)
            if fresh is None or replace(fresh, index=old.index) != old:
                return None
            if ref == action.target_ref:
                target = fresh
        self.check(context)
        return target

    async def is_current(self, binding: Binding, action: Action, context: SubAgentContext) -> bool:
        async with self.lock:
            return await run_native(self.current, binding, action, context) is not None

    async def dispatch(
        self, binding: Binding, action: Action, context: SubAgentContext,
    ) -> DispatchReceipt:
        def send() -> DispatchReceipt:
            try:
                config = self.config
                target = self.current(binding, action, context)
                window = self.window
                if config is None or target is None or window is None or target.frame is None:
                    return DispatchReceipt(action.id, "not_sent", "stale_reference")
                x, y, width, height = target.frame
                wx, wy, ww, wh = window.bounds
                if not (wx <= x < x + width <= wx + ww and wy <= y < y + height <= wy + wh):
                    return DispatchReceipt(action.id, "not_sent", "target_outside_window")
                point = (x + width // 2, y + height // 2)
                if (action.operation == "click" and config.dispatch == "quartz"
                        and not pointer_target_is_exposed(window, *point)):
                    return DispatchReceipt(action.id, "not_sent", "target_occluded")
                if self.bound_window(context) != window:
                    return DispatchReceipt(action.id, "not_sent", "window_changed")
                if not inputs_idle():
                    return DispatchReceipt(action.id, "not_sent", "user_input_active")
                self.check(context)
            except SubAgentStopped as exc:
                return DispatchReceipt(action.id, "not_sent", exc.reason)
            try:
                if action.operation == "fill":
                    assert action.value is not None
                    ax_set_value(target.element, action.value)
                elif config.dispatch == "ax_press":
                    ax_press(target.element)
                else:
                    self.pointer_uncertain = True
                    macos._click_macos(*point, clear_modifiers=True)
                    self.pointer_uncertain = False
            except (RuntimeError, OSError):
                return DispatchReceipt(action.id, "unknown", "native_action_failed")
            return DispatchReceipt(action.id, "sent")

        async with self.lock:
            return await run_native(send)

    async def aclose(self) -> None:
        self.closed = True
        async with self.lock:
            if self.source is not None:
                await self.source.aclose()
            if self.pointer_uncertain:
                await run_native(release_uncertain_pointer)
                self.pointer_uncertain = False
            self.previous = None
