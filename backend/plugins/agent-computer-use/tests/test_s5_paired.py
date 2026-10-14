"""S5 paired pilot harness tests: three arms, one schedule, shared accounting."""

import json
import re
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

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
    assert frozen["revision"] == "s5-confirmatory-2"
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
    assert frozen["a_timeout_limit"] == 3
    assert frozen["statistics"]["scipy_version"]
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


@pytest.mark.parametrize(
    "identifiers,incomplete,accepted",
    [
        (["Mode: basic; unitConversion: false"], False, True),
        (["Mode: scientific; unitConversion: false"], False, False),
        (["Mode: programmer; unitConversion: false"], False, False),
        (["Mode: basic; unitConversion: true"], False, False),
        (["Mode: unknown; unitConversion: false"], False, False),
        (["Mode: basic; unitConversion: unknown"], False, False),
        ([], False, False),
        (["Mode: basic; unitConversion: false"] * 2, False, False),
        (["Mode: basic; unitConversion: false"], True, False),
    ],
)
def test_owned_calculator_requires_confirmed_basic_mode(
    request, monkeypatch, identifiers, incomplete, accepted
):
    world = request.getfixturevalue("shared_world")
    s5 = _bootstrap(monkeypatch)
    config = SimpleNamespace(bundle_id=s5.BUNDLES["calculator"], window_id=7)
    monkeypatch.setattr(s5.s4_ax.OwnedApplication, "start", lambda self: config)
    monkeypatch.setattr(s5.computer_use_macos, "_active_displays", lambda: [])
    monkeypatch.setattr(s5.computer_use_macos, "_main_geometry", lambda displays: world.window.display_geometry)
    candidates = [replace(world.button, identifier=identifier) for identifier in identifiers]
    monkeypatch.setattr(s5.computer_ax, "ax_window_candidates", lambda *args: (candidates, incomplete))
    owner = s5.OwnedApplication(s5.TASKS[0])
    if accepted:
        assert owner.start() is config
    else:
        with pytest.raises(RuntimeError, match="frozen basic mode"):
            owner.start()


@pytest.mark.parametrize(
    "fields,accepted",
    [
        ({"title": "7", "description": "Other", "identifier": "Other"}, True),
        ({"title": "", "description": "7", "identifier": "digit.seven"}, True),
        ({"title": "", "description": "", "identifier": "", "value": "7"}, True),
        ({"title": "", "description": "", "identifier": "7"}, True),
        ({"title": "Other", "description": "7", "identifier": "7"}, False),
        ({"title": "", "description": "Other", "identifier": "7"}, False),
        ({"title": "", "description": "", "identifier": "Other", "value": "7"}, False),
    ],
)
def test_owned_quartz_calculator_rejects_initial_occlusion(
    request, monkeypatch, fields, accepted
):
    world = request.getfixturevalue("shared_world")
    s5 = _bootstrap(monkeypatch)
    task = next(task for task in s5.TASKS if task["dispatch"] == "quartz")
    config = SimpleNamespace(bundle_id=s5.BUNDLES["calculator"], window_id=7)
    monkeypatch.setattr(s5.s4_ax.OwnedApplication, "start", lambda self: config)
    monkeypatch.setattr(s5.computer_use_macos, "_active_displays", lambda: [])
    monkeypatch.setattr(s5.computer_use_macos, "_main_geometry", lambda displays: world.window.display_geometry)
    candidates = [replace(world.button, identifier="Mode: basic; unitConversion: false")]
    candidates.extend(replace(world.button, **fields) if label == "7"
                      else replace(world.button, title=label, identifier=label)
                      for label in s5.button_sequence(task["expression"]))
    monkeypatch.setattr(s5.computer_ax, "ax_window_candidates", lambda *args: (candidates, False))
    monkeypatch.setattr(s5.native, "read_window", lambda config: world.window)
    monkeypatch.setattr(s5.native, "pointer_target_is_exposed", lambda *args: False)
    owner = s5.OwnedApplication(task)
    with pytest.raises(RuntimeError, match="Quartz.*occluded"):
        owner.start()
    monkeypatch.setattr(s5.native, "pointer_target_is_exposed", lambda *args: True)
    if accepted:
        assert owner.start() is config
    else:
        with pytest.raises(RuntimeError, match="Quartz.*unavailable"):
            owner.start()


