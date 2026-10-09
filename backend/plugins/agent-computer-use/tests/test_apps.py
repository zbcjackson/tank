"""Application resolution uses injectable directory listings, never Spotlight."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass
class FakeInstance:
    pid: int
    start: str
    bundle_id: str


class FakePlatform:
    def __init__(self) -> None:
        self.apps: dict[str, list[FakeInstance]] = {}
        self.window_ids: dict[int, list[int]] = {}
        self.launches: list[Path] = []
        self.activations: list[int] = []
        self.pumps = 0
        self.launch_windows_after = 0

    def running(self, bundle_id: str) -> list[FakeInstance]:
        return list(self.apps.get(bundle_id, []))

    def launch(self, path: Path, bundle_id: str) -> FakeInstance:
        self.launches.append(path)
        instance = FakeInstance(100, "9:0", bundle_id)
        self.apps.setdefault(bundle_id, []).append(instance)
        if self.launch_windows_after == 0:
            self.window_ids[instance.pid] = [11]
        return instance

    def activate(self, pid: int) -> None:
        self.activations.append(pid)

    def windows(self, pid: int) -> list[int]:
        return list(self.window_ids.get(pid, []))

    def pump(self, seconds: float = 0.05) -> None:
        self.pumps += 1
        if self.launch_windows_after and self.pumps >= self.launch_windows_after:
            for pid in list(self.window_ids) + [inst.pid for apps in self.apps.values() for inst in apps]:
                self.window_ids.setdefault(pid, [11])


def test_bind_launches_missing_app_and_reuses_a_single_instance(apps) -> None:
    from agent_computer_use.channels.apps import AppProfile, bind_application

    roots = apps["roots"]
    platform = FakePlatform()
    profile = AppProfile()
    launched = bind_application(
        "Calculator", scope="calc", roots=roots, platform=platform, profile=profile)
    assert launched.launched is True
    assert launched.binding.bundle_id == "com.apple.calculator"
    assert launched.config.pid == 100 and launched.config.window_id == 11
    assert platform.launches and not platform.activations

    platform = FakePlatform()
    platform.apps["com.apple.calculator"] = [FakeInstance(42, "1:0", "com.apple.calculator")]
    platform.window_ids[42] = [7]
    reused = bind_application(
        "com.apple.calculator", scope="calc", roots=roots, platform=platform, profile=profile)
    assert reused.launched is False
    assert reused.config.pid == 42 and reused.config.window_id == 7
    assert platform.activations == [42] and not platform.launches


@pytest.mark.parametrize(("instances", "windows", "reason"), [
    ([FakeInstance(1, "1:0", "com.apple.calculator"),
      FakeInstance(2, "2:0", "com.apple.calculator")], [7], "instance_ambiguous"),
    ([FakeInstance(1, "1:0", "com.apple.calculator")], [7, 8], "window_ambiguous"),
    ([FakeInstance(1, "1:0", "com.apple.calculator")], [], "window_unavailable"),
])
def test_bind_requires_a_unique_running_instance_and_window(
    apps, instances, windows, reason,
) -> None:
    from agent_computer_use.channels.apps import AppProfile, bind_application

    platform = FakePlatform()
    platform.apps["com.apple.calculator"] = instances
    for instance in instances:
        platform.window_ids[instance.pid] = list(windows)
    with pytest.raises(TargetUnavailable, match=reason):
        bind_application("Calculator", scope="calc", roots=apps["roots"],
                         platform=platform, profile=AppProfile())


def test_bind_waits_for_the_first_window_after_launch(apps) -> None:
    from agent_computer_use.channels.apps import AppProfile, bind_application

    platform = FakePlatform()
    platform.launch_windows_after = 3
    result = bind_application(
        "Calculator", scope="calc", roots=apps["roots"], platform=platform, profile=AppProfile())
    assert result.launched and result.config.window_id == 11
    assert platform.pumps >= 3


def test_bind_applies_profile_readouts_to_completion_keys(apps) -> None:
    from agent_computer_use.channels.apps import AppProfile, bind_application
    from agent_computer_use.channels.native import Readout

    platform = FakePlatform()
    profile = AppProfile(readouts=(Readout(name="result", role="AXStaticText"),))
    result = bind_application(
        "Calculator", scope="task", roots=apps["roots"], platform=platform, profile=profile)
    assert result.binding.completion_keys == frozenset({"ax:value:result"})
    assert result.config.readouts[0].name == "result"
