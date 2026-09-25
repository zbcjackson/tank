"""Static cases for the controlled-window gate in launcher.py.

Extracts the launcher's own gate_decision() and evaluates it, so the recorded
cases describe the shipped file rather than a re-implementation. Records the
launcher sha256 for review.
"""
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAUNCHER = HERE / "launcher.py"

WINDOW = (600, 100, 1274, 508)  # measured Calculator window in the controlled frame

SCREEN = (1920, 1080)

CASES = [
    # name, point, container, protocol, expected ("pass" | "block" | "corrected")
    ("center_of_target", (1101, 310), WINDOW, "pixels", "pass"),
    ("on_window_edge", (600, 100), WINDOW, "pixels", "pass"),
    # A plain overshoot must never be moved: 1275 or 1290 cannot be a 0..1000 value.
    ("just_outside_right", (1275, 310), WINDOW, "pixels", "block"),
    ("pixel_overshoot_right", (1290, 314), WINDOW, "pixels", "block"),
    ("just_outside_below", (1101, 509), WINDOW, "pixels", "block"),
    # Unit confusion: the point cannot be a pixel value for this window and reads
    # as the "7" button when treated as normalized (1035, 310).
    ("normalized_in_pixel_field", (539, 287), WINDOW, "pixels", "corrected"),
    ("normalized_in_pixel_field_2", (573, 241), WINDOW, "pixels", "corrected"),
    # Same numbers under a normalized contract are a legitimate miss: no correction.
    ("normalized_contract_miss", (539, 287), WINDOW, None, "block"),
    ("normalized_contract_miss_legacy", (539, 287), WINDOW, "point", "block"),
    ("toolbar_of_another_app", (300, 900), WINDOW, "pixels", "corrected" ) if False else
    ("toolbar_of_another_app", (300, 900), WINDOW, "pixels", "block"),
    ("target_window_missing", (1101, 310), None, "pixels", "block"),
]


def load_gate():
    tree = ast.parse(LAUNCHER.read_text(encoding="utf-8"))
    wanted = {"gate_decision", "disambiguate_unit", "inside"}
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in wanted]
    namespace: dict[str, object] = {"LAST_PROTOCOL": {"value": None},
                                    "display_size": lambda: SCREEN}
    exec(compile(ast.Module(body=functions, type_ignores=[]), "<launcher>", "exec"),
         namespace)
    return namespace


def main() -> None:
    namespace = load_gate()
    gate_decision = namespace["gate_decision"]
    cases = []
    for name, point, container, protocol, expected in CASES:
        namespace["LAST_PROTOCOL"]["value"] = protocol
        verdict = gate_decision(point, container)
        if verdict is None:
            outcome, detail = "pass", None
        else:
            outcome = "corrected" if verdict[0] == "use" else "block"
            detail = list(verdict[1]) if verdict[0] == "use" else str(verdict[1])[:80]
        cases.append({"case": name, "point": list(point), "protocol": protocol,
                      "container": list(container) if container else None,
                      "outcome": outcome, "expected": expected, "detail": detail})
        assert outcome == expected, f"{name}: {outcome} != {expected} ({detail})"
        if outcome == "corrected":
            left, top, right, bottom = container
            x, y = verdict[1]
            assert left <= x <= right and top <= y <= bottom, f"{name}: correction off target"
        if outcome == "block":
            assert "observe again" in verdict[1], f"{name}: no recovery hint"
    report = {"launcher_sha256": hashlib.sha256(LAUNCHER.read_bytes()).hexdigest(),
              "screen": list(SCREEN), "cases": cases}
    (HERE / "gate-checks.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
