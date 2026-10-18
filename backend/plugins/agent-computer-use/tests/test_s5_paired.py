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


def test_attempt_metrics_count_failed_intake_and_one_fallback(monkeypatch):
    _bootstrap(monkeypatch)
    from benchmarks.computer_use.call_metrics import count_attempts

    events = [
        {"kind": "model_call", "phase": "started", "call_id": "intake1",
         "purpose": "computer_use.intake"},
        {"kind": "model_call", "phase": "finished", "call_id": "intake1",
         "purpose": "computer_use.intake", "status": "unknown"},
        {"kind": "model_call", "phase": "started", "call_id": "fallback1",
         "purpose": "computer_use.fallback"},
        {"kind": "model_call", "phase": "finished", "call_id": "fallback1",
         "purpose": "computer_use.fallback", "status": "returned"},
        {"kind": "computer_use_selection", "stage": "fallback", "phase": "start"},
        {"kind": "computer_use_selection", "stage": "fallback", "phase": "result"},
    ]
    row = {"events": events}
    assert count_attempts([row], "intake") == 1
    assert count_attempts([row], "fallback") == 1
    assert count_attempts([row, row], "intake") == 1
    assert count_attempts([{}], "intake") is None
    assert count_attempts([row, {}], "intake") is None
    legacy = {"events": events[-2:], "result": {"details": {"intake": {"application": "app"}}}}
    assert count_attempts([legacy], "fallback") == 1
    assert count_attempts([legacy], "intake") is None
    zero = {"events": [], "result": {"details": {"model_call_metrics_version": 2}}}
    assert count_attempts([zero], "intake") == 0


@pytest.mark.parametrize("stage", ["intake", "fallback"])
def test_attempt_metrics_exclude_unsent_and_preserve_incomplete_missingness(monkeypatch, stage):
    _bootstrap(monkeypatch)
    from benchmarks.computer_use.call_metrics import count_attempts

    start = {"kind": "model_call", "phase": "started", "call_id": "attempt",
             "purpose": f"computer_use.{stage}"}
    finish = {**start, "phase": "finished", "status": "not_started"}
    assert count_attempts([{"events": [start, finish]}], stage) == 0
    assert count_attempts([{"events": [start]}], stage) is None
    assert count_attempts([{"events": [finish]}], stage) == 0
    assert count_attempts([{"events": [{**finish, "status": "returned"}]}], stage) is None
    for status in ("returned", "unknown"):
        assert count_attempts([{"events": [start, {**finish, "status": status}]}], stage) == 1


@pytest.mark.parametrize("failure", ["scope", "reserve", "capture"])
async def test_failed_intake_before_sdk_invoke_has_zero_sdk_calls(monkeypatch, failure):
    import asyncio
    from tank_backend.agents.subagent import (
        SubAgentAuthorization, SubAgentBudget, SubAgentContext, SubAgentStopped,
    )
    from tank_backend.llm.model_call import model_purpose
    from tank_backend.llm.model_data import ModelDataScope
    from tank_backend.llm.profile import LLMProfile
    _bootstrap(monkeypatch)
    from benchmarks.computer_use.call_metrics import count_attempts

    events = []
    class Observer:
        def on_event(self, kind, metadata):
            events.append({"kind": kind, **metadata})
    class Policy:
        def check(self):
            pass
        def reserve(self, call_id, request):
            if failure == "reserve":
                raise SubAgentStopped("policy_denied")
        def settle(self, call_id, inputs, outputs):
            pass
        def release_unsent(self, call_id):
            pass
    class Capture:
        async def request(self, call_id, request):
            raise RuntimeError("capture unavailable")
        async def response(self, call_id, response):
            pass

    ctx = SubAgentContext(
        SubAgentAuthorization(frozenset({"network"})), SubAgentBudget(), asyncio.Event(),
        observer=Observer(), model_policy=Policy(),
        model_capture=Capture() if failure == "capture" else None,
        model_data_scope=ModelDataScope(max_request_bytes=1) if failure == "scope" else ModelDataScope())
    ctx.runtime.configure_model("task", LLMProfile(
        "text", "key", "planner", "https://offline.invalid/v1", max_tokens=128))
    try:
        assert ctx.runtime.model is not None
        with pytest.raises((SubAgentStopped, RuntimeError)):
            with model_purpose("computer_use.intake"):
                await ctx.runtime.model.complete([{"role": "user", "content": "make task brief"}])
        assert count_attempts([{"events": events}], "intake") == 0
        assert ctx.budget.call_count == 0
        assert any(e.get("status") == "not_started" for e in events)
    finally:
        await ctx.runtime.aclose()


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


@pytest.mark.parametrize("harness", ["paired", "dom"])
def test_freeze_rejects_changed_call_metric_source(monkeypatch, tmp_path, harness):
    s5 = _bootstrap(monkeypatch)
    from benchmarks.computer_use import call_metrics, s5_dom

    module = s5 if harness == "paired" else s5_dom
    output = tmp_path / "pilot"
    frozen = module.prepare(output)
    source = Path(call_metrics.__file__)
    original = Path.read_bytes

    def changed(path):
        data = original(path)
        return data + b"\n# changed metrics\n" if path == source else data

    monkeypatch.setattr(Path, "read_bytes", changed)
    with pytest.raises(ValueError, match="changed"):
        module.load_freeze(output, frozen["sha256"])


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


@pytest.mark.parametrize("fenced", [False, True])
async def test_a_preflight_real_sdk_single_factor_wire(monkeypatch, tmp_path, fenced):
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
        if fenced:
            payload = "```json\n" + payload + "\n```"
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
        assert "tools" not in body and "max_tokens" not in body and body["stream_options"] == {"include_usage": True}
        assert body["temperature"] == 0.1 and body["stream"] is True
        png = base64.b64decode(body["messages"][1]["content"][1]["image_url"]["url"].split(",")[1])
        assert hashlib.sha256(png).hexdigest() == frozen["image_sha256"]
    assert requests[0]["max_completion_tokens"] == requests[1]["max_completion_tokens"] == 40000
    assert "enable_thinking" not in requests[0] and requests[1]["enable_thinking"] is False
    assert requests[2]["max_completion_tokens"] == 2048 and "enable_thinking" not in requests[2]
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
    assert result["spend"]["batch"]["reserved_nano_usd"] == 190054920
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
        monkeypatch.setattr(module, "freeze_inputs", lambda frame, case=None: {**original(frame, case), "revision": "changed"})
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


@pytest.mark.parametrize("body,finish,tool,valid,hit", [
    ({"coordinate_space": "normalized_1000", "image_size": [1920, 1080], "x": 165, "y": 387}, "stop", False, True, True),
    ({"coordinate_space": "normalized_1000", "image_size": [1920, 1080], "x": 88, "y": 356}, "stop", False, True, False),
    ({"coordinate_space": "normalized_1000", "image_size": [1920, 1080], "x": None, "y": None}, "stop", False, True, False),
    ({"coordinate_space": "normalized_1000", "image_size": [1920, 1080], "x": None, "y": 387}, "stop", False, False, False),
    ({"coordinate_space": "normalized_1000", "image_size": [1920, 1080], "x": True, "y": 387}, "stop", False, False, False),
    ({"coordinate_space": "normalized_1000", "image_size": [1920, 1080], "x": "165", "y": 387}, "stop", False, False, False),
    ({"coordinate_space": "normalized_1000", "image_size": [1920, 1080], "x": 165.0, "y": 387}, "stop", False, False, False),
    ({"coordinate_space": "normalized_1000", "image_size": [1920.0, 1080], "x": 165, "y": 387}, "stop", False, False, False),
    ({"coordinate_space": "normalized_1000", "image_size": [1280, 720], "x": 165, "y": 387}, "stop", False, False, False),
    ({"coordinate_space": "pixels", "image_size": [1920, 1080], "x": 316, "y": 418}, "stop", False, False, False),
    ({"image_size": [1920, 1080], "x": 165, "y": 387}, "stop", False, False, False),
    ({"coordinate_space": "normalized_1000", "image_size": [1920, 1080], "x": 165, "y": 387, "extra": 1}, "stop", False, False, False),
    ({"coordinate_space": "normalized_1000", "image_size": [1920, 1080], "x": 1001, "y": 387}, "stop", False, False, False),
    ({"coordinate_space": "normalized_1000", "image_size": [1920, 1080], "x": 165, "y": -1}, "stop", False, False, False),
    ({"coordinate_space": "normalized_1000", "image_size": [1920, 1080], "x": 165, "y": 387}, "length", False, False, False),
    ({"coordinate_space": "normalized_1000", "image_size": [1920, 1080], "x": 165, "y": 387}, "stop", True, False, False),
    ('{"coordinate_space":"normalized_1000","image_size":[1920,1080],"x":165,"x":88,"y":387}', "stop", False, False, False),
    ('{"coordinate_space":"normalized_1000","image_size":[1920,1080],"x":165,"y":NaN}', "stop", False, False, False),
    ('{"coordinate_space":"normalized_1000","image_size":[1920,1080],"x":165,"y":387', "stop", False, False, False),
    ([], "stop", False, False, False),
])
def test_a_preflight_fenced_reply_keeps_strict_semantics(monkeypatch, body, finish, tool, valid, hit):
    module = _preflight(monkeypatch)
    raw = body if isinstance(body, str) else json.dumps(body)
    result = module.score(" \n```json\n" + raw + "\n```\n ", finish, tool)
    assert result["schema_valid"] is valid and result["within_annotation"] is hit
    if valid:
        assert result == module.score(raw, finish, tool)


