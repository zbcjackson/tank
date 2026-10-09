"""Resolve and bind installed macOS applications by bundle id or display name."""

from __future__ import annotations

import plistlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tank_backend.agents.subagent import SubAgentStopped

from ..contracts import TargetBinding, TargetUnavailable
from .native import NativeConfig, Readout

DENIED_BUNDLES = frozenset({
    "com.apple.Terminal",
    "com.googlecode.iterm2",
    "com.apple.systempreferences",
    "com.apple.keychainaccess",
    "com.apple.Passwords",
    "com.apple.ActivityMonitor",
    "com.apple.ScriptEditor2",
    "com.apple.Automator",
    "com.apple.shortcuts",
})

DEFAULT_ROOTS = (
    Path("/Applications"),
    Path("/Applications/Utilities"),
    Path("/System/Applications"),
    Path("/System/Applications/Utilities"),
    Path("/System/Library/CoreServices/Applications"),
    Path.home() / "Applications",
)


@dataclass(frozen=True)
class ApplicationRef:
    bundle_id: str
    path: Path


def _read_plist(path: Path) -> dict[object, object]:
    with path.open("rb") as stream:
        data = plistlib.load(stream)
    return data if isinstance(data, dict) else {}


def _names(info: dict[object, object], resources: Path) -> set[str]:
    names = {value for key in ("CFBundleName", "CFBundleDisplayName")
             if isinstance(value := info.get(key), str) and value}
    loctable = resources / "InfoPlist.loctable"
    if loctable.is_file():
        locales = _read_plist(loctable)
        for locale in locales.values():
            if not isinstance(locale, dict):
                continue
            for key in ("CFBundleName", "CFBundleDisplayName"):
                value = locale.get(key)
                if isinstance(value, str) and value:
                    names.add(value)
    for directory in resources.glob("*.lproj"):
        strings = directory / "InfoPlist.strings"
        if not strings.is_file():
            continue
        try:
            localized = _read_plist(strings)
        except Exception:
            continue
        for key in ("CFBundleName", "CFBundleDisplayName"):
            value = localized.get(key)
            if isinstance(value, str) and value:
                names.add(value)
    return names


def _apps(roots: tuple[Path, ...]) -> list[tuple[ApplicationRef, set[str]]]:
    found: list[tuple[ApplicationRef, set[str]]] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for app in sorted(root.glob("*.app")):
            resolved = app.resolve()
            if resolved in seen:
                continue
            info_path = app / "Contents" / "Info.plist"
            if not info_path.is_file():
                continue
            try:
                info = _read_plist(info_path)
            except Exception:
                continue
            bundle_id = info.get("CFBundleIdentifier")
            if not isinstance(bundle_id, str) or not bundle_id:
                continue
            seen.add(resolved)
            found.append((ApplicationRef(bundle_id, app),
                          _names(info, app / "Contents" / "Resources")))
    return found


def resolve_application(
    application: str,
    *,
    roots: tuple[Path, ...] = DEFAULT_ROOTS,
    denied_bundles: frozenset[str] = frozenset(),
) -> ApplicationRef:
    query = application.strip()
    if not query:
        raise TargetUnavailable("application_not_found")
    denied = DENIED_BUNDLES | denied_bundles
    if query in denied:
        raise TargetUnavailable("application_denied")
    apps = _apps(roots)
    by_bundle = [ref for ref, _ in apps if ref.bundle_id == query]
    if by_bundle:
        matches = by_bundle
    else:
        needle = query.casefold()
        matches = [ref for ref, names in apps
                   if any(name.casefold() == needle for name in names)]
    if not matches:
        raise TargetUnavailable("application_not_found")
    unique = {ref.bundle_id: ref for ref in matches}
    if len(unique) != 1:
        raise TargetUnavailable("application_ambiguous")
    ref = next(iter(unique.values()))
    if ref.bundle_id in denied:
        raise TargetUnavailable("application_denied")
    return ref


class AppProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    dispatch: Literal["ax_press", "quartz"] = "ax_press"
    labels: Literal["accessible_name", "identifier"] = "accessible_name"
    blocked_identifiers: tuple[str, ...] = Field(default=(), max_length=32)
    blocked_labels: tuple[str, ...] = Field(default=(), max_length=32)
    readouts: tuple[Readout, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def unique_readouts(self) -> AppProfile:
        if len({r.name for r in self.readouts}) != len(self.readouts):
            raise ValueError("Readout names must be unique")
        if self.readouts and all(r.allow_empty for r in self.readouts):
            raise ValueError("At least one readout must require native evidence")
        return self


class MacOSPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    denied_bundles: tuple[str, ...] = Field(default=(), max_length=64)
    profiles: dict[str, AppProfile] = Field(default_factory=dict)


@dataclass(frozen=True)
class RunningInstance:
    pid: int
    start: str
    bundle_id: str


class AppPlatform(Protocol):
    def running(self, bundle_id: str) -> list[RunningInstance]: ...
    def launch(self, path: Path, bundle_id: str) -> RunningInstance: ...
    def activate(self, pid: int) -> None: ...
    def windows(self, pid: int) -> list[int]: ...
    def pump(self, seconds: float = 0.05) -> None: ...


@dataclass(frozen=True)
class BoundApplication:
    launched: bool
    binding: TargetBinding
    config: NativeConfig


class SystemPlatform:
    """NSWorkspace / Quartz adapter; tests inject a fake platform instead."""

    def running(self, bundle_id: str) -> list[RunningInstance]:
        import AppKit

        from .native import process_identity

        apps = AppKit.NSWorkspace.sharedWorkspace().runningApplications()
        found: list[RunningInstance] = []
        for app in apps:
            if app.bundleIdentifier() != bundle_id or app.activationPolicy() != 0:
                continue
            pid = int(app.processIdentifier())
            identity = process_identity(pid)
            if identity.bundle_id != bundle_id:
                continue
            found.append(RunningInstance(pid, identity.start, bundle_id))
        return found

    def launch(self, path: Path, bundle_id: str) -> RunningInstance:
        import AppKit
        import Foundation

        from .native import process_identity

        workspace = AppKit.NSWorkspace.sharedWorkspace()
        configuration = AppKit.NSWorkspaceOpenConfiguration.configuration()
        configuration.setCreatesNewApplicationInstance_(False)
        configuration.setActivates_(True)
        completed: list[tuple[object, object]] = []

        def launched(app: object, error: object) -> None:
            completed.append((app, error))

        workspace.openApplicationAtURL_configuration_completionHandler_(
            Foundation.NSURL.fileURLWithPath_(str(path)), configuration, launched)
        for _ in range(200):
            self.pump()
            if completed:
                break
        app, _error = completed[0] if completed else (None, None)
        if app is None:
            raise SubAgentStopped("launch_unconfirmed")
        pid = int(app.processIdentifier())  # type: ignore[attr-defined]
        identity = process_identity(pid)
        if identity.bundle_id != bundle_id:
            raise SubAgentStopped("launch_unconfirmed")
        return RunningInstance(pid, identity.start, bundle_id)

    def activate(self, pid: int) -> None:
        import AppKit

        app = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        if app is None:
            raise SubAgentStopped("instance_unavailable")
        app.activateWithOptions_(0)

    def windows(self, pid: int) -> list[int]:
        from tank_backend.tools import computer_use_macos as macos

        quartz = macos._load_quartz()
        windows = quartz.CGWindowListCopyWindowInfo(quartz.kCGWindowListOptionOnScreenOnly, 0) or []
        return [int(item["kCGWindowNumber"]) for item in windows
                if item.get("kCGWindowOwnerPID") == pid and item.get("kCGWindowLayer") == 0]

    def pump(self, seconds: float = 0.05) -> None:
        import Foundation

        Foundation.NSRunLoop.currentRunLoop().runUntilDate_(
            Foundation.NSDate.dateWithTimeIntervalSinceNow_(seconds))


def _wait_for_window(platform: AppPlatform, pid: int, *, waits: int = 200) -> int:
    for _ in range(waits):
        windows = platform.windows(pid)
        if len(windows) == 1:
            return windows[0]
        if len(windows) > 1:
            raise TargetUnavailable("window_ambiguous")
        platform.pump()
    raise TargetUnavailable("window_unavailable")


def bind_application(
    application: str,
    *,
    scope: str,
    platform: AppPlatform,
    profile: AppProfile | None = None,
    profiles: dict[str, AppProfile] | None = None,
    roots: tuple[Path, ...] = DEFAULT_ROOTS,
    denied_bundles: frozenset[str] = frozenset(),
) -> BoundApplication:
    ref = resolve_application(application, roots=roots, denied_bundles=denied_bundles)
    profile = profile or (profiles or {}).get(ref.bundle_id) or AppProfile()
    running = platform.running(ref.bundle_id)
    launched = False
    if len(running) > 1:
        raise TargetUnavailable("instance_ambiguous")
    if not running:
        instance = platform.launch(ref.path, ref.bundle_id)
        launched = True
        window_id = _wait_for_window(platform, instance.pid)
    else:
        instance = running[0]
        platform.activate(instance.pid)
        windows = platform.windows(instance.pid)
        if not windows:
            raise TargetUnavailable("window_unavailable")
        if len(windows) > 1:
            raise TargetUnavailable("window_ambiguous")
        window_id = windows[0]
    config = NativeConfig(
        scope=scope, bundle_id=ref.bundle_id, pid=instance.pid,
        process_start=instance.start, window_id=window_id,
        dispatch=profile.dispatch, labels=profile.labels,
        blocked_identifiers=profile.blocked_identifiers,
        blocked_labels=profile.blocked_labels, readouts=profile.readouts,
    )
    return BoundApplication(
        launched,
        TargetBinding(ref.bundle_id, launched, frozenset(r.key for r in profile.readouts)),
        config,
    )
