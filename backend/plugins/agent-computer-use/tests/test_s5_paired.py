"""S5 paired pilot harness tests: three arms, one schedule, shared accounting."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from tank_backend.tools.computer_ax import AXElementRef

from .test_native import world as shared_world  # noqa: F401 — fixture registration


def _bootstrap(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s5_paired

    return s5_paired


def test_freeze_pins_three_arm_schedule_and_budget(monkeypatch, tmp_path):
    s5 = _bootstrap(monkeypatch)
    frozen = s5.prepare(tmp_path / "pilot")
    assert frozen["revision"] == "s5-paired-1"
    assert len(frozen["tasks"]) == 9
    assert len(frozen["schedule"]) == 27
    # First-mover rotation balances across arms: each arm leads three blocks.
    leads: dict[str, int] = {}
    for index, entry in enumerate(frozen["schedule"]):
        if index % 3 == 0:
            leads[entry["arm"]] = leads.get(entry["arm"], 0) + 1
        assert entry in frozen["schedule"]
    assert leads == {"A": 3, "H": 3, "J": 3}
    assert {entry["arm"] for entry in frozen["schedule"]} == {"A", "H", "J"}
    # Arm configs differ only in the selector; the J arm keeps the same advisor.
    assert frozen["arm_configs"]["H"]["selector"] == "llm"
    assert frozen["arm_configs"]["J"]["selector"] == "jev-fallback"
    for arm in ("H", "J"):
        assert frozen["arm_configs"][arm]["advisor"] == "llm"
        assert frozen["arm_configs"][arm]["intake"] == "llm"
    assert frozen["a_config"]["agent"] == "computer_use"
    assert frozen["a_config"]["input_cleanup"] is True
    assert frozen["models"]["a"]["model"] == frozen["models"]["qwen"]["model"]
    assert frozen["nano_usd_limit"] == 2_000_000_000
    assert frozen["decision_rule"]["kind"] == "descriptive_pilot"
    assert any(
        path.endswith("agents/computer_use.md") for path in frozen["source_sha256"]
    )
    # Every prompt is shared verbatim across arms; targets pin the owned app.
    for task in frozen["tasks"]:
        assert frozen["prompts"][task["id"]]
        assert frozen["task_inputs"][task["id"]]["target"]["application"].startswith(
            "com.apple."
        )
    assert s5.load_freeze(tmp_path / "pilot", frozen["sha256"]) == frozen
    with pytest.raises(ValueError, match="freeze"):
        s5.load_freeze(tmp_path / "pilot", "wrong")


def test_score_case_is_independent_of_model_claims(monkeypatch):
    s5 = _bootstrap(monkeypatch)
    assert s5.score_case("calculator", {"expression": "7×8", "result": "56"}) == (
        True,
        False,
        False,
    )
    strict, partial, violation = s5.score_case(
        "calculator", {"expression": "7×8", "result": "0"}
    )
    assert not strict and partial and not violation
    strict, partial, violation = s5.score_case(
        "calculator", {"expression": "56", "result": "56"}
    )
    assert not strict and not partial and violation
    body = s5.TEXTEDIT_BODY
    assert s5.score_case("textedit", {"document": body}) == (True, False, False)
    strict, partial, violation = s5.score_case("textedit", {"document": "keep " + body})
    assert not strict and partial and not violation
    assert s5.score_case("textedit", {"document": "别的"}) == (False, False, False)


def test_conclusion_stays_descriptive_without_adoption(monkeypatch):
    s5 = _bootstrap(monkeypatch)
    summary = {arm_name: {"strict": 9} for arm_name in s5.ARMS}
    assert s5.conclusion(summary, completed=False) == "incomplete_no_pilot_conclusion"
    verdict = s5.conclusion(summary, completed=True)
    assert verdict == "pilot_descriptive_only_needs_confirmatory_freeze"


def _install_fake_calculator(monkeypatch, s5, world):
    """Fake AX Calculator world, owned-application seam and cleanup, as test_native."""
    from unittest.mock import Mock

    from agent_computer_use.channels.native import NativeConfig
    from tank_backend.benchmarks.desktop_cleanup import MacOSInputCleanup
    from tank_backend.tools import computer_use_macos

    # The A arm drives production tools; offline tests must never touch the host.
    for boundary in ("_capture_screenshot_macos", "_click_macos", "_load_quartz"):
        monkeypatch.setattr(
            computer_use_macos,
            boundary,
            Mock(side_effect=AssertionError("host access forbidden")),
        )

    world.buttons = [
        replace(
            world.button,
            title=label,
            identifier=label,
            element=AXElementRef(object(), False, 80),
        )
        for label in ("7", "Multiply", "8", "Equals")
    ]
    expression = {"text": ""}
    expression_element = AXElementRef(object(), False, 80)

    def press(ref):
        label = next(button.title for button in world.buttons if button.element == ref)
        world.sent.append(label)
        world.value = {"7": "7", "Multiply": "7", "8": "8", "Equals": "56"}[label]
        expression["text"] = {"7": "", "Multiply": "7×", "8": "7×", "Equals": "7×8"}[
            label
        ]

    def read(*args, **kwargs):
        return [
            *world.buttons,
            replace(world.output, value=world.value),
            replace(
                world.output,
                index=3,
                title="Expression",
                identifier="expression",
                value=expression["text"],
                element=expression_element,
                ancestor_identifiers=("expression-region",),
            ),
        ], False

    monkeypatch.setattr("agent_computer_use.channels.native.ax_press", press)
    monkeypatch.setattr("agent_computer_use.observation.ax_window_candidates", read)

    def start(owner):
        # Fresh owned instance per trial: reset the shared fake world, as the
        # production owner does by launching a clean app and pressing All Clear.
        world.value = "0"
        world.sent.clear()
        expression["text"] = ""
        config = {
            "scope": owner.task["id"],
            "bundle_id": "test.counter",
            "pid": 42,
            "process_start": "1:0",
            "window_id": 7,
            "dispatch": owner.task["dispatch"],
            "labels": "accessible_name",
            "readouts": [
                {"name": "result", "role": "AXStaticText", "identifier": "result"},
                {
                    "name": "expression",
                    "role": "AXStaticText",
                    "ancestor_identifier": "expression-region",
                    "aggregation": "compact_text",
                    "allow_empty": True,
                },
            ],
        }
        return NativeConfig.model_validate_json(json.dumps(config))

    monkeypatch.setattr(s5.OwnedApplication, "start", start)
    monkeypatch.setattr(
        s5.OwnedApplication,
        "read_values",
        lambda self: {"expression": expression["text"], "result": world.value},
    )
    monkeypatch.setattr(s5.OwnedApplication, "close", lambda self: {"confirmed": True})
    monkeypatch.setattr(MacOSInputCleanup, "_state", staticmethod(lambda: ([], [])))
    monkeypatch.setattr(MacOSInputCleanup, "_release", lambda self: {"errors": []})
    profile = {
        "dispatch": "ax_press",
        "labels": "accessible_name",
        "readouts": [
            {"name": "result", "role": "AXStaticText", "identifier": "result"},
            {
                "name": "expression",
                "role": "AXStaticText",
                "ancestor_identifier": "expression-region",
                "aggregation": "compact_text",
                "allow_empty": True,
            },
        ],
    }
    monkeypatch.setattr(
        s5,
        "channel_policy",
        lambda task: {
            "profiles": {"test.counter": {**profile, "dispatch": task["dispatch"]}}
        },
    )
    monkeypatch.setattr(
        s5, "task_input", lambda task: {"target": {"application": "test.counter"}}
    )


async def test_fake_pilot_runs_three_arms_on_one_ledger(request, monkeypatch, tmp_path):
    world = request.getfixturevalue("shared_world")
    s5 = _bootstrap(monkeypatch)
    monkeypatch.setattr(s5, "TASKS", (s5.TASKS[0],))
    _install_fake_calculator(monkeypatch, s5, world)
    output = tmp_path / "pilot"
    frozen = s5.prepare(output)
    report = await s5.run_batch(output, frozen["sha256"], mode="fake")
    assert report["mode"] == "fake"
    rows = report["rows"]
    assert [row["arm"] for row in rows] == ["A", "H", "J"]
    for row in rows:
        assert row["status"] == "finished", row
        assert row["application_cleanup"]["confirmed"]
    assert rows[0]["independent_values"] == {"expression": "", "result": "0"}
    for row in rows[1:]:
        assert row["independent_values"] == {"expression": "7×8", "result": "56"}
    # The fake A arm answers one SSE turn and takes no desktop action, so its
    # strict score fails while the row stays settled and the batch continues.
    assert rows[0]["arm"] == "A"
    assert rows[0]["driver"]["llm_calls"] == 1
    assert rows[0]["strict"] is False
    assert rows[1]["arm"] == "H"
    assert rows[2]["arm"] == "J"
    assert rows[1]["strict"] and rows[2]["strict"]
    h_calls = [call for call in rows[1]["calls"].values()]
    j_calls = [call for call in rows[2]["calls"].values()]
    assert h_calls and all(call["provider"] != "jev" for call in h_calls)
    assert any(call["provider"] == "jev" for call in j_calls)
    assert report["spend"]["batch"]["admitted_requests"] >= 3
    assert report["summary"]["A"]["planned"] == 1
    assert report["summary"]["H"]["strict"] == 1
    assert report["summary"]["J"]["strict"] == 1
    assert report["paired"] and report["paired"][0]["task_id"] == rows[0]["task_id"]
    assert report["conclusion"] == "pilot_descriptive_only_needs_confirmatory_freeze"
    assert (output / "rows.jsonl").exists()
    with pytest.raises(FileExistsError):
        await s5.run_batch(output, frozen["sha256"], mode="fake")


async def test_operational_failure_stops_and_keeps_full_denominator(
    request, monkeypatch, tmp_path
):
    world = request.getfixturevalue("shared_world")
    s5 = _bootstrap(monkeypatch)
    monkeypatch.setattr(s5, "TASKS", (s5.TASKS[0],))
    _install_fake_calculator(monkeypatch, s5, world)
    original = s5.OwnedApplication.read_values

    def unknown_effect(self):
        original(self)
        raise RuntimeError("independent readback failed")

    monkeypatch.setattr(s5.OwnedApplication, "read_values", unknown_effect)
    output = tmp_path / "pilot"
    frozen = s5.prepare(output)
    report = await s5.run_batch(output, frozen["sha256"], mode="fake")
    assert not report["completed"]
    journal = [
        json.loads(line) for line in (output / "rows.jsonl").read_text().splitlines()
    ]
    assert len(journal) == 3
    assert journal[0]["status"] == "error"
    assert {row["status"] for row in journal[1:]} == {"not_run"}
    assert report["conclusion"] == "incomplete_no_pilot_conclusion"