@pytest.mark.parametrize("wrapper", [
    "```json\n{}", "{}\n```", "prefix\n```json\n{}\n```",
    "```json\n{}\n```\nsuffix", "```\n{}\n```", "```python\n{}\n```",
    "```json\n{}\n```\n```json\n{}\n```", "```json\n```json\n{}\n```\n```",
])
def test_a_preflight_rejects_non_whole_json_fences(monkeypatch, wrapper):
    module = _preflight(monkeypatch)
    body = json.dumps({"coordinate_space": "normalized_1000", "image_size": [1920, 1080],
                       "x": 165, "y": 387})
    assert not module.score(wrapper.replace("{}", body), "stop", False)["schema_valid"]


def test_a_preflight_revision_pins_shared_format_source(monkeypatch, tmp_path):
    module = _preflight(monkeypatch)
    _, frozen = _preflight_recipe(module, tmp_path, monkeypatch)
    assert frozen["revision"] == "a-static-preflight-4"
    assert frozen["response_format"] == "pure-json-or-single-json-lf-fence"
    assert "core/src/tank_backend/benchmarks/grounding_probe.py" in frozen["source_sha256"]


def _independent_static_case(tmp_path):
    import hashlib

    from PIL import Image

    frame = tmp_path / "new-frame.png"
    Image.new("RGB", (1920, 1080), "navy").save(frame)
    case = {"image_sha256": hashlib.sha256(frame.read_bytes()).hexdigest(),
            "annotation": {"center": [1234, 789], "radius": 20, "provenance": "TRUTH_PRIVATE"}}
    path = tmp_path / "new-case.json"
    path.write_text(json.dumps(case))
    return frame, path, case


async def test_independent_static_case_binds_sdk_image_and_scoring(monkeypatch, tmp_path):
    import base64
    import hashlib

    import httpx
    from openai import AsyncOpenAI

    module = _preflight(monkeypatch)
    frame, path, case = _independent_static_case(tmp_path)
    output = tmp_path / "new-recipe"
    frozen = module.prepare(frame, output, case_path=path)
    assert frozen["revision"] == "a-static-preflight-4"
    assert frozen["annotation"] == case["annotation"]
    assert json.loads((output / "case.json").read_text()) == case
    assert module.load_freeze(output, frozen["sha256"]) == frozen
    sent = []

    def respond(request):
        body = json.loads(request.content)
        sent.append(body)
        assert "TRUTH_PRIVATE" not in json.dumps(body) and "annotation" not in json.dumps(body)
        image = body["messages"][1]["content"][1]["image_url"]["url"].split(",", 1)[1]
        assert hashlib.sha256(base64.b64decode(image)).hexdigest() == case["image_sha256"]
        reply = "```json\n" + json.dumps({"coordinate_space": "normalized_1000",
            "image_size": [1920, 1080], "x": 643, "y": 731}) + "\n```"
        chunks = [
            {"choices": [{"index": 0, "delta": {"content": reply}, "finish_reason": "stop"}]},
            {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9}},
        ]
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content="".join(
            "data: " + json.dumps({"id": "fake", "object": "chat.completion.chunk", "created": 1,
                                   "model": body["model"], **chunk}) + "\n\n" for chunk in chunks
        ) + "data: [DONE]\n\n")

    monkeypatch.setattr(module, "AsyncOpenAI", lambda **kwargs: AsyncOpenAI(
        **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond), trust_env=False)))
    result = await module.run_batch(output, frozen["sha256"], mode="live", credential="offline")
    assert result["completed"] and len(sent) == 3
    assert all(row["point"] == [1234, 789] and row["within_annotation"] for row in result["rows"])
    assert all(row["usage"]["prompt_tokens"] == 7 for row in result["rows"])
    assert (output / "case.json").read_bytes() == path.read_bytes()


@pytest.mark.parametrize("change", ["center", "radius", "provenance", "missing"])
async def test_independent_static_case_drift_is_rejected_before_client(monkeypatch, tmp_path, change):
    from unittest.mock import Mock

    module = _preflight(monkeypatch)
    frame, path, case = _independent_static_case(tmp_path)
    output = tmp_path / "new-recipe"
    frozen = module.prepare(frame, output, case_path=path)
    bound = output / "case.json"
    if change == "missing":
        bound.unlink()
    else:
        case["annotation"][change] = {"center": [1300, 789], "radius": 21, "provenance": "changed"}[change]
        bound.write_text(json.dumps(case))
    client = Mock()
    monkeypatch.setattr(module, "AsyncOpenAI", client)
    with pytest.raises(ValueError):
        await module.run_batch(output, frozen["sha256"], mode="live", credential="offline")
    client.assert_not_called()
    assert not (output / "started.json").exists()


@pytest.mark.parametrize("field,value", [
    ("image_sha256", "0" * 64), ("image_sha256", "not-a-sha"),
    ("center", [1920, 789]), ("center", [-1, 789]), ("center", [True, 789]),
    ("center", [1234.0, 789]), ("center", [1234]), ("radius", 0),
    ("radius", True), ("radius", 2000), ("provenance", ""), ("extra", "unexpected"),
])
def test_independent_static_case_rejects_invalid_annotation(monkeypatch, tmp_path, field, value):
    module = _preflight(monkeypatch)
    frame, path, case = _independent_static_case(tmp_path)
    if field in {"image_sha256", "extra"}:
        case[field] = value
    else:
        case["annotation"][field] = value
    path.write_text(json.dumps(case))
    output = tmp_path / "invalid-recipe"
    with pytest.raises(ValueError):
        module.prepare(frame, output, case_path=path)
    assert not output.exists()


@pytest.mark.parametrize("offset", [0, 1, 10, 11, None])
async def test_total_output_cap_reservation_and_usage_boundaries(monkeypatch, tmp_path, offset):
    import httpx
    from openai import AsyncOpenAI

    module = _preflight(monkeypatch)
    output, frozen = _preflight_recipe(module, tmp_path, monkeypatch)
    assert frozen["revision"] == "a-static-preflight-4"
    assert frozen["output_contract"]["parameter"] == "max_completion_tokens"
    assert frozen["output_contract"]["usage_slack_tokens"] == 10
    assert frozen["production_max_tokens_reference"] == 40000
    sent = []

    def respond(request):
        body = json.loads(request.content)
        sent.append(body)
        assert "max_tokens" not in body
        cap = body["max_completion_tokens"]
        assert cap in (40000, 2048)
        reply = json.dumps({"coordinate_space": "normalized_1000", "image_size": [1920, 1080],
                            "x": 165, "y": 387})
        chunks: list[dict[str, object]] = [
            {"choices": [{"index": 0, "delta": {"content": reply}, "finish_reason": "stop"}]},
        ]
        if offset is not None:
            chunks.append({"choices": [], "usage": {"prompt_tokens": 7,
                "completion_tokens": cap + offset, "total_tokens": 7 + cap + offset,
                "completion_tokens_details": {"reasoning_tokens": cap + offset - 2}}})
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content="".join(
            "data: " + json.dumps({"id": "fake", "object": "chat.completion.chunk", "created": 1,
                                   "model": body["model"], **chunk}) + "\n\n" for chunk in chunks
        ) + "data: [DONE]\n\n")

    monkeypatch.setattr(module, "AsyncOpenAI", lambda **kwargs: AsyncOpenAI(
        **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond), trust_env=False)))
    report = await module.run_batch(output, frozen["sha256"], mode="live", credential="offline")
    batch = report["spend"]["batch"]
    requests = list(report["spend"]["requests"].values())
    assert requests[0]["allowance"]["output_tokens"] == 40010
    if offset is not None and offset <= 10:
        assert report["completed"] and len(sent) == 3
        assert [body["max_completion_tokens"] for body in sent] == [40000, 40000, 2048]
        assert [item["allowance"]["output_tokens"] for item in requests] == [40010, 40010, 2058]
        assert all(item["status"] == "known" for item in requests)
        assert batch["known_tokens"] == 21 + 82048 + 3 * offset
        assert batch["reserved_nano_usd"] == 0
    else:
        assert len(sent) == 1 and not report["completed"]
        assert [row["status"] for row in report["rows"]] == ["failed", "not_run", "not_run"]
        if offset is None:
            assert report["spend"]["stop_reason"] == "unknown_usage"
            assert batch["reserved_tokens"] == 1031818
            assert batch["reserved_nano_usd"] == 190054920
        else:
            assert report["spend"]["stop_reason"] == "bound_exceeded"
            assert requests[0]["status"] == "bound_exceeded"
            assert batch["known_tokens"] == 40018 and batch["reserved_nano_usd"] == 0
            assert batch["known_nano_usd"] == 7 * 165 + 40011 * 660