def test_fake_confirmation_never_returns_an_adoption_conclusion(monkeypatch):
    s5 = _bootstrap(monkeypatch)
    verdict = s5.confirmatory_verdict({}, completed=True, mode="fake")
    assert verdict["decision"] == "fake_wiring_only_no_adoption_conclusion"
    assert not any(verdict[name] for name in ("h1", "h2", "h3", "h4"))


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


def test_paired_statistics_reports_exact_quality_and_signed_differences(monkeypatch):
    s5 = _bootstrap(monkeypatch)
    pairs = [
        {
            "task_id": f"calculator-long-ax_press-{repeat}",
            "repeat": str(repeat),
            "a_strict": False,
            "h_strict": False,
            "j_strict": True,
            "a_ms": 100,
            "h_ms": 100,
            "j_ms": 99 - repeat,
            "a_nano_usd": 100,
            "h_nano_usd": 100,
            "j_nano_usd": 95,
        }
        for repeat in range(10)
    ]
    report = s5.paired_statistics(pairs)
    comparison = report["by_task"]["calculator-long-ax_press"]["J-H"]
    quality = comparison["quality"]
    assert quality["wins"] == 10 and quality["losses"] == 0
    assert quality["discordant"] == 10
    assert quality["pvalue"] == pytest.approx(2 / 1024)
    assert quality["win_probability_ci95"][1] == 1
    elapsed = comparison["elapsed_ms"]
    assert elapsed["n"] == 10
    assert elapsed["median_difference"] == -5.5
    assert elapsed["median_ci95"] == [-9, -2]
    assert elapsed["ci_coverage"] >= 0.95
    assert elapsed["wilcoxon_pvalue"] == pytest.approx(2 / 1024)
    assert comparison["nano_usd"]["median_difference"] == -5
    assert comparison["nano_usd"]["wilcoxon_pvalue"] == pytest.approx(2 / 1024)


def test_paired_statistics_handles_ties_small_samples_and_repeat_blocks(monkeypatch):
    s5 = _bootstrap(monkeypatch)
    pairs = [
        {
            "task_id": f"calculator-long-{dispatch}-{repeat}",
            "repeat": str(repeat),
            "a_strict": True,
            "h_strict": True,
            "j_strict": True,
            "a_ms": 10,
            "h_ms": 10,
            "j_ms": 10 + (2 if dispatch == "quartz" else 0),
            "a_nano_usd": 10,
            "h_nano_usd": 10,
            "j_nano_usd": 10,
        }
        for repeat in range(3)
        for dispatch in ("ax_press", "quartz")
    ]
    report = s5.paired_statistics(pairs)
    quality = report["by_task"]["calculator-long-quartz"]["J-H"]["quality"]
    assert quality["discordant"] == 0 and quality["pvalue"] == 1
    assert quality["win_probability_ci95"] is None
    elapsed = report["long_family"]["J-H"]["elapsed_ms"]
    assert elapsed["n"] == 3  # Repeat is the block, not the six dispatch trials.
    assert elapsed["median_difference"] == 1
    assert elapsed["median_ci95"] is None and elapsed["ci_coverage"] is None
    cost = report["long_family"]["J-H"]["nano_usd"]
    assert cost["median_difference"] == 0 and cost["wilcoxon_pvalue"] == 1
    assert s5.paired_statistics([]) == {"by_task": {}, "long_family": {}}


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


