"""S5 paired pilot harness tests: three arms, one schedule, shared accounting."""

import json
import re
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
    assert frozen["revision"] == "s5-confirmatory-1"
    assert len(frozen["tasks"]) == 50
    assert len(frozen["schedule"]) == 150
    families = {task["id"].rsplit("-", 1)[0] for task in frozen["tasks"]}
    assert families == {
        "calculator-ax_press",
        "calculator-quartz",
        "textedit",
        "calculator-long-ax_press",
        "calculator-long-quartz",
    }
    long_tasks = [t for t in frozen["tasks"] if t["id"].startswith("calculator-long-")]
    assert all(t["max_decisions"] == 20 for t in long_tasks)
    assert all(len(s5.button_sequence(t["expression"])) >= 9 for t in long_tasks)
    # First-mover rotation over 5 tasks x 10 repeats: 17/17/16 block leads.
    leads: dict[str, int] = {}
    for index, entry in enumerate(frozen["schedule"]):
        if index % 3 == 0:
            leads[entry["arm"]] = leads.get(entry["arm"], 0) + 1
    assert leads == {"A": 17, "H": 17, "J": 16}
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
    assert frozen["nano_usd_limit"] == 4_000_000_000
    assert frozen["decision_rule"]["kind"] == "confirmatory"
    assert set(frozen["decision_rule"]["hypotheses"]) == {
        "h1_amortization",
        "h2_quality_not_worse",
        "h3_cost_lower",
        "h4_baseline_insufficient",
    }
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
    assert s5.score_case(
        "calculator",
        {"expression": "12×3-8+5", "result": "33"},
        expected=("12×3-8+5", "33"),
    ) == (True, False, False)
    strict, partial, violation = s5.score_case(
        "calculator",
        {"expression": "12×3-8+5", "result": "0"},
        expected=("12×3-8+5", "33"),
    )
    assert not strict and partial and not violation
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


def test_read_values_reactivates_defocused_owned_app(monkeypatch):
    """Arm A may defocus the target; readback re-activates the owned instance."""
    from unittest.mock import Mock

    s5 = _bootstrap(monkeypatch)
    owner = s5.OwnedApplication(s5.TASKS[0])
    owner.pid, owner.app = 42, Mock()
    monkeypatch.setattr(s5.computer_ax, "ax_focused_pid", lambda: 99)
    pumped = []
    monkeypatch.setattr(s5.s4_ax, "pump", lambda seconds=0: pumped.append(seconds))
    values = {"expression": "7×8", "result": "56"}
    monkeypatch.setattr(s5.s4_ax.OwnedApplication, "read_values", lambda self: values)
    assert owner.read_values() == values
    owner.app.activateWithOptions_.assert_called_once_with(0)
    assert pumped == [0.1]


def test_conclusion_stays_descriptive_without_adoption(monkeypatch):
    s5 = _bootstrap(monkeypatch)
    summary = {arm_name: {"strict": 9} for arm_name in s5.ARMS}
    assert s5.conclusion(summary, completed=False) == "incomplete_no_pilot_conclusion"
    verdict = s5.conclusion(summary, completed=True)
    assert verdict == "pilot_descriptive_only_needs_confirmatory_freeze"


def test_button_sequence_derives_deterministic_labels(monkeypatch):
    s5 = _bootstrap(monkeypatch)
    assert s5.button_sequence("7×8") == ("7", "Multiply", "8", "Equals")
    assert s5.button_sequence("12×3-8+5") == (
        "1",
        "2",
        "Multiply",
        "3",
        "Subtract",
        "8",
        "Add",
        "5",
        "Equals",
    )


def test_confirmatory_verdict_applies_predeclared_gates(monkeypatch):
    s5 = _bootstrap(monkeypatch)
    assert s5.confirmatory_verdict({}, completed=False) == {
        "h1": False,
        "h2": False,
        "h3": False,
        "h4": False,
        "decision": "incomplete_no_confirmatory_conclusion",
    }
    base = {"strict": 40, "nano_usd": 100, "elapsed_ms": 100}
    summary = {
        "H": dict(base),
        "J": {**base, "nano_usd": 60},
        "A": {**base, "strict": 5},
        "long_family": {
            "H": {"strict": 20, "elapsed_ms": 1000},
            "J": {"strict": 20, "elapsed_ms": 1050},
            "A": {"strict": 0, "elapsed_ms": 9000, "nano_usd": 0},
        },
    }
    verdict = s5.confirmatory_verdict(summary, completed=True)
    assert verdict["h1"] and verdict["h2"] and verdict["h3"] and verdict["h4"]
    assert verdict["decision"] == "trial_j_for_multidecision_native_scenarios"
    slow = {
        **summary,
        "long_family": {
            "H": {"strict": 20, "elapsed_ms": 1000},
            "J": {"strict": 20, "elapsed_ms": 1300},
            "A": {"strict": 0, "elapsed_ms": 9000, "nano_usd": 0},
        },
    }
    verdict = s5.confirmatory_verdict(slow, completed=True)
    assert not verdict["h1"] and verdict["h2"] and verdict["h3"]
    assert verdict["decision"] == "no_net_gain_keep_jev_explicit_experimental"
    quality_break = {**summary, "J": {**base, "strict": 30, "nano_usd": 60}}
    verdict = s5.confirmatory_verdict(quality_break, completed=True)
    assert verdict["decision"] == "mixed_review_before_any_adoption"