async def test_total_cap_known_overrun_preserves_completed_reply_and_failure(monkeypatch, tmp_path):
    import httpx
    from openai import AsyncOpenAI

    module = _preflight(monkeypatch)
    output, frozen = _preflight_recipe(module, tmp_path, monkeypatch)
    sent = []

    def respond(request):
        body = json.loads(request.content)
        sent.append(body)
        assert "max_tokens" not in body and body["max_completion_tokens"] in (40000, 2048)
        count = 3021 if len(sent) == 3 else 2
        reply = json.dumps({"coordinate_space": "normalized_1000", "image_size": [1920, 1080],
                            "x": 165, "y": 387})
        chunk = {"id": "fake", "object": "chat.completion.chunk", "created": 1,
            "model": body["model"], "choices": [{"index": 0, "delta": {"content": reply},
            "finish_reason": "stop"}], "usage": {"prompt_tokens": 7,
            "completion_tokens": count, "total_tokens": count + 7}}
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              content="data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n")

    monkeypatch.setattr(module, "AsyncOpenAI", lambda **kwargs: AsyncOpenAI(
        **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond), trust_env=False)))
    report = await module.run_batch(output, frozen["sha256"], mode="live", credential="offline")
    assert len(sent) == 3 and not report["completed"]
    assert [row["status"] for row in report["rows"]] == ["finished", "finished", "failed"]
    last = report["rows"][-1]
    assert last["finish_reason"] == "stop" and not last["schema_valid"]
    assert last["usage"]["completion_tokens"] == 3021 and last["error"] == "SpendLimitExceeded"
    assert report["spend"]["stop_reason"] == "bound_exceeded"
    assert report["spend"]["batch"]["known_tokens"] == 3046
    assert report["spend"]["batch"]["reserved_nano_usd"] == 0
    assert module.score(last["content"], "stop", False)["schema_valid"]


async def test_total_cap_slack_drift_rejected_before_client(monkeypatch, tmp_path):
    from unittest.mock import Mock

    module = _preflight(monkeypatch)
    output, frozen = _preflight_recipe(module, tmp_path, monkeypatch)
    monkeypatch.setattr(module, "OUTPUT_USAGE_SLACK", 11)
    client = Mock()
    monkeypatch.setattr(module, "AsyncOpenAI", client)
    with pytest.raises(ValueError):
        await module.run_batch(output, frozen["sha256"], mode="live", credential="offline")
    client.assert_not_called()
    assert not (output / "started.json").exists()


def _cross_image(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import a_cross_image

    return a_cross_image


def _cross_inputs(tmp_path):
    import hashlib

    from PIL import Image

    folders = []
    for index, (color, center) in enumerate((("navy", [480, 324]), ("darkgreen", [1440, 756])), 1):
        folder = tmp_path / f"input-{index}"
        folder.mkdir()
        Image.new("RGB", (1920, 1080), color).save(folder / "frame.png")
        case = {"image_sha256": hashlib.sha256((folder / "frame.png").read_bytes()).hexdigest(),
                "annotation": {"center": center, "radius": 20, "provenance": f"PRIVATE_TRUTH_{index}"}}
        (folder / "case.json").write_text(json.dumps(case))
        folders.append(folder)
    return folders


@pytest.mark.parametrize("scenario", ["valid", "format", "length", "miss", "unknown", "overrun"])
async def test_cross_image_pairs_share_budget_and_preserve_failures(monkeypatch, tmp_path, scenario):
    import base64
    import hashlib

    import httpx
    from openai import AsyncOpenAI
    from tank_backend.benchmarks.spend_ledger import SpendLedger

    module = _cross_image(monkeypatch)
    static = _preflight(monkeypatch)
    inputs = _cross_inputs(tmp_path)
    output = tmp_path / "cross"
    frozen = module.prepare(inputs, output)
    assert frozen["revision"] == "a-cross-image-1"
    assert [(x["image_id"], x["arm"]) for x in frozen["schedule"]] == [
        ("image-1", "default"), ("image-1", "no-think"),
        ("image-2", "no-think"), ("image-2", "default"),
    ]
    assert module.load_freeze(output, frozen["sha256"]) == frozen
    hashes = [json.loads((folder / "case.json").read_text())["image_sha256"] for folder in inputs]
    sent = []
    ledgers = []

    def ledger_factory(*args, **kwargs):
        ledger = SpendLedger(*args, **kwargs)
        ledgers.append(ledger)
        return ledger

    monkeypatch.setattr(module, "SpendLedger", ledger_factory)

    def respond(request):
        body = json.loads(request.content)
        sent.append(body)
        assert "max_tokens" not in body and body["max_completion_tokens"] == 2048
        assert "PRIVATE_TRUTH" not in json.dumps(body) and "annotation" not in json.dumps(body)
        assert body["stream_options"] == {"include_usage": True} and body["temperature"] == 0.1
        png = base64.b64decode(body["messages"][1]["content"][1]["image_url"]["url"].split(",", 1)[1])
        index = hashes.index(hashlib.sha256(png).hexdigest())
        x, y = ((250, 300), (750, 700))[index]
        if scenario == "miss" and len(sent) == 2:
            x = y = 0
        content = json.dumps({"coordinate_space": "normalized_1000", "image_size": [1920, 1080], "x": x, "y": y})
        if scenario == "format" and len(sent) == 1:
            content = "not JSON"
        finish = "length" if scenario == "length" and len(sent) == 1 else "stop"
        count = 2050 if finish == "length" else 2059 if scenario == "overrun" else 11
        chunks: list[dict[str, object]] = [{"choices": [{"index": 0, "delta": {"content": content}, "finish_reason": finish}]}]
        if scenario != "unknown":
            chunks.append({"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": count, "total_tokens": count + 7}})
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content="".join(
            "data: " + json.dumps({"id": "fake", "object": "chat.completion.chunk", "created": 1,
                                   "model": body["model"], **chunk}) + "\n\n" for chunk in chunks
        ) + "data: [DONE]\n\n")

    def factory(**kwargs):
        assert kwargs["max_retries"] == 0
        return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond), trust_env=False))

    monkeypatch.setattr(static, "AsyncOpenAI", factory)
    report = await module.run_batch(output, frozen["sha256"], mode="live", credential="offline")
    assert len(ledgers) == 1 and len(report["rows"]) == 4
    if scenario in ("unknown", "overrun"):
        assert len(sent) == 1 and not report["completed"] and report["pairs"] == []
        assert report["verdict"] == "incomplete_no_candidate_conclusion"
        assert [row["status"] for row in report["rows"]] == ["failed", "not_run", "not_run", "not_run"]
        assert report["spend"]["stop_reason"] == ("unknown_usage" if scenario == "unknown" else "bound_exceeded")
        assert report["spend"]["batch"]["reserved_nano_usd"] == (165006600 if scenario == "unknown" else 0)
    else:
        assert len(sent) == 4 and report["completed"] and len(report["pairs"]) == 2
        assert report["spend"]["batch"]["admitted_requests"] == 4
        assert len(report["spend"]["trials"]) == 4 and report["spend"]["stop_reason"] is None
        assert [body.get("enable_thinking") for body in sent] == [None, False, False, None]
        assert sent[0]["messages"] == sent[1]["messages"] and sent[2]["messages"] == sent[3]["messages"]
        assert sent[0]["messages"] != sent[2]["messages"]
        assert report["verdict"] == ("candidate_not_qualified" if scenario == "miss" else "advance_to_owned_gui_smoke_preparation")
        if scenario in ("format", "length"):
            assert report["rows"][0]["status"] == "failed"
            assert [row["status"] for row in report["rows"]][1:] == ["finished"] * 3
    with pytest.raises(FileExistsError):
        await module.run_batch(output, frozen["sha256"], mode="live", credential="offline")
    assert len(sent) == (1 if scenario in ("unknown", "overrun") else 4)