def test_confirmation_rejects_zero_quality_and_rule_violations(monkeypatch):
    s5 = _bootstrap(monkeypatch)
    summary = {
        "H": {"strict": 0, "nano_usd": 100},
        "J": {"strict": 0, "nano_usd": 60},
        "A": {"strict": 0},
        "long_family": {
            "H": {"strict": 0, "elapsed_ms": 1000},
            "J": {"strict": 0, "elapsed_ms": 1050},
        },
    }
    assert (
        s5.confirmatory_verdict(summary, completed=True)["decision"]
        == "mixed_review_before_any_adoption"
    )
    for arm in ("H", "J"):
        summary["H"]["strict"] = summary["J"]["strict"] = 40
        summary["H"]["rule_violations"] = summary["J"]["rule_violations"] = 0
        summary[arm]["rule_violations"] = 1
        assert (
            s5.confirmatory_verdict(summary, completed=True)["decision"]
            == "mixed_review_before_any_adoption"
        )


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
    assert report["conclusion"] == "fake_wiring_only_no_adoption_conclusion"
    assert report["conclusion"] == report["confirmatory"]["decision"]
    assert report["statistics"]["by_task"]
    assert (output / "rows.jsonl").exists()
    with pytest.raises(FileExistsError):
        await s5.run_batch(output, frozen["sha256"], mode="fake")


async def test_stop_after_long_task_preserves_unstarted_rows_and_summary(
    request, monkeypatch, tmp_path
):
    world = request.getfixturevalue("shared_world")
    s5 = _bootstrap(monkeypatch)
    monkeypatch.setattr(s5, "TASKS", tuple(s5.TASKS[30:32]))
    _install_fake_calculator(monkeypatch, s5, world)
    original_start = s5.OwnedApplication.start
    starts = 0

    def start(owner):
        nonlocal starts
        starts += 1
        if starts == 4:
            raise RuntimeError("Target app already running")
        return original_start(owner)

    monkeypatch.setattr(s5.OwnedApplication, "start", start)
    output = tmp_path / "long-then-stop"
    frozen = s5.prepare(output)
    report = await s5.run_batch(output, frozen["sha256"], mode="fake")
    assert not report["completed"]
    assert [r["status"] for r in report["rows"]] == [
        "finished", "finished", "finished", "environment_error", "not_run", "not_run",
    ]
    assert report["spend"]["stop_reason"] == "s5_trial_unsettled"
    assert report["external_model_requests"] == 0
    assert report["conclusion"] == "incomplete_no_confirmatory_conclusion"
    assert report["statistics"] == {"by_task": {}, "long_family": {}}
    assert len((output / "rows.jsonl").read_text().splitlines()) == 6
    saved = json.loads((output / "result.json").read_text())
    assert saved["conclusion"] == report["conclusion"]
    for row in report["rows"][:3]:
        arm = row["arm"]
        expected = report["spend"]["trials"][row["spend_trial"]]["known_nano_usd"]
        assert report["summary"][arm]["planned"] == 2
        assert report["summary"]["long_family"][arm]["planned"] == 2
        assert report["summary"]["long_family"][arm]["nano_usd"] == expected


async def test_third_a_timeout_stops_batch_and_retains_full_denominator(
    request, monkeypatch, tmp_path
):
    world = request.getfixturevalue("shared_world")
    s5 = _bootstrap(monkeypatch)
    monkeypatch.setattr(s5, "TASKS", tuple(s5.TASKS[:3]))
    _install_fake_calculator(monkeypatch, s5, world)
    original = s5._a_driver_result
    monkeypatch.setattr(
        s5,
        "_a_driver_result",
        lambda result: {
            **original(result),
            "timed_out": True,
        },
    )
    output = tmp_path / "timeouts"
    frozen = s5.prepare(output)
    report = await s5.run_batch(output, frozen["sha256"], mode="fake")
    assert not report["completed"]
    assert report["spend"]["stop_reason"] == "a_timeout_limit"
    assert (
        sum(row.get("driver", {}).get("timed_out", False) for row in report["rows"])
        == 3
    )
    assert len(report["rows"]) == 9
    assert any(row["status"] == "not_run" for row in report["rows"])
    assert len((output / "rows.jsonl").read_text().splitlines()) == 9
    assert report["statistics"] == {"by_task": {}, "long_family": {}}
    assert report["conclusion"] == "incomplete_no_confirmatory_conclusion"


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
    assert report["conclusion"] == "incomplete_no_confirmatory_conclusion"


