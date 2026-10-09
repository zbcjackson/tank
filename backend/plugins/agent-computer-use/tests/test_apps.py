"""Application resolution uses injectable directory listings, never Spotlight."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_computer_use.contracts import TargetUnavailable


def write_app(
    root: Path,
    name: str,
    *,
    bundle_id: str,
    display_name: str | None = None,
    bundle_name: str | None = None,
    locales: dict[str, dict[str, str]] | None = None,
) -> Path:
    import plistlib

    app = root / f"{name}.app"
    contents = app / "Contents"
    resources = contents / "Resources"
    resources.mkdir(parents=True)
    info = {
        "CFBundleIdentifier": bundle_id,
        "CFBundleName": bundle_name or name,
        "CFBundleDisplayName": display_name or name,
    }
    with (contents / "Info.plist").open("wb") as stream:
        plistlib.dump(info, stream)
    if locales:
        with (resources / "InfoPlist.loctable").open("wb") as stream:
            plistlib.dump(locales, stream)
    return app


@pytest.fixture
def apps(tmp_path: Path) -> dict[str, Path]:
    applications = tmp_path / "Applications"
    system = tmp_path / "System" / "Applications"
    utilities = system / "Utilities"
    home = tmp_path / "Home" / "Applications"
    for directory in (applications, system, utilities, home):
        directory.mkdir(parents=True)
    write_app(system, "Calculator", bundle_id="com.apple.calculator",
              locales={"zh_CN": {"CFBundleDisplayName": "计算器", "CFBundleName": "计算器"},
                       "ja": {"CFBundleDisplayName": "計算機", "CFBundleName": "計算機"}})
    write_app(system, "TextEdit", bundle_id="com.apple.TextEdit")
    write_app(utilities, "Terminal", bundle_id="com.apple.Terminal")
    write_app(applications, "Notes", bundle_id="com.apple.Notes")
    write_app(home, "Drafts", bundle_id="com.example.Drafts", display_name="Draft Box")
    write_app(applications, "Alpha", bundle_id="com.example.Alpha", display_name="Shared")
    write_app(home, "Beta", bundle_id="com.example.Beta", display_name="Shared")
    return {
        "roots": (applications, system, utilities, home),
        "tmp": tmp_path,
    }


def test_resolve_accepts_bundle_id_and_case_insensitive_display_names(apps) -> None:
    from agent_computer_use.channels.apps import resolve_application

    roots = apps["roots"]
    assert resolve_application("com.apple.calculator", roots=roots).bundle_id == (
        "com.apple.calculator")
    assert resolve_application("calculator", roots=roots).bundle_id == "com.apple.calculator"
    assert resolve_application("计算器", roots=roots).bundle_id == "com.apple.calculator"
    assert resolve_application("DRAFT BOX", roots=roots).bundle_id == "com.example.Drafts"


def test_resolve_rejects_missing_ambiguous_and_denied_apps(apps) -> None:
    from agent_computer_use.channels.apps import DENIED_BUNDLES, resolve_application

    roots = apps["roots"]
    with pytest.raises(TargetUnavailable, match="application_not_found"):
        resolve_application("Missing", roots=roots)
    with pytest.raises(TargetUnavailable, match="application_ambiguous"):
        resolve_application("Shared", roots=roots)
    assert "com.apple.Terminal" in DENIED_BUNDLES
    with pytest.raises(TargetUnavailable, match="application_denied"):
        resolve_application("Terminal", roots=roots)
    with pytest.raises(TargetUnavailable, match="application_denied"):
        resolve_application("com.apple.Terminal", roots=roots)


def test_resolve_denylist_can_only_grow(apps) -> None:
    from agent_computer_use.channels.apps import DENIED_BUNDLES, resolve_application

    roots = apps["roots"]
    denied = frozenset({"com.apple.Notes"})
    with pytest.raises(TargetUnavailable, match="application_denied"):
        resolve_application("Notes", roots=roots, denied_bundles=denied)
    # Built-in entries remain even if the caller omits them.
    assert DENIED_BUNDLES <= (DENIED_BUNDLES | denied)
    with pytest.raises(TargetUnavailable, match="application_denied"):
        resolve_application("com.apple.Terminal", roots=roots, denied_bundles=frozenset())
    # Bundle ids on the denylist are refused even when the app is not installed here.
    with pytest.raises(TargetUnavailable, match="application_denied"):
        resolve_application("com.apple.keychainaccess", roots=roots)
