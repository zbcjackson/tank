"""Static scope cases for launcher.py; writes scope-checks.json.

Extracts the launcher's own scope_violations() and evaluates it against fake
desktop states, so the recorded cases describe the shipped file rather than a
re-implementation. Records the launcher sha256 for review.
"""
import ast
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAUNCHER = HERE / "launcher.py"


class FakeAppKit:
    NSApplicationActivationPolicyRegular = 0


class FakeApp:
    def __init__(self, bundle, *, hidden=False, policy=0, pid=100):
        self._bundle = bundle
        self._hidden = hidden
        self._policy = policy
        self._pid = pid

    def bundleIdentifier(self):
        return self._bundle

    def isHidden(self):
        return self._hidden

    def activationPolicy(self):
        return self._policy

    def processIdentifier(self):
        return self._pid


class FakeWindow:
    def __init__(self, number):
        self._number = number

    def windowNumber(self):
        return self._number


class FakeWorkspace:
    def __init__(self, apps):
        self._apps = apps

    def runningApplications(self):
        return self._apps


class FakeQuartz:
    kCGWindowListOptionOnScreenOnly = 0
    kCGNullWindowID = 0

    def __init__(self, on_screen=()):
        self.on_screen = list(on_screen)

    def CGWindowListCopyWindowInfo(self, *_):
        return [{"kCGWindowNumber": number} for number in self.on_screen]


CALCULATOR = FakeApp("com.apple.calculator")
FINDER = FakeApp("com.apple.finder")
HIDDEN_FINDER = FakeApp("com.apple.finder", hidden=True)
OTHER = FakeApp("com.tinyspeck.slackmacgap")
WINDOW = FakeWindow(7)

CASES = [
    # name, apps, on-screen window numbers, expected acceptance
    ("calculator_only", [CALCULATOR], [7], True),
    ("finder_visible", [CALCULATOR, FINDER], [7], False),
    ("finder_hidden", [CALCULATOR, HIDDEN_FINDER], [7], True),
    ("other_visible", [CALCULATOR, OTHER], [7], False),
    ("background_absent", [CALCULATOR], [1], False),
]


def load_scope_violations(quartz):
    tree = ast.parse(LAUNCHER.read_text(encoding="utf-8"))
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "scope_violations"
    )
    namespace = {"AppKit": FakeAppKit, "Quartz": quartz, "os": os}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "<launcher>", "exec"),
         namespace)
    return namespace["scope_violations"]


def main() -> None:
    quartz = FakeQuartz()
    scope_violations = load_scope_violations(quartz)
    cases = []
    for name, apps, on_screen, expected in CASES:
        quartz.on_screen = on_screen
        visible, background_visible = scope_violations(FakeWorkspace(apps), WINDOW)
        accepted = not visible and background_visible
        cases.append({"case": name, "accepted": accepted, "expected": expected})
        assert accepted is expected, f"{name}: accepted={accepted} expected={expected}"
    report = {
        "launcher_sha256": hashlib.sha256(LAUNCHER.read_bytes()).hexdigest(),
        "cases": cases,
    }
    (HERE / "scope-checks.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