async def test_setup_failure_stops_before_any_model_call(request, monkeypatch, tmp_path):
    world = request.getfixturevalue("shared_world")
    s5 = _bootstrap(monkeypatch)
    monkeypatch.setattr(s5, "TASKS", (s5.TASKS[0],))
    _install_fake_calculator(monkeypatch, s5, world)

    def blocked(owner):
        raise RuntimeError("Frozen Quartz button is occluded before any model call")

    monkeypatch.setattr(s5.OwnedApplication, "start", blocked)
    output = tmp_path / "blocked"
    frozen = s5.prepare(output)
    report = await s5.run_batch(output, frozen["sha256"], mode="fake")
    assert [row["status"] for row in report["rows"]] == ["environment_error", "not_run", "not_run"]
    assert report["spend"]["batch"]["admitted_requests"] == 0
    assert report["fake_http_requests"] == 0
    assert report["conclusion"] == "incomplete_no_confirmatory_conclusion"
    assert len((output / "rows.jsonl").read_text().splitlines()) == 3


def _preflight(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import a_preflight

    return a_preflight


def _preflight_recipe(module, tmp_path, monkeypatch, name="recipe"):
    import hashlib
    from PIL import Image

    frame = tmp_path / "image.png"
    Image.new("RGB", (1920, 1080)).save(frame)
    monkeypatch.setattr(module, "FRAME_SHA256", hashlib.sha256(frame.read_bytes()).hexdigest())
    output = tmp_path / name
    frozen = module.prepare(frame, output)
    return output, frozen


async def test_a_preflight_real_sdk_single_factor_wire(monkeypatch, tmp_path):
    import base64
    import hashlib

    import httpx
    from openai import AsyncOpenAI

    module = _preflight(monkeypatch)
    output, frozen = _preflight_recipe(module, tmp_path, monkeypatch)
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert request.headers["authorization"] == "Bearer offline"
        payload = json.dumps({"coordinate_space": "normalized_1000", "image_size": [1920, 1080],
                              "x": 165, "y": 387})
        chunks = [
            {"choices": [{"index": 0, "delta": {"reasoning_content": "fake reasoning"}}]},
            {"choices": [{"index": 0, "delta": {"content": payload}, "finish_reason": "stop"}]},
            {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9}},
        ]
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content="".join(
            "data: " + json.dumps({"id": "fake", "object": "chat.completion.chunk", "created": 1,
                                   "model": body["model"], **chunk}) + "\n\n" for chunk in chunks
        ) + "data: [DONE]\n\n")

    def factory(**kwargs):
        assert kwargs["max_retries"] == 0
        return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(respond), trust_env=False))

    monkeypatch.setattr(module, "AsyncOpenAI", factory)
    result = await module.run_batch(output, frozen["sha256"], mode="live", credential="offline")
    assert result["completed"] and len(requests) == 3
    assert all(row["within_annotation"] and row["schema_valid"] for row in result["rows"])
    assert all(row["reasoning_content"] == "fake reasoning" for row in result["rows"])
    assert all(row["usage"]["prompt_tokens"] == 7 for row in result["rows"])
    for body in requests:
        assert "tools" not in body and body["stream_options"] == {"include_usage": True}
        assert body["temperature"] == 0.1 and body["stream"] is True
        png = base64.b64decode(body["messages"][1]["content"][1]["image_url"]["url"].split(",")[1])
        assert hashlib.sha256(png).hexdigest() == frozen["image_sha256"]
    assert requests[0]["max_tokens"] == requests[1]["max_tokens"] == 40000
    assert "enable_thinking" not in requests[0] and requests[1]["enable_thinking"] is False
    assert requests[2]["max_tokens"] == 2048 and "enable_thinking" not in requests[2]
    assert requests[0]["messages"] == requests[1]["messages"] == requests[2]["messages"]
    serialized = "".join(path.read_text() for path in output.glob("*.json*"))
    assert "Bearer offline" not in serialized and "data:image" not in serialized
    with pytest.raises(FileExistsError):
        await module.run_batch(output, frozen["sha256"], mode="live", credential="offline")
    assert len(requests) == 3