@pytest.mark.parametrize("change", ["annotation", "image", "signature"])
async def test_cross_image_freeze_drift_zero_client(monkeypatch, tmp_path, change):
    from unittest.mock import Mock

    module = _cross_image(monkeypatch)
    static = _preflight(monkeypatch)
    output = tmp_path / "cross"
    frozen = module.prepare(_cross_inputs(tmp_path), output)
    if change == "annotation":
        path = output / "image-1/case.json"
        case = json.loads(path.read_text())
        case["annotation"]["radius"] = 21
        path.write_text(json.dumps(case))
    elif change == "image":
        (output / "image-2/frame.png").write_bytes(b"changed")
    client = Mock()
    monkeypatch.setattr(static, "AsyncOpenAI", client)
    with pytest.raises(ValueError):
        await module.run_batch(output, "wrong" if change == "signature" else frozen["sha256"], mode="live", credential="offline")
    client.assert_not_called()
    assert not (output / "started.json").exists()


async def test_cross_image_fake_never_gives_candidate_verdict(monkeypatch, tmp_path):
    module = _cross_image(monkeypatch)
    output = tmp_path / "cross"
    frozen = module.prepare(_cross_inputs(tmp_path), output)
    report = await module.run_batch(output, frozen["sha256"], mode="fake")
    assert report["completed"] and report["fake_http_requests"] == 4
    assert report["external_model_requests"] == 0 and report["new_gui_operations"] == 0
    assert report["verdict"] == "fake_wiring_only_no_candidate_conclusion"


async def test_original_static_recipe_still_stops_known_invalid_json(monkeypatch, tmp_path):
    import httpx
    from openai import AsyncOpenAI

    static = _preflight(monkeypatch)
    output, frozen = _preflight_recipe(static, tmp_path, monkeypatch)
    sent = []

    def respond(request):
        sent.append(request)
        chunk = {"id": "fake", "object": "chat.completion.chunk", "created": 1,
            "model": "fake", "choices": [{"index": 0, "delta": {"content": "not JSON"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9}}
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content="data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n")

    monkeypatch.setattr(static, "AsyncOpenAI", lambda **kwargs: AsyncOpenAI(
        **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond), trust_env=False)))
    report = await static.run_batch(output, frozen["sha256"], mode="live", credential="offline")
    assert len(sent) == 1 and report["spend"]["stop_reason"] == "invalid_reply"
    assert [row["status"] for row in report["rows"]] == ["failed", "not_run", "not_run"]
    assert report["spend"]["batch"]["known_tokens"] == 9


@pytest.mark.parametrize("mode", ["fake", "live"])
def test_cross_image_incomplete_gate_never_implies_wiring_success(monkeypatch, mode):
    module = _cross_image(monkeypatch)
    assert module.verdict([], False, mode) == "incomplete_no_candidate_conclusion"


@pytest.mark.parametrize("phase", ["settlement", "close"])
async def test_cross_image_persistence_failure_retains_four_rows(monkeypatch, tmp_path, phase):
    from tank_backend.benchmarks import spend_ledger

    module = _cross_image(monkeypatch)
    static = _preflight(monkeypatch)
    output = tmp_path / "cross"
    frozen = module.prepare(_cross_inputs(tmp_path), output)
    respond = static._fake
    sent = []

    def fail_fsync(_fd):
        raise OSError("simulated journal fsync failure")

    def respond_then_fail_persistence(request):
        sent.append(request)
        if phase == "settlement":
            monkeypatch.setattr(spend_ledger.os, "fsync", fail_fsync)
        return respond(request)

    close = spend_ledger.SpendLedger.close

    def close_with_failure(ledger):
        monkeypatch.setattr(spend_ledger.os, "fsync", fail_fsync)
        close(ledger)

    if phase == "close":
        monkeypatch.setattr(spend_ledger.SpendLedger, "close", close_with_failure)
    monkeypatch.setattr(static, "_fake", respond_then_fail_persistence)
    with pytest.raises(spend_ledger.SpendLimitExceeded, match="persistence_error"):
        await module.run_batch(output, frozen["sha256"], mode="fake")
    report = json.loads((output / "result.json").read_text())
    assert len(sent) == (1 if phase == "settlement" else 4) and len(report["rows"]) == 4
    assert [row["status"] for row in report["rows"]] == (
        ["failed", "not_run", "not_run", "not_run"] if phase == "settlement" else ["finished"] * 4)
    assert report["spend"]["stop_reason"] == "persistence_error"
    assert not report["completed"] and report["pairs"] == []
    assert report["verdict"] == "incomplete_no_candidate_conclusion"


@pytest.fixture
def owned_input_world(monkeypatch):
    """Only the native OS boundaries are replaced; guard and mapping are real."""
    import io
    from PIL import Image
    from agent_computer_use.channels import native
    from .test_native import native_config

    _bootstrap(monkeypatch)
    from benchmarks.computer_use.a_owned_input import OwnedInputGuard

    window = native.NativeWindow(42, "1:0", "test.counter", 7, (10, 10, 60, 50),
                                 (5, 0, 0, 100, 80, 200, 160))
    world = SimpleNamespace(window=window, image=Image.new("RGB", (100, 80)), sent=[],
                            exposed=True, idle=True, blocked=False)

    def capture(**kwargs):
        stream = io.BytesIO()
        world.image.save(stream, format="PNG")
        return stream.getvalue()

    def check():
        if world.blocked:
            raise RuntimeError("task cancelled")

    monkeypatch.setattr(native, "read_window", lambda config: world.window)
    monkeypatch.setattr(native.macos, "_capture_screenshot_macos", capture)
    monkeypatch.setattr(native, "pointer_target_is_exposed", lambda *args: world.exposed)
    monkeypatch.setattr(native, "inputs_idle", lambda: world.idle)
    monkeypatch.setattr(native.macos, "_click_macos",
                        lambda x, y, **kwargs: world.sent.append(("click", x, y)))
    monkeypatch.setattr(native.macos, "_key_macos",
                        lambda keys: world.sent.append(("key", keys)))
    world.guard = OwnedInputGuard(native.NativeConfig.model_validate_json(json.dumps(native_config())), check=check)
    return world


def test_owned_input_click_consumes_frame(owned_input_world):
    world = owned_input_world
    frame, png = world.guard.observe()
    assert png.startswith(b"\x89PNG")
    world.guard.click(frame.frame_id, 20, 20)
    assert world.sent == [("click", 20, 20)]
    with pytest.raises(ValueError, match="frame"):
        world.guard.click(frame.frame_id, 20, 20)
    assert len(world.sent) == 1


@pytest.mark.parametrize("change", ["outside", "moved", "process", "pixels", "occluded", "busy"])
def test_owned_input_rejects_changed_or_unowned_target(owned_input_world, change):
    world = owned_input_world
    frame, _ = world.guard.observe()
    point = (20, 20)
    if change == "outside":
        point = (80, 20)
    elif change == "moved":
        world.window = replace(world.window, bounds=(11, 10, 60, 50))
    elif change == "process":
        world.window = replace(world.window, process_start="2:0")
    elif change == "pixels":
        world.image.putpixel((20, 20), (255, 0, 0))
    elif change == "occluded":
        world.exposed = False
    elif change == "busy":
        world.idle = False
    with pytest.raises(ValueError):
        world.guard.click(frame.frame_id, *point)
    assert world.sent == []


def test_owned_input_enter_is_single_use_and_rejects_shortcuts(owned_input_world):
    world = owned_input_world
    frame, _ = world.guard.observe()
    with pytest.raises(ValueError):
        world.guard.key_press(frame.frame_id, "cmd+q")
    assert not world.sent
    frame, _ = world.guard.observe()
    world.guard.key_press(frame.frame_id, "enter")
    assert world.sent == [("key", ["return"])]
    with pytest.raises(ValueError):
        world.guard.key_press(frame.frame_id, "enter")
    assert len(world.sent) == 1