def test_settled_treats_readback_resolved_effect_unknown_as_known_failure(monkeypatch):
    """Trials are isolated: an unknown effect with independent readback and
    confirmed cleanup stays in the denominator instead of stopping the batch."""
    s5 = _bootstrap(monkeypatch)
    row = {
        "status": "finished",
        "arm": "H",
        "application_cleanup": {"confirmed": True},
        "independent_values": {"expression": "78×", "result": "78×"},
        "result": {
            "status": "unknown",
            "reason": "effect_unknown",
            "cleanup": "confirmed",
            "details": {"receipts": [{"status": "sent"}]},
        },
    }
    assert s5.settled(row, None)
    assert not s5.settled({**row, "independent_values": None}, None)
    assert not s5.settled({**row, "status": "error"}, None)
    assert not s5.settled({**row, "application_cleanup": {"confirmed": False}}, None)
    backend_error = {**row, "result": {**row["result"], "reason": "backend_error"}}
    assert not s5.settled(backend_error, None)
    unknown_receipt = {
        **row,
        "result": {**row["result"], "details": {"receipts": [{"status": "unknown"}]}},
    }
    assert not s5.settled(unknown_receipt, None)
    assert not s5.settled(row, "unknown_usage")


def test_settled_arm_a_stops_on_terminal_driver_reasons(monkeypatch):
    """The A arm shares the declared stop policy: cancellation, driver errors,
    request limits, unknown usage and unconfirmed cleanup stop the batch,
    while bounded known failures (timeout, max steps) stay settled."""
    s5 = _bootstrap(monkeypatch)
    row = {
        "status": "finished",
        "arm": "A",
        "application_cleanup": {"confirmed": True},
        "driver": {
            "cleanup": "confirmed",
            "unknown_calls": 0,
            "stop_reason": "max_steps(15) reached",
        },
    }
    assert s5.settled(row, None)
    for stop_reason in ("cancelled", "error", "request_limit"):
        driver = {**row["driver"], "stop_reason": stop_reason}
        assert not s5.settled({**row, "driver": driver}, None), stop_reason
    unknown_usage = {**row["driver"], "unknown_calls": 1}
    assert not s5.settled({**row, "driver": unknown_usage}, None)
    unconfirmed = {**row["driver"], "cleanup": "unconfirmed"}
    assert not s5.settled({**row, "driver": unconfirmed}, None)
    assert not s5.settled({**row, "application_cleanup": {"confirmed": False}}, None)


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
        for label in (
            "7",
            "8",
            "1",
            "2",
            "3",
            "5",
            "Multiply",
            "Add",
            "Subtract",
            "Equals",
        )
    ]
    expression = {"text": ""}
    expression_element = AXElementRef(object(), False, 80)
    symbols = {"Multiply": "×", "Add": "+", "Subtract": "-"}

    def evaluate(text):
        # Deterministic digits/+/-/× evaluation: × first, then left-to-right.
        tokens = [int(t) if t.isdigit() else t for t in re.findall(r"\d+|[+\-×]", text)]
        merged = [tokens[0]]
        for index in range(1, len(tokens), 2):
            operator, value = tokens[index], tokens[index + 1]
            if operator == "×":
                merged[-1] = merged[-1] * value
            else:
                merged.extend([operator, value])
        total = merged[0]
        for index in range(1, len(merged), 2):
            total = (
                total + merged[index + 1]
                if merged[index] == "+"
                else total - merged[index + 1]
            )
        return total

    def press(ref):
        label = next(button.title for button in world.buttons if button.element == ref)
        world.sent.append(label)
        if label == "Equals":
            world.value = str(evaluate(expression["text"]))
        elif label in symbols:
            expression["text"] += symbols[label]
        else:
            expression["text"] += label
            world.value = label

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


@pytest.mark.parametrize(
    "task_index,expected",
    [
        (0, {"expression": "7×8", "result": "56"}),
        (30, {"expression": "12×3-8+5", "result": "33"}),
    ],
)
async def test_fake_pilot_runs_three_arms_on_one_ledger(
    request, monkeypatch, tmp_path, task_index, expected
):
    world = request.getfixturevalue("shared_world")
    s5 = _bootstrap(monkeypatch)
    monkeypatch.setattr(s5, "TASKS", (s5.TASKS[task_index],))
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
        assert row["independent_values"] == expected
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
