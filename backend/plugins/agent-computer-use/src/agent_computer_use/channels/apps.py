"""Resolve installed macOS applications by bundle id or display name."""

from __future__ import annotations

import plistlib
from dataclasses import dataclass
from pathlib import Path

from ..contracts import TargetUnavailable

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