@pytest.mark.parametrize("action", ["click", "key_press"])
@pytest.mark.parametrize("failure", ["foreground", "cancelled", "dispatch"])
def test_owned_input_failure_never_replays(owned_input_world, monkeypatch, action, failure):
    from agent_computer_use.channels import native
    from tank_backend.agents.subagent import SubAgentStopped

    world = owned_input_world
    frame, _ = world.guard.observe()
    if failure == "foreground":
        def changed(config):
            raise SubAgentStopped("foreground_changed")
        monkeypatch.setattr(native, "read_window", changed)
    elif failure == "cancelled":
        world.blocked = True
    else:
        def uncertain(*args, **kwargs):
            world.sent.append("possibly_sent")
            raise OSError("lost native return")
        monkeypatch.setattr(native.macos,
                            "_click_macos" if action == "click" else "_key_macos", uncertain)
    args = (20, 20) if action == "click" else ("enter",)
    with pytest.raises((SubAgentStopped, RuntimeError, OSError)):
        getattr(world.guard, action)(frame.frame_id, *args)
    assert len(world.sent) == (1 if failure == "dispatch" else 0)
    with pytest.raises(ValueError, match="frame"):
        getattr(world.guard, action)(frame.frame_id, *args)
    assert len(world.sent) == (1 if failure == "dispatch" else 0)


def test_owned_input_rejects_old_and_foreign_frames(owned_input_world):
    from benchmarks.computer_use.a_owned_input import OwnedInputGuard

    world = owned_input_world
    previous, _ = world.guard.observe()
    world.guard.observe()
    with pytest.raises(ValueError, match="frame"):
        world.guard.click(previous.frame_id, 20, 20)
    other = OwnedInputGuard(world.guard.config, check=lambda: None)
    foreign, _ = other.observe()
    world.guard.observe()
    with pytest.raises(ValueError, match="frame"):
        world.guard.click(foreign.frame_id, 20, 20)
    assert world.sent == []


def test_owned_input_ignores_pixels_outside_owned_window(owned_input_world):
    world = owned_input_world
    frame, _ = world.guard.observe()
    world.image.putpixel((90, 70), (255, 0, 0))
    world.guard.click(frame.frame_id, 20, 20)
    assert world.sent == [("click", 20, 20)]


def test_owned_input_checks_after_capture_and_before_dispatch(owned_input_world, monkeypatch):
    from agent_computer_use.channels import native

    world = owned_input_world
    frame, _ = world.guard.observe()
    original = native.pointer_target_is_exposed

    def lose_focus(*args):
        world.window = replace(world.window, window_id=8)
        return original(*args)

    monkeypatch.setattr(native, "pointer_target_is_exposed", lose_focus)
    with pytest.raises(ValueError, match="Window changed"):
        world.guard.click(frame.frame_id, 20, 20)
    assert world.sent == []


def test_owned_input_capture_failure_invalidates_previous_frame(owned_input_world, monkeypatch):
    from agent_computer_use.channels import native

    world = owned_input_world
    frame, _ = world.guard.observe()
    original = native.macos._capture_screenshot_macos

    def moving(**kwargs):
        png = original(**kwargs)
        world.window = replace(world.window, bounds=(11, 10, 60, 50))
        return png

    monkeypatch.setattr(native.macos, "_capture_screenshot_macos", moving)
    with pytest.raises(ValueError, match="capture"):
        world.guard.observe()
    with pytest.raises(ValueError, match="frame"):
        world.guard.click(frame.frame_id, 20, 20)
    assert world.sent == []


def test_gui_smoke_preparation_is_offline_and_pins_one_request(monkeypatch, tmp_path):
    _bootstrap(monkeypatch)
    from benchmarks.computer_use import a_gui_smoke as smoke

    def forbidden(*args, **kwargs):
        raise AssertionError("preparation touched the desktop")

    monkeypatch.setattr(smoke.s5.OwnedApplication, "start", forbidden)
    frozen = smoke.prepare(tmp_path / "smoke")
    assert frozen["arm"] == "A-control-owned-seven"
    assert frozen["request_limit"] == 1
    assert frozen["nano_usd_limit"] == 200000000
    assert frozen["case"]["max_completion_tokens"] == 2048
    assert frozen["case"]["extra_body"] == {"enable_thinking": False}
    assert smoke.load_freeze(tmp_path / "smoke", frozen["sha256"]) == frozen
    assert not (tmp_path / "smoke" / "started.json").exists()
    with pytest.raises(ValueError, match="freeze"):
        smoke.load_freeze(tmp_path / "smoke", "wrong")


@pytest.fixture
def gui_smoke_world(owned_input_world, monkeypatch):
    from PIL import Image
    from agent_computer_use.channels import native
    from tank_backend.benchmarks.desktop_cleanup import MacOSInputCleanup
    from benchmarks.computer_use import a_gui_smoke as smoke
    from tank_backend.tools.computer_ax import AXCandidate

    world = owned_input_world
    world.window = replace(world.window, bounds=(180, 160, 232, 350),
                           display_geometry=(5, 0, 0, 1920, 1080, 3840, 2160))
    world.image = Image.new("RGB", (1920, 1080))
    world.events = []
    world.value = "7"
    world.cleanup_ok = True
    world.target = AXCandidate(1, "AXButton", "7", "", "", "7", ("AXPress",), True,
                               (190, 347, 48, 48), AXElementRef(object(), False, 1080),
                               pid=42, window_id=7)
    monkeypatch.setattr(smoke.s5.computer_ax, "ax_window_candidates",
                        lambda *args: ([world.target], False))

    class Owner:
        setup_actions = ["clear_owned_calculator"]
        def __init__(self, task):
            pass
        def start(self):
            assert smoke.resources.DESKTOP_RESOURCE.lock.locked()
            world.events.append("start")
            return world.guard.config
        def read_values_once(self):
            return {"result": world.value if world.sent else "0", "expression": ""}
        def close(self):
            assert smoke.resources.DESKTOP_RESOURCE.lock.locked()
            world.events.append("app_cleanup")
            return {"confirmed": world.cleanup_ok}

    def release(self):
        assert smoke.resources.DESKTOP_RESOURCE.lock.locked()
        world.events.append("input_cleanup")
        return {"errors": [], "keys_before": [], "buttons_before": []}

    monkeypatch.setattr(smoke.s5, "OwnedApplication", Owner)
    monkeypatch.setattr(MacOSInputCleanup, "_state", staticmethod(lambda: ([], [])))
    monkeypatch.setattr(MacOSInputCleanup, "_release", release)
    # Native foreground/identity is exercised by the real guard with OS boundaries replaced.
    monkeypatch.setattr(native, "read_window", lambda config: world.window)
    monkeypatch.setattr(smoke.resources, "DESKTOP_RESOURCE", smoke.resources.DesktopResource())
    return world


async def test_gui_smoke_fake_http_click_readback_and_cleanup(gui_smoke_world, tmp_path):
    from benchmarks.computer_use import a_gui_smoke as smoke

    world = gui_smoke_world
    output = tmp_path / "smoke"
    frozen = smoke.prepare(output)
    report = await smoke.run_batch(output, frozen["sha256"], mode="fake")
    assert report["passed"] is True
    assert report["verdict"] == "fake_wiring_only"
    assert report["external_model_requests"] == 0
    assert report["fake_http_requests"] == 1
    assert len(world.sent) == 1
    assert world.events == ["start", "input_cleanup", "app_cleanup"]
    assert not smoke.resources.DESKTOP_RESOURCE.lock.locked()
    request = json.loads((output / "A-control-owned-seven.request.json").read_text())
    assert "annotation" not in json.dumps(request)
    assert request["enable_thinking"] is False
    assert request["max_completion_tokens"] == 2048
    with pytest.raises(FileExistsError):
        await smoke.run_batch(output, frozen["sha256"], mode="fake")
    assert len(world.sent) == 1


@pytest.mark.parametrize("case", ["wrong_readback", "occluded", "cleanup_failed", "native_error"])
async def test_gui_smoke_failure_keeps_cleanup_and_no_retry(gui_smoke_world, monkeypatch, tmp_path, case):
    from agent_computer_use.channels import native
    from benchmarks.computer_use import a_gui_smoke as smoke

    world = gui_smoke_world
    if case == "wrong_readback":
        world.value = "9"
    elif case == "occluded":
        world.exposed = False
    elif case == "cleanup_failed":
        world.cleanup_ok = False
    else:
        def uncertain(*args, **kwargs):
            world.sent.append("possibly_sent")
            raise OSError("lost native return")
        monkeypatch.setattr(native.macos, "_click_macos", uncertain)
    output = tmp_path / "smoke"
    frozen = smoke.prepare(output)
    report = await smoke.run_batch(output, frozen["sha256"], mode="fake")
    assert not report["passed"]
    assert report["fake_http_requests"] == 1
    assert len(world.sent) == (0 if case == "occluded" else 1)
    assert world.events[-2:] == ["input_cleanup", "app_cleanup"]
    assert not smoke.resources.DESKTOP_RESOURCE.lock.locked()
    if case == "cleanup_failed":
        with pytest.raises(RuntimeError, match="quarantined"):
            async with smoke.resources.DESKTOP_RESOURCE.acquire():
                pytest.fail("unconfirmed cleanup released usable desktop")