@pytest.mark.parametrize("failure", ["missing_usage", "timeout", "http_error"])
async def test_a_preflight_unknown_stops_without_replay(monkeypatch, tmp_path, failure):
    import asyncio

    import httpx
    from openai import AsyncOpenAI

    module = _preflight(monkeypatch)
    if failure == "timeout":
        monkeypatch.setattr(module, "SECONDS_PER_REQUEST", 0.02)
    output, frozen = _preflight_recipe(module, tmp_path, monkeypatch)
    sent = []

    async def respond(request):
        sent.append(request)
        if failure == "timeout":
            await asyncio.Event().wait()
        if failure == "http_error":
            return httpx.Response(500, json={"error": {"message": "NEVER_LOG_SECRET"}})
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              content="data: [DONE]\n\n")

    monkeypatch.setattr(module, "AsyncOpenAI", lambda **kwargs: AsyncOpenAI(
        **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond), trust_env=False)))
    result = await module.run_batch(output, frozen["sha256"], mode="live", credential="offline")
    assert len(sent) == 1 and not result["completed"]
    assert [row["status"] for row in result["rows"]] == ["failed", "not_run", "not_run"]
    assert result["spend"]["stop_reason"] == "unknown_usage"
    assert result["spend"]["batch"]["reserved_nano_usd"] == 190048320
    assert "NEVER_LOG_SECRET" not in (output / "result.json").read_text()


@pytest.mark.parametrize("change", ["image", "signature", "recipe", "source"])
async def test_a_preflight_freeze_drift_zero_client(monkeypatch, tmp_path, change):
    from unittest.mock import Mock

    module = _preflight(monkeypatch)
    output, frozen = _preflight_recipe(module, tmp_path, monkeypatch)
    if change == "image":
        (output / "frame.png").write_bytes(b"changed")
    if change == "recipe":
        changed = json.loads((output / "freeze.json").read_text())
        changed["temperature"] = 0
        (output / "freeze.json").write_text(json.dumps(changed))
    if change == "source":
        original = module.freeze_inputs
        monkeypatch.setattr(module, "freeze_inputs", lambda frame: {**original(frame), "revision": "changed"})
    client = Mock()
    monkeypatch.setattr(module, "AsyncOpenAI", client)
    with pytest.raises(ValueError):
        await module.run_batch(output, "wrong" if change == "signature" else frozen["sha256"],
                               mode="live", credential="offline")
    client.assert_not_called()
    assert not (output / "started.json").exists()


@pytest.mark.parametrize("answer,finish,valid,hit", [
    ({"coordinate_space": "normalized_1000", "image_size": [1920, 1080], "x": 165, "y": 387}, "stop", True, True),
    ({"coordinate_space": "normalized_1000", "image_size": [1920, 1080], "x": 1, "y": 1}, "stop", True, False),
    ({"coordinate_space": "pixels", "image_size": [1920, 1080], "x": 316, "y": 418}, "stop", False, False),
    ({"coordinate_space": "normalized_1000", "image_size": [1280, 720], "x": 165, "y": 387}, "stop", False, False),
    ({"coordinate_space": "normalized_1000", "image_size": [1920, 1080], "x": True, "y": 387}, "stop", False, False),
    ({"coordinate_space": "normalized_1000", "image_size": [1920, 1080], "x": 165, "y": 387}, "length", False, False),
    ('{"coordinate_space":"normalized_1000","image_size":[1920,1080],"x":165,"x":165,"y":387}', "stop", False, False),
])
def test_a_preflight_declared_units_and_complete_reply(monkeypatch, answer, finish, valid, hit):
    module = _preflight(monkeypatch)
    scored = module.score(answer if isinstance(answer, str) else json.dumps(answer), finish, False)
    assert scored["schema_valid"] is valid and scored["within_annotation"] is hit