async def test_gui_smoke_annotation_is_not_a_dispatch_oracle(gui_smoke_world, monkeypatch, tmp_path):
    from benchmarks.computer_use import a_gui_smoke as smoke

    original = smoke.fake_reply
    monkeypatch.setattr(smoke, "fake_reply", lambda target: original({"center": [350, 450]}))
    gui_smoke_world.value = "9"
    output = tmp_path / "smoke"
    frozen = smoke.prepare(output)
    report = await smoke.run_batch(output, frozen["sha256"], mode="fake")
    assert report["row"]["schema_valid"] and not report["row"]["within_annotation"]
    assert report["click_returned"] and len(gui_smoke_world.sent) == 1
    assert not report["passed"]


async def test_gui_smoke_unknown_usage_keeps_reservation_without_click(gui_smoke_world, monkeypatch, tmp_path):
    import httpx
    from benchmarks.computer_use import a_gui_smoke as smoke

    monkeypatch.setattr(smoke, "fake_reply", lambda target: lambda request: httpx.Response(
        200, headers={"content-type": "text/event-stream"}, content="data: [DONE]\n\n"))
    output = tmp_path / "smoke"
    frozen = smoke.prepare(output)
    report = await smoke.run_batch(output, frozen["sha256"], mode="fake")
    assert not report["passed"] and not gui_smoke_world.sent
    assert report["fake_http_requests"] == 1
    assert report["spend"]["batch"]["reserved_nano_usd"] > 0
    assert report["application_cleanup"]["confirmed"]


async def test_gui_smoke_cancel_joins_cleanup_and_retains_report(gui_smoke_world, monkeypatch, tmp_path):
    import asyncio
    from benchmarks.computer_use import a_gui_smoke as smoke

    entered = asyncio.Event()
    async def blocked(request):
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(smoke, "fake_reply", lambda target: blocked)
    output = tmp_path / "smoke"
    frozen = smoke.prepare(output)
    pending = asyncio.create_task(smoke.run_batch(output, frozen["sha256"], mode="fake"))
    await asyncio.wait_for(entered.wait(), 5)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    report = json.loads((output / "result.json").read_text())
    assert report["status"] == "cancelled" and not report["passed"]
    assert report["application_cleanup"]["confirmed"]
    assert report["input_cleanup"]["confirmed"]
    assert gui_smoke_world.events[-2:] == ["input_cleanup", "app_cleanup"]
    assert not gui_smoke_world.sent


async def test_gui_smoke_ledger_close_error_retains_failed_report(gui_smoke_world, monkeypatch, tmp_path):
    from benchmarks.computer_use import a_gui_smoke as smoke

    close = smoke.SpendLedger.close
    def broken(self):
        close(self)
        raise OSError("journal unavailable")
    monkeypatch.setattr(smoke.SpendLedger, "close", broken)
    output = tmp_path / "smoke"
    frozen = smoke.prepare(output)
    with pytest.raises(OSError):
        await smoke.run_batch(output, frozen["sha256"], mode="fake")
    report = json.loads((output / "result.json").read_text())
    assert not report["passed"] and report["ledger_error"] == "OSError"
    assert report["row"]["usage"]["status"] == "returned"
    assert report["application_cleanup"]["confirmed"]


async def test_gui_smoke_waits_for_asynchronous_click_effect(gui_smoke_world, monkeypatch, tmp_path):
    from benchmarks.computer_use import a_gui_smoke as smoke

    original = smoke.s5.OwnedApplication.read_values_once
    reads = 0
    def delayed(self):
        nonlocal reads
        if gui_smoke_world.sent:
            reads += 1
            if reads < 3:
                return {"result": "0"}
        return original(self)
    monkeypatch.setattr(smoke.s5.OwnedApplication, "read_values_once", delayed)
    output = tmp_path / "smoke"
    frozen = smoke.prepare(output)
    report = await smoke.run_batch(output, frozen["sha256"], mode="fake")
    assert report["passed"] and reads == 3
    assert len(gui_smoke_world.sent) == 1


async def test_gui_smoke_task_deadline_cancels_pending_model(gui_smoke_world, monkeypatch, tmp_path):
    import asyncio
    from benchmarks.computer_use import a_gui_smoke as smoke

    original = smoke.freeze_inputs
    def short_recipe():
        frozen = original()
        frozen["seconds_per_task"] = 1
        return frozen
    async def stalled(request):
        await asyncio.Event().wait()
    monkeypatch.setattr(smoke, "freeze_inputs", short_recipe)
    monkeypatch.setattr(smoke, "fake_reply", lambda target: stalled)
    output = tmp_path / "smoke"
    frozen = smoke.prepare(output)
    report = await asyncio.wait_for(smoke.run_batch(output, frozen["sha256"], mode="fake"), 3)
    assert report["status"] == "error" and report["error"] == "TimeoutError"
    assert not report["passed"] and not gui_smoke_world.sent
    assert report["application_cleanup"]["confirmed"]


def test_hj_long_freeze_pins_independent_balanced_pairs(monkeypatch, tmp_path):
    s5 = _bootstrap(monkeypatch)
    output = tmp_path / "long"
    frozen = s5.prepare(output, track="hj-long")
    assert frozen["revision"] == "s5-hj-long-1"
    assert frozen["arms"] == ["H", "J"]
    assert len(frozen["tasks"]) == 20 and len(frozen["schedule"]) == 40
    assert frozen["nano_usd_limit"] == 1000000000
    assert frozen["request_limit"] == 1400
    assert frozen["decision_rule"]["minimum_strict_per_arm"] == 18
    assert frozen["statistics"]["comparisons"] == ["J-H"]
    for dispatch in ("ax_press", "quartz"):
        blocks = [frozen["schedule"][i:i+2] for i in range(0, 40, 2)
                  if frozen["schedule"][i]["task_id"].startswith(f"calculator-long-{dispatch}-")]
        assert len(blocks) == 10
        assert sum(block[0]["arm"] == "H" for block in blocks) == 5
        assert all({row["arm"] for row in block} == {"H", "J"} for block in blocks)
    assert s5.load_freeze(output, frozen["sha256"], track="hj-long") == frozen
    with pytest.raises(ValueError, match="freeze"):
        s5.load_freeze(output, frozen["sha256"])
    original = s5.freeze_inputs()
    assert original["revision"] == "s5-confirmatory-2"
    assert original["arms"] == ["A", "H", "J"] and len(original["schedule"]) == 150


@pytest.mark.parametrize("h_success,j_success,j_time,j_cost,decision", [
    (20, 19, 1100, 99, "long_task_point_gates_passed"),
    (19, 18, 1100, 99, "long_task_point_gates_passed"),
    (18, 17, 900, 99, "long_task_no_joint_gain"),
    (20, 18, 900, 99, "long_task_no_joint_gain"),
    (20, 20, 1101, 99, "long_task_cost_only"),
    (20, 20, 1000, 100, "long_task_no_joint_gain"),
])
def test_hj_long_verdict_has_independent_gates(monkeypatch, h_success, j_success, j_time, j_cost, decision):
    s5 = _bootstrap(monkeypatch)
    rules = s5.freeze_inputs(track="hj-long")["decision_rule"]
    summary = {"H": {"planned": 20, "finished": 20, "strict": h_success,
                      "elapsed_ms": 1000, "nano_usd": 100, "rule_violations": 0},
               "J": {"planned": 20, "finished": 20, "strict": j_success,
                      "elapsed_ms": j_time, "nano_usd": j_cost, "rule_violations": 0}}
    result = s5.long_verdict(summary, completed=True, mode="live", rules=rules)
    assert result["decision"] == decision
    assert result["h4"] is None and "h1" not in result
    for completed, mode in ((False, "live"), (True, "fake")):
        result = s5.long_verdict(summary, completed=completed, mode=mode, rules=rules)
        assert result["l1_time"] is None
        assert result["l2_quality"] is None
        assert result["l3_cost"] is None
    summary["J"]["rule_violations"] = 1
    assert not s5.long_verdict(summary, completed=True, mode="live", rules=rules)["l2_quality"]


async def test_hj_long_runs_shared_sdk_without_a(request, monkeypatch, tmp_path):
    from unittest.mock import Mock
    world = request.getfixturevalue("shared_world")
    s5 = _bootstrap(monkeypatch)
    monkeypatch.setattr(s5, "TASKS", tuple(s5.TASKS[30:32]))
    _install_fake_calculator(monkeypatch, s5, world)
    forbidden = Mock(side_effect=AssertionError("A must not be instantiated"))
    monkeypatch.setattr(s5, "create_a_driver", forbidden)
    output = tmp_path / "long"
    frozen = s5.prepare(output, track="hj-long")
    report = await s5.run_batch(output, frozen["sha256"], mode="fake", track="hj-long")
    assert report["completed"] and len(report["rows"]) == 4
    assert [r["arm"] for r in report["rows"]] == ["H", "J", "J", "H"]
    assert all(r["passed"] for r in report["rows"])
    assert all(r["independent_values"] == {"expression": "12×3-8+5", "result": "33"}
               for r in report["rows"])
    forbidden.assert_not_called()
    assert "A" not in report["summary"]
    assert set(report["summary"]["long_family"]) == {"H", "J"}
    assert all(not any(key.startswith("a_") for key in pair) for pair in report["paired"])
    assert len(report["paired"]) == 2
    assert set(report["statistics"]["long_family"]) == {"J-H"}
    assert report["confirmatory"]["h4"] is None
    assert report["conclusion"] == "fake_wiring_only_no_adoption_conclusion"
    assert report["external_model_requests"] == 0
    assert len(report["spend"]["trials"]) == 4
    for row in report["rows"]:
        assert row["application_cleanup"]["confirmed"]
        if row["arm"] == "H":
            assert all(c["provider"] != "jev" for c in row["calls"].values())
    with pytest.raises(FileExistsError):
        await s5.run_batch(output, frozen["sha256"], mode="fake", track="hj-long")


async def test_hj_long_environment_stop_retains_all_40_rows(request, monkeypatch, tmp_path):
    world = request.getfixturevalue("shared_world")
    s5 = _bootstrap(monkeypatch)
    _install_fake_calculator(monkeypatch, s5, world)
    def fail(owner):
        raise RuntimeError("owned application unavailable")
    monkeypatch.setattr(s5.OwnedApplication, "start", fail)
    output = tmp_path / "long"
    frozen = s5.prepare(output, track="hj-long")
    with pytest.raises(ValueError, match="freeze"):
        await s5.run_batch(output, frozen["sha256"], mode="fake")
    assert not (output / "started.json").exists()
    report = await s5.run_batch(output, frozen["sha256"], mode="fake", track="hj-long")
    assert not report["completed"] and len(report["rows"]) == 40
    assert report["rows"][0]["status"] == "environment_error"
    assert sum(r["status"] == "not_run" for r in report["rows"]) == 39
    assert report["summary"]["H"]["planned"] == report["summary"]["J"]["planned"] == 20
    assert not report["paired"] and not report["statistics"]["by_task"]
    assert report["conclusion"] == "incomplete_no_long_task_conclusion"
    assert report["fake_http_requests"] == report["external_model_requests"] == 0
    assert len((output / "rows.jsonl").read_text().splitlines()) == 40


async def test_hj_long_close_failure_retains_failed_report(request, monkeypatch, tmp_path):
    from tank_backend.benchmarks.spend_ledger import SpendLedger
    world = request.getfixturevalue("shared_world")
    s5 = _bootstrap(monkeypatch)
    monkeypatch.setattr(s5, "TASKS", (s5.TASKS[30],))
    _install_fake_calculator(monkeypatch, s5, world)
    close = SpendLedger.close
    def broken(self):
        close(self)
        raise OSError("journal close failed")
    monkeypatch.setattr(SpendLedger, "close", broken)
    output = tmp_path / "long"
    frozen = s5.prepare(output, track="hj-long")
    report = await s5.run_batch(output, frozen["sha256"], mode="fake", track="hj-long")
    assert report["ledger_close_error"] == "OSError"
    assert not report["completed"] and not report["paired"]
    assert report["conclusion"] == "incomplete_no_long_task_conclusion"
    assert len(report["rows"]) == 2
    saved = json.loads((output / "result.json").read_text())
    assert saved["ledger_close_error"] == "OSError" and not saved["completed"]
    assert not saved["paired"] and saved["spend"] == report["spend"]
    assert [(row["trial"], row["status"]) for row in saved["rows"]] == [
        (row["trial"], row["status"]) for row in report["rows"]
    ]


def test_intake_probe_freezes_balanced_text_only_comparison(monkeypatch, tmp_path):
    _bootstrap(monkeypatch)
    from benchmarks.computer_use import intake_probe as probe
    frozen = probe.prepare(tmp_path / "probe")
    assert len(frozen["schedule"]) == 12
    assert frozen["nano_usd_limit"] == 250000000 and frozen["request_limit"] == 12
    assert set(frozen["messages"]) == {"calculator", "literal-text"}
    for case in frozen["cases"]:
        messages = frozen["messages"][case["id"]]
        assert messages["legacy"][1] == messages["revised"][1]
        assert messages["legacy"][0] != messages["revised"][0]
        payload = json.loads(messages["revised"][1]["content"])
        assert set(payload) == {"request", "context", "application", "response_schema"}
        assert "expected" not in payload
    assert [r["arm"] for r in frozen["schedule"]].count("revised") == 6
    assert probe.load_freeze(tmp_path / "probe", frozen["sha256"]) == frozen
    with pytest.raises(ValueError):
        probe.load_freeze(tmp_path / "probe", "wrong")


async def test_intake_probe_sdk_continues_known_failures_without_gui(monkeypatch, tmp_path):
    from unittest.mock import Mock
    s5 = _bootstrap(monkeypatch)
    from benchmarks.computer_use import intake_probe as probe
    forbidden = Mock(side_effect=AssertionError("no desktop in intake probe"))
    monkeypatch.setattr(s5.OwnedApplication, "start", forbidden)
    monkeypatch.setattr(s5.computer_use_macos, "_capture_screenshot_macos", forbidden)
    output = tmp_path / "probe"
    frozen = probe.prepare(output)
    result = await probe.run_batch(output, frozen["sha256"], mode="fake")
    assert result["completed"] and len(result["rows"]) == 12
    assert result["summary"] == {"legacy": {"calculator": 0, "literal-text": 3},
                                  "revised": {"calculator": 3, "literal-text": 3}}
    assert result["verdict"] == "fake_wiring_only"
    assert result["fake_http_requests"] == 12 and result["external_model_requests"] == 0
    assert result["gui_operations"] == 0
    forbidden.assert_not_called()
    assert len(result["spend"]["trials"]) == 12
    for row in result["rows"]:
        request = next(iter(row["calls"].values()))["request"]
        assert request["messages"] == frozen["messages"][row["case_id"]][row["arm"]]
        assert request["max_tokens"] == 2048 and request["enable_thinking"] is False
    with pytest.raises(FileExistsError):
        await probe.run_batch(output, frozen["sha256"], mode="fake")


@pytest.mark.parametrize("failure", ["unknown", "bad_json", "wrong_literal", "changed_source"])
async def test_intake_probe_failure_and_gate_boundaries(monkeypatch, tmp_path, failure):
    import httpx
    _bootstrap(monkeypatch)
    from benchmarks.computer_use import intake_probe as probe
    original = probe.fake_text
    if failure == "bad_json":
        monkeypatch.setattr(probe, "fake_text", lambda case, row: "not json")
    elif failure == "wrong_literal":
        def wrong(case, row):
            answer = original(case, row)
            return answer.replace('\\n', '') if case["id"] == "literal-text" else answer
        monkeypatch.setattr(probe, "fake_text", wrong)
    elif failure == "unknown":
        monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda *a, **kw: httpx.MockTransport(
            lambda request: httpx.Response(500, json={"error": "synthetic"})))
    output = tmp_path / "probe"
    frozen = probe.prepare(output)
    if failure == "changed_source":
        monkeypatch.setattr(probe.intake, "INTAKE_SYSTEM", "changed")
        with pytest.raises(ValueError, match="freeze"):
            await probe.run_batch(output, frozen["sha256"], mode="fake")
        assert not (output / "started.json").exists()
        return
    result = await probe.run_batch(output, frozen["sha256"],
                                  mode="live" if failure == "unknown" else "fake", credential="offline")
    assert len(result["rows"]) == 12
    if failure == "unknown":
        assert not result["completed"] and result["external_model_requests"] == 1
        assert sum(r["status"] == "not_run" for r in result["rows"]) == 11
        assert result["spend"]["batch"]["reserved_nano_usd"] > 0
        assert result["verdict"] == "incomplete_no_conclusion"
    else:
        assert result["completed"] and result["fake_http_requests"] == 12
        assert result["summary"]["revised"]["literal-text"] == 0
        assert result["verdict"] == "fake_wiring_only"


async def test_intake_probe_cleanup_failure_retains_call_evidence(monkeypatch, tmp_path):
    from tank_backend.agents.task_runtime import TaskRuntime
    _bootstrap(monkeypatch)
    from benchmarks.computer_use import intake_probe as probe
    original = TaskRuntime.aclose
    async def broken(self):
        await original(self)
        raise OSError("client close failure")
    monkeypatch.setattr(TaskRuntime, "aclose", broken)
    output = tmp_path / "probe"
    frozen = probe.prepare(output)
    with pytest.raises(OSError):
        await probe.run_batch(output, frozen["sha256"], mode="fake")
    result = json.loads((output / "result.json").read_text())
    assert not result["completed"] and len(result["rows"]) == 12
    assert len(result["rows"][0]["calls"]) == 1
    assert result["rows"][0]["cleanup_error"] == "OSError"
    assert result["fake_http_requests"] == 1


@pytest.mark.parametrize("qualified", [True, False])
async def test_intake_probe_live_gate_uses_revised_all_six(monkeypatch, tmp_path, qualified):
    import httpx
    _bootstrap(monkeypatch)
    from benchmarks.computer_use import intake_probe as probe
    cases = json.loads((probe.FIXTURES / "cases.json").read_text())
    def reply(request):
        payload = json.loads(request.content)
        body = json.loads(payload["messages"][1]["content"])
        case = next(c for c in cases if c["request"] == body["request"])
        answer = probe.fake_text(case, {"arm": "revised", "repeat": 0})
        if not qualified and case["id"] == "literal-text":
            answer = answer.replace('\\n', '')
        return httpx.Response(200, json={"id": "offline", "object": "chat.completion",
            "created": 1, "model": payload["model"], "choices": [{"index": 0,
                "finish_reason": "stop", "message": {"role": "assistant", "content": answer}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17}})
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda *a, **kw: httpx.MockTransport(reply))
    output = tmp_path / "probe"
    frozen = probe.prepare(output)
    result = await probe.run_batch(output, frozen["sha256"], mode="live", credential="offline")
    assert result["completed"]
    assert result["verdict"] == ("prepare_gui_validation" if qualified else "revised_prompt_not_qualified")


async def test_intake_probe_cancel_preserves_denominator_and_reservation(monkeypatch, tmp_path):
    import asyncio
    import httpx
    _bootstrap(monkeypatch)
    from benchmarks.computer_use import intake_probe as probe
    entered = asyncio.Event()
    async def stalled(request: httpx.Request) -> httpx.Response:
        entered.set()
        await asyncio.Event().wait()
        raise AssertionError("stalled transport must be cancelled")
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda *a, **kw: httpx.MockTransport(stalled))
    output = tmp_path / "probe"
    frozen = probe.prepare(output)
    task = asyncio.create_task(probe.run_batch(output, frozen["sha256"], mode="live", credential="offline"))
    await asyncio.wait_for(entered.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    result = json.loads((output / "result.json").read_text())
    assert len(result["rows"]) == 12 and len(result["rows"][0]["calls"]) == 1
    assert result["spend"]["batch"]["reserved_nano_usd"] > 0
    assert result["verdict"] == "incomplete_no_conclusion"


def test_hj_context_freezes_four_tasks_and_full_intake(monkeypatch, tmp_path):
    s5 = _bootstrap(monkeypatch)
    output = tmp_path / "context"
    frozen = s5.prepare(output, track="hj-context")
    assert frozen["revision"] == "s5-hj-context-1"
    assert len(frozen["tasks"]) == 2 and len(frozen["schedule"]) == 4
    assert [r["arm"] for r in frozen["schedule"]] == ["H", "J", "J", "H"]
    assert frozen["request_limit"] == 140 and frozen["nano_usd_limit"] == 500000000
    assert frozen["decision_rule"]["planned_per_arm"] == 2
    assert frozen["statistics"]["comparisons"] == []
    for task in frozen["tasks"]:
        payload = json.loads(frozen["intake_messages"][task["id"]][1]["content"])
        assert payload["request"] == frozen["prompts"][task["id"]]
        assert payload["application"] == "com.apple.calculator"
        assert "--- Clarification ---" in payload["context"]
        assert "--- Security Rules ---" in payload["context"]
        assert "ENVIRONMENT:" in payload["context"]
    assert s5.load_freeze(output, frozen["sha256"], track="hj-context") == frozen
    for track in ("original", "hj-long"):
        with pytest.raises(ValueError, match="freeze"):
            s5.load_freeze(output, frozen["sha256"], track=track)


@pytest.mark.parametrize("change", ["none", "known_failure", "no_model_action", "rule_violation", "incomplete", "fake"])
def test_hj_context_gate_requires_all_four_without_adoption(monkeypatch, change):
    s5 = _bootstrap(monkeypatch)
    summary = {arm: {"planned": 2, "finished": 2, "strict": 2, "passed": 2,
                     "rule_violations": 0} for arm in ("H", "J")}
    if change == "known_failure":
        summary["H"]["strict"] = 1
    if change == "no_model_action":
        summary["J"]["passed"] = 1
    if change == "rule_violation":
        summary["J"]["rule_violations"] = 1
    result = s5.context_verdict(summary, completed=change != "incomplete",
                                mode="fake" if change == "fake" else "live")
    assert all(result[k] is None for k in ("l1_time", "l2_quality", "l3_cost", "h4"))
    assert result["decision"] == {
        "none": "prepare_hj_long_confirmation", "fake": "fake_wiring_only_no_adoption_conclusion",
        "incomplete": "incomplete_no_context_smoke_conclusion",
    }.get(change, "context_smoke_not_qualified")


@pytest.mark.parametrize("mismatch", [False, True])
async def test_hj_context_real_runner_binds_full_messages_before_http(request, monkeypatch, tmp_path, mismatch):
    from agent_computer_use.channels import native
    from tank_backend.agents.runner import AgentRunner
    world = request.getfixturevalue("shared_world")
    s5 = _bootstrap(monkeypatch)
    _install_fake_calculator(monkeypatch, s5, world)
    world.buttons = [replace(button, frame=(5 + index * 7, 10, 6, 10))
                     for index, button in enumerate(world.buttons)]
    def click(x, y, **kwargs):
        button = next(b for b in world.buttons if b.frame is not None
                      and b.frame[0] <= x < b.frame[0] + b.frame[2])
        native.ax_press(button.element)
    monkeypatch.setattr(native.macos, "_click_macos", click)
    builder = AgentRunner._build_sub_agent_prompt
    if mismatch:
        def changed(self, *args):
            text = builder(self, *args)
            return text + "\nChanged runtime context" if self._app_config is not None else text
        monkeypatch.setattr(AgentRunner, "_build_sub_agent_prompt", changed)
    output = tmp_path / "context"
    frozen = s5.prepare(output, track="hj-context")
    result = await s5.run_batch(output, frozen["sha256"], mode="fake", track="hj-context")
    assert len(result["rows"]) == 4 and result["external_model_requests"] == 0
    if mismatch:
        assert not result["completed"]
        assert result["spend"]["stop_reason"] == "intake_context_mismatch"
        assert result["fake_http_requests"] == result["spend"]["batch"]["admitted_requests"] == 0
        assert sum(r["status"] == "not_run" for r in result["rows"]) == 3
    else:
        assert result["completed"] and all(r["passed"] for r in result["rows"])
        assert result["conclusion"] == "fake_wiring_only_no_adoption_conclusion"
        assert all(result["confirmatory"][key] is None for key in ("l1_time", "l2_quality", "l3_cost", "h4"))
        assert len(result["paired"]) == 2
        assert result["statistics"] == {"by_task": {}, "long_family": {}}
        for row in result["rows"]:
            call = next(iter(row["calls"].values()))
            assert call["request"]["messages"] == frozen["intake_messages"][row["task_id"]]
            assert row["independent_values"] == {"expression": "12×3-8+5", "result": "33"}
            assert row["application_cleanup"]["confirmed"]


def test_hj_context_rejects_context_drift_before_execution(monkeypatch, tmp_path):
    from tank_backend.prompts.assembler import PromptAssembler
    s5 = _bootstrap(monkeypatch)
    output = tmp_path / "context"
    frozen = s5.prepare(output, track="hj-context")
    monkeypatch.setattr(PromptAssembler, "get_base_rules", lambda self: "changed base rules")
    with pytest.raises(ValueError, match="freeze"):
        s5.load_freeze(output, frozen["sha256"], track="hj-context")
    assert not (output / "started.json").exists()
