"""Local OCR: fake native Vision only, real PNG identity and M2 transforms."""

import io
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from tank_backend.tools.computer_observation import Observation
from .test_native import world as shared_world  # noqa: F401


@pytest.mark.parametrize("arm,outcome", [
    (arm, outcome) for arm in ("text", "image") for outcome in ("correct", "wrong", "abstain")
] + [("image", outcome) for outcome in ("revoked", "unknown", "stale", "scope", "receiver", "unstable")])
async def test_ablation_selector_uses_same_candidates_and_real_sdk_without_oracle(
    monkeypatch, shared_world, arm, outcome,  # noqa: F811
):
    import asyncio
    import json
    from dataclasses import replace
    from email.parser import BytesParser
    from email.policy import default
    from pathlib import Path
    import httpx2
    from agent_computer_use import create_subagent
    from agent_computer_use.channels import native
    from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext, SubAgentRequest
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.llm.model_data import ModelDataScope
    from .test_native import macos_policy
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_image_ablation as pilot

    shared_world.value = pilot.BODY
    shared_world.buttons = []
    shared_world.output = replace(shared_world.output, role="AXTextArea", identifier="First Text View", value_settable=True)
    monkeypatch.setattr(pilot.s4_ax.computer_ax, "ax_window_candidates", shared_world.read)
    image = io.BytesIO()
    Image.new("RGB", (100, 80), "white").save(image, "PNG")
    monkeypatch.setattr(native.macos, "_capture_screenshot_macos", lambda **kwargs: image.getvalue())
    calls = []
    png_bytes = image.getvalue()
    captures = 0
    def screenshot(**kwargs):
        nonlocal captures
        captures += 1
        if outcome == "unstable" and captures % 2 == 0:
            changed = io.BytesIO()
            Image.new("RGB", (100, 80), "black").save(changed, "PNG")
            return changed.getvalue()
        return png_bytes
    monkeypatch.setattr(native.macos, "_capture_screenshot_macos", screenshot)

    def respond(request):
        nonlocal png_bytes
        if arm == "image":
            assert request.headers["TypeSafe-Danger-Zone-Images"] == "true"
            message = BytesParser(policy=default).parsebytes(
                ("Content-Type: " + request.headers["content-type"] + "\r\n\r\n").encode() + request.content)
            parts = list(message.iter_parts())
            assert len(parts) == 2
            raw = parts[0].get_payload(decode=True)
            assert isinstance(raw, bytes)
            payload = json.loads(raw)
            assert "image" in payload["state"]
        else:
            payload = json.loads(request.content)
            assert "TypeSafe-Danger-Zone-Images" not in request.headers
            assert "image" not in payload["state"]
        calls.append(payload)
        assert "completion" not in payload["state"]["goal"]
        assert payload["state"]["full_ax"]["elements"][0]["identifier"] == "First Text View"
        criteria = payload["questions"]["next_action"]["criteria"]
        assert {v["value"] for v in criteria.values() if isinstance(v, dict)} == set(pilot.VARIANTS.values())
        choice = ("need_more_context" if outcome == "abstain" else next(k for k, v in criteria.items()
            if isinstance(v, dict) and v["value"] == pilot.VARIANTS["south" if outcome == "wrong" else "north"]))
        reply = {"model": "jev-1.14.0", "answers": {"next_action": {
            "type": "choice", "choice": choice, "confidence": 1,
            "probabilities": {k: float(k == choice) for k in criteria}}},
            "usage": {"input_tokens": 10, "output_tokens": 2}}
        if outcome == "unknown":
            reply.pop("usage")
        elif outcome == "revoked":
            context.authorization.revoke()
        elif outcome == "stale":
            changed = io.BytesIO()
            Image.new("RGB", (100, 80), "black").save(changed, "PNG")
            png_bytes = changed.getvalue()
        return httpx2.Response(200, json=reply)

    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kwargs: httpx2.MockTransport(respond))
    context = SubAgentContext(SubAgentAuthorization(frozenset({"desktop", "network"})), SubAgentBudget(),
        asyncio.Event(), max_actions=2, model_data_scope=ModelDataScope(
            frozenset({"text"} if outcome == "scope" else {"text", "image"})))
    context.runtime.configure_decision_model("task", DecisionModelProfile(
        "https://offline.invalid/v1/systemone", "jev-1.14.0", "KEY", images=outcome != "receiver"), credential="fixture")
    plugin = create_subagent({"macos": macos_policy(labels="identifier", readouts=[
        {"name": "document", "role": "AXTextArea", "identifier": "First Text View"}])})
    assert isinstance(plugin.controller.source, native.NativeAXChannel)
    selector = pilot.PairedSelector(plugin.controller.source, arm)
    selector.register(context)
    plugin.controller.selector = selector
    trial = {"id": "task", "scene": "scene-01", "arm": arm}
    task = pilot.goal(trial, pilot.VARIANTS["north"])
    task["scope"] = "counter"
    task["target"] = {"application": "test.counter"}
    try:
        outputs = [o async for o in plugin.run(SubAgentRequest(pilot.INSTRUCTION, "", "task", task), context)]
        result = outputs[-1].metadata["task_result"]
        if outcome in {"correct", "wrong"}:
            assert (result["status"] == "completed") == (outcome == "correct"), result
            assert shared_world.sent == [("fill", pilot.VARIANTS["south" if outcome == "wrong" else "north"])]
        else:
            assert result["status"] != "completed" and not shared_world.sent, result
        assert len(calls) == (0 if outcome in {"scope", "receiver", "unstable"} else 1)
        assert bool(context.budget.unknown_calls) == (outcome == "unknown")
        if outcome == "unstable":
            assert len(selector.captures) == 3
        if outcome not in {"scope", "receiver", "unknown", "unstable"}:
            assert context.budget.total_tokens == 12
    finally:
        await plugin.aclose()
        await context.runtime.aclose()


@pytest.mark.parametrize("selected", ["Jev visual probe", "North"])
def test_ablation_selects_only_neutral_header_and_verifies_setup(monkeypatch, shared_world, selected):  # noqa: F811
    import json
    from pathlib import Path
    from dataclasses import replace
    from agent_computer_use.channels import native
    from .test_native import native_config
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_image_ablation as pilot
    shared_world.value = pilot.BODY
    shared_world.buttons = []
    shared_world.output = replace(shared_world.output, role="AXTextArea", identifier="First Text View")
    monkeypatch.setattr(pilot.s4_ax.computer_ax, "ax_window_candidates", shared_world.read)
    writes = []
    monkeypatch.setattr(pilot.s4_ax.computer_ax, "_load_ax", lambda: {
        "AXUIElementSetAttributeValue": lambda ref, key, value: writes.append((key, value)) or 0,
        "AXUIElementCopyAttributeValue": lambda ref, key, out: (0, selected)})
    foundation = SimpleNamespace(NSBundle=SimpleNamespace(bundleWithPath_=lambda path: "bundle"))
    objc = SimpleNamespace(loadBundleFunctions=lambda bundle, functions, spec: functions.update(
        AXValueCreate=lambda kind, value: value))
    original = pilot.importlib.import_module
    monkeypatch.setattr(pilot.importlib, "import_module", lambda name:
        {"Foundation": foundation, "objc": objc}.get(name) or original(name))
    monkeypatch.setattr(pilot.s4_ax, "pump", lambda *args: None)
    owner = pilot.s4_ax.OwnedApplication(pilot.s4_ax.CASES[0])
    owner.pid = 42
    monkeypatch.setattr(owner, "read_values", lambda: {"document": shared_world.value})
    config = native.NativeConfig.model_validate_json(json.dumps(native_config()))
    if selected == "North":
        with pytest.raises(RuntimeError, match="header selection"):
            pilot.select_heading(owner, config)
        assert not owner.setup_actions
    else:
        pilot.select_heading(owner, config)
        assert owner.setup_actions == ["select_neutral_header"]
    assert writes == [("AXSelectedTextRange", (0, len("Jev visual probe")))]
    assert shared_world.value == pilot.BODY


@pytest.mark.parametrize("unknown,blocked", [(False, False), (True, False), (False, True)])
async def test_ablation_batch_governs_all_real_sdk_calls_and_stops_unknown(
    monkeypatch, shared_world, tmp_path, unknown, blocked,  # noqa: F811
):
    import json
    from pathlib import Path
    from dataclasses import replace
    from contextlib import contextmanager
    import httpx2
    from agent_computer_use.channels import native
    from tank_backend.agents import resources
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_image_ablation as pilot

    shared_world.value = pilot.BODY
    shared_world.buttons = []
    shared_world.output = replace(shared_world.output, role="AXTextArea", identifier="First Text View", value_settable=True)
    monkeypatch.setattr(pilot.s4_ax.computer_ax, "ax_window_candidates", shared_world.read)
    monkeypatch.setattr(pilot.s4_ax.computer_use_macos, "_active_displays", lambda: (shared_world.window.display_geometry,))
    image = io.BytesIO()
    Image.new("RGB", (100, 80), "white").save(image, "PNG")
    monkeypatch.setattr(native.macos, "_capture_screenshot_macos", lambda **kwargs: image.getvalue())
    closed = []
    idle = True
    monkeypatch.setattr(native, "inputs_idle", lambda: idle)

    class Owner:
        pid = 42
        setup_actions = []

        def __init__(self, case, *, rtf):
            self.case = case
            assert b"\\rtf1" in rtf

        def start(self):
            nonlocal idle
            idle = True
            shared_world.value = pilot.BODY
            return native.NativeConfig.model_validate_json(json.dumps({
                "scope": self.case["id"], "bundle_id": "com.apple.TextEdit", "pid": 42,
                "process_start": "1:0", "window_id": 7, "labels": "identifier",
                "readouts": pilot.s4_ax.channel_readouts("textedit")}))

        def read_values(self):
            return {"document": shared_world.value}

        def bound_ax_window(self, api):
            return "window"

        def close(self):
            closed.append(self.case["id"])
            return {"confirmed": True}

    def attribute(element, key, out):
        attrs = ({"AXRole": "AXWindow", "AXChildren": [shared_world.output.element.native, "italic", "align left", "align center", "align right", "fully justify"]}
                 if element == "window" else {"AXRole": "AXTextArea", "AXIdentifier": "First Text View", "AXSelectedText": "Jev visual probe"}
                 if element is shared_world.output.element.native else {
                     "AXRole": "AXCheckBox", "AXDescription": element, "AXPosition": (10, 10), "AXSize": (20, 20)})
        return 0, attrs.get(key)

    monkeypatch.setattr(pilot.s4_ax, "OwnedApplication", Owner)
    monkeypatch.setattr(pilot.s4_ax.computer_ax, "_load_ax", lambda: {
        "AXUIElementGetPid": lambda element, out: (0, 42), "AXUIElementCopyAttributeValue": attribute,
        "AXUIElementSetAttributeValue": lambda *args: 0})
    foundation = SimpleNamespace(NSBundle=SimpleNamespace(bundleWithPath_=lambda path: "bundle"))
    objc = SimpleNamespace(loadBundleFunctions=lambda bundle, functions, spec: functions.update(
        AXValueCreate=lambda kind, value: value))
    original_import = pilot.importlib.import_module
    monkeypatch.setattr(pilot.importlib, "import_module", lambda name:
        {"Foundation": foundation, "objc": objc}.get(name) or original_import(name))
    monkeypatch.setattr(pilot.s4_ax, "pump", lambda *args: None)
    monkeypatch.setattr(resources, "DESKTOP_RESOURCE", resources.DesktopResource())
    if unknown or blocked:
        original = pilot.s4_ax.fake_model_http

        @contextmanager
        def missing_usage(respond):
            async def changed(request):
                nonlocal idle
                response = await respond(request)
                payload = response.json()
                if unknown:
                    payload.pop("usage")
                    answer = payload["answers"]["next_action"]
                    answer["choice"] = "c1"
                    answer["probabilities"] = {k: float(k == "c1") for k in answer["probabilities"]}
                elif request.headers["content-type"].startswith("multipart/") and "next_action" in payload["answers"]:
                    idle = False
                return httpx2.Response(200, json=payload)
            with original(changed):
                yield
        monkeypatch.setattr(pilot.s4_ax, "fake_model_http", missing_usage)
    root = tmp_path / "pilot"
    frozen = pilot.prepare(root)
    report = await pilot.run_batch(root, frozen["sha256"], mode="fake")
    assert len(report["rows"]) == 10 and sum(len(r.get("boxes", [])) for r in report["rows"]) == 6
    assert report["completed"] == (not unknown), report.get("spend")
    calls = [json.loads(line) for line in (root / "calls.jsonl").read_text().splitlines()]
    requests = [r for r in calls if "request" in r]
    if unknown:
        assert len(requests) == len(closed) == 1 and not shared_world.sent
        assert report["spend"]["stop_reason"] == "unknown_usage"
        assert report["spend"]["batch"]["reserved_tokens"] > 0
        assert all(r["status"] == "not_run" for r in report["rows"][1:])
    else:
        assert len(requests) == 14 and len(closed) == 10
        image_rows = [r for r in report["rows"] if r["kind"] == "task" and r["arm"] == "image"]
        assert sum(r["passed"] for r in image_rows) == (0 if blocked else 4)
        assert all(r["model_correct"] for r in image_rows)
        if blocked:
            assert all(not r["native_actions"] and r["result"]["reason"] == "not_sent" for r in image_rows)
        assert all(r.get("model_abstained") and not r["native_actions"] for r in report["rows"] if r["arm"] == "text")
        assert all(not r["native_actions"] for r in report["rows"] if r["kind"] == "box")
        assert report["spend"]["batch"]["known_tokens"] == 14 * 12
        assert report["spend"]["batch"]["known_nano_usd"] == 14 * 10 * 42
        assert report["spend"]["batch"]["reserved_tokens"] == 0


@pytest.mark.parametrize("cleanup", [True, False])
async def test_ablation_setup_failure_keeps_all_task_and_box_denominators(monkeypatch, tmp_path, cleanup):
    from pathlib import Path
    from tank_backend.agents import resources
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_image_ablation as pilot

    closed = []
    class Owner:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise RuntimeError("setup unavailable")

        def close(self):
            closed.append(True)
            return {"confirmed": cleanup}

    monkeypatch.setattr(pilot.s4_ax, "OwnedApplication", Owner)
    monkeypatch.setattr(resources, "DESKTOP_RESOURCE", resources.DesktopResource())
    root = tmp_path / "pilot"
    frozen = pilot.prepare(root)
    report = await pilot.run_batch(root, frozen["sha256"], mode="fake")
    assert not report["completed"] and report["spend"]["batch"]["admitted_requests"] == 0
    assert len(report["rows"]) == 10 and closed == [True]
    assert report["rows"][0]["cleanup_confirmed"] == cleanup
    assert [r["status"] for r in report["rows"]] == ["error"] + ["not_run"] * 9
    assert sum(len(r.get("boxes", [])) for r in report["rows"]) == 6
    with pytest.raises(FileExistsError):
        await pilot.run_batch(root, frozen["sha256"], mode="fake")


async def test_ablation_live_preflight_refuses_before_marker_or_client(monkeypatch, tmp_path):
    from pathlib import Path
    import httpx2
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_image_ablation as pilot
    def refuse():
        raise RuntimeError("desktop locked")
    def forbidden(*args, **kwargs):
        raise AssertionError("preflight cannot create a client")
    monkeypatch.setattr(pilot, "preflight", refuse)
    monkeypatch.setattr(httpx2, "AsyncClient", forbidden)
    root = tmp_path / "pilot"
    frozen = pilot.prepare(root)
    with pytest.raises(RuntimeError, match="desktop locked"):
        await pilot.run_batch(root, frozen["sha256"], mode="live", credential="fixture")
    assert not (root / "started.json").exists()


def test_ablation_public_question_keeps_both_variants_and_hides_private_completion(monkeypatch):
    from pathlib import Path
    from agent_computer_use.action_builder import ActionBuilder
    from agent_computer_use.contracts import Element, Fact, GoalContract, Snapshot
    from agent_computer_use.jev_image import normalize_frame
    from agent_computer_use.visual_selector import VisualFrame
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_image_ablation as pilot

    trial = pilot.trials()[0]
    raw = pilot.goal(trial, pilot.VARIANTS["north"])
    raw.pop("target")
    goal = GoalContract.from_input(raw)
    snapshot = Snapshot("obs", goal.scope, 0, (
        Element("body", "textbox", "First Text View", ("fill",), source="ax", value=pilot.BODY),),
        facts=(Fact(key="ax:value:document", value=pilot.BODY),))
    actions = ActionBuilder().build(goal.goal_id, 1, goal, snapshot)
    stream = io.BytesIO()
    Image.new("RGB", (100, 80), "white").save(stream, format="PNG")
    frame, png = Observation.capture(stream.getvalue(), session_id="task", display_id=5)
    image = normalize_frame(VisualFrame("obs", frame, png, (("body", (5, 5, 90, 70)),)))
    extra = {"incomplete": True, "elements": [{"description": "bold", "value": ""}]}
    first = pilot.question(goal, snapshot, actions, image, extra)
    changed = goal.model_copy(update={"completion": (Fact(key="ax:value:document", value=pilot.VARIANTS["south"]),)})
    assert pilot.question(changed, snapshot, actions, image, extra) == first
    assert "completion" not in first["state"]["goal"]
    assert first["state"]["full_ax"] == extra
    choices = first["questions"]["next_action"]["criteria"]
    assert {v["value"] for v in choices.values() if isinstance(v, dict)} == set(pilot.VARIANTS.values())
    assert list(first["state"]["image_candidates"].values()) == [[17.5, 17.5, 315.0, 245.0]] * 2


def test_real_app_ablation_prepares_private_oracle_without_clients_or_desktop(monkeypatch, tmp_path):
    import json
    from pathlib import Path
    import httpx2
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_image_ablation as pilot

    def forbidden(*args, **kwargs):
        raise AssertionError("prepare is offline")

    monkeypatch.setattr(pilot.s4_ax.OwnedApplication, "start", forbidden)
    monkeypatch.setattr(httpx2, "AsyncClient", forbidden)
    root = tmp_path / "pilot"
    frozen = pilot.prepare(root)
    assert len(frozen["trials"]) == 10
    assert [t["arm"] for t in frozen["trials"]].count("text") == 4
    assert frozen["request_limit"] == 14 and frozen["nano_usd_limit"] == 100_000_000
    assert pilot.load_freeze(root, frozen["sha256"]) == frozen
    assert b"\\red220" in (root / "private/scene-01.rtf").read_bytes()
    public = json.loads((root / "public.json").read_text())
    assert "expected_body" not in json.dumps(public)
    (root / "private/labels.json").write_text('{}')
    with pytest.raises(ValueError, match="freeze changed"):
        pilot.load_freeze(root, frozen["sha256"])


def test_real_application_image_recipe_prepares_without_desktop_or_clients(monkeypatch, tmp_path):
    import json
    from pathlib import Path
    import httpx
    import httpx2
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_image_native as pilot

    def forbidden(*args, **kwargs):
        raise AssertionError("offline preparation cannot open clients or applications")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    monkeypatch.setattr(httpx2, "AsyncClient", forbidden)
    monkeypatch.setattr(pilot.OwnedApplication, "start", forbidden)
    root = tmp_path / "pilot"
    frozen = pilot.prepare(root)
    assert frozen["request_limit"] == 26 and frozen["nano_usd_limit"] == 100_000_000
    assert [case["expression"] for case in frozen["cases"]] == ["7×8", "12+34"]
    assert frozen["application"]["bundle_id"] == "com.apple.calculator"
    assert pilot.load_freeze(root, frozen["sha256"]) == frozen
    assert not (root / "started.json").exists()
    frozen["cases"][0]["result"] = "57"
    (root / "freeze.json").write_text(json.dumps(frozen))
    with pytest.raises(ValueError, match="freeze changed"):
        pilot.load_freeze(root, frozen["sha256"])


def test_native_image_freeze_rejects_changed_selector_gate(monkeypatch, tmp_path):
    from pathlib import Path
    from agent_computer_use import model_selector
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_image_native as pilot

    root = tmp_path / "pilot"
    frozen = pilot.prepare(root)
    source = Path(model_selector.__file__)
    original = Path.read_bytes

    def changed(path):
        data = original(path)
        return data + b"\n# changed selector gate\n" if path == source else data

    monkeypatch.setattr(Path, "read_bytes", changed)
    with pytest.raises(ValueError, match="freeze changed"):
        pilot.load_freeze(root, frozen["sha256"])


@pytest.mark.parametrize("cleanup_confirmed", [True, False])
async def test_native_image_setup_failure_preserves_tasks_and_closes_owner(monkeypatch, tmp_path, cleanup_confirmed):
    from pathlib import Path
    from tank_backend.agents import resources
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_image_native as pilot

    closed = []
    class Owner:
        def __init__(self, case):
            pass

        def start(self):
            raise RuntimeError("native setup unavailable")

        def close(self):
            closed.append(True)
            return {"confirmed": cleanup_confirmed}

    monkeypatch.setattr(pilot, "OwnedApplication", Owner)
    monkeypatch.setattr(resources, "DESKTOP_RESOURCE", resources.DesktopResource())
    root = tmp_path / "pilot"
    frozen = pilot.prepare(root)
    report = await pilot.run_batch(root, frozen["sha256"], mode="fake")
    assert not report["completed"] and not report["all_passed"]
    assert [row["status"] for row in report["rows"]] == ["error", "not_run"]
    assert report["rows"][0]["cleanup_confirmed"] == cleanup_confirmed
    assert closed == [True] and report["spend"]["batch"]["admitted_requests"] == 0
    with pytest.raises(FileExistsError):
        await pilot.run_batch(root, frozen["sha256"], mode="fake")


async def test_native_image_live_preflight_refuses_before_marker_or_client(monkeypatch, tmp_path):
    from pathlib import Path
    import httpx2
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_image_native as pilot

    def denied():
        raise RuntimeError("OS access denied")

    def forbidden(*args, **kwargs):
        raise AssertionError("preflight refusal cannot create a client")

    monkeypatch.setattr(pilot, "preflight", denied)
    monkeypatch.setattr(httpx2, "AsyncClient", forbidden)
    root = tmp_path / "pilot"
    frozen = pilot.prepare(root)
    with pytest.raises(RuntimeError, match="OS access denied"):
        await pilot.run_batch(root, frozen["sha256"], mode="live", credential="test")
    assert not (root / "started.json").exists()


@pytest.mark.parametrize("count,failure", [(3, None), (5, None)] + [
    (3, failure) for failure in ("scope", "receiver", "stale_image", "revoked", "unknown",
                                "unoffered", "abstain", "bounds", "effect_unknown", "settle", "unstable", "padding")])
async def test_jev_native_image_factory_executes_bound_candidates(
    monkeypatch, shared_world, count, failure,  # noqa: F811
):
    import asyncio
    import json
    from email.parser import BytesParser
    from email.policy import default
    import httpx2
    from agent_computer_use import create_subagent
    from tank_backend.agents.subagent import (
        SubAgentAuthorization, SubAgentBudget, SubAgentContext, SubAgentRequest,
    )
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.llm.model_data import ModelDataScope
    from .test_native import goal, macos_policy, targeted

    requests = []

    def respond(request):
        nonlocal png_bytes
        assert request.headers["TypeSafe-Danger-Zone-Images"] == "true"
        message = BytesParser(policy=default).parsebytes(
            ("Content-Type: " + request.headers["content-type"] + "\r\n\r\n").encode()
            + request.content)
        parts = list(message.iter_parts())
        raw = parts[0].get_payload(decode=True)
        assert isinstance(raw, bytes)
        body = json.loads(raw)
        requests.append(body)
        assert len(parts) == 2
        expected_bounds = [7.84, 108.8, 15.68, 15.6] if failure == "padding" else [35, 35, 70, 70]
        assert body["state"]["image_candidates"]["c1"] == pytest.approx(expected_bounds)
        criteria = body["questions"]["next_action"]["criteria"]
        choice = "none" if failure == "abstain" else "invented" if failure == "unoffered" else "c1"
        reply = {"model": "jev-1.14.0", "answers": {
            "next_action": {"type": "choice", "choice": choice, "confidence": 1.0,
                "probabilities": {key: float(key == choice) for key in criteria}}},
            "usage": {"input_tokens": 7, "output_tokens": 0}}
        if failure == "stale_image":
            changed = io.BytesIO()
            Image.new("RGB", (100, 80), "black").save(changed, "PNG")
            png_bytes = changed.getvalue()
        elif failure == "revoked":
            context.authorization.revoke()
        elif failure == "unknown":
            reply.pop("usage")
        return httpx2.Response(200, json=reply)

    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kwargs: httpx2.MockTransport(respond))
    size = (100, 80)
    if failure == "padding":
        from dataclasses import replace
        size = (2000, 100)
        shared_world.window = replace(shared_world.window, bounds=(0, 0, *size),
            display_geometry=(5, 0, 0, *size, *size))
    png = io.BytesIO()
    Image.new("RGB", size, "white").save(png, "PNG")
    png_bytes = png.getvalue()
    captures = 0
    def screenshot(**kwargs):
        nonlocal captures
        captures += 1
        if failure in {"settle", "unstable"} and captures > 1 and (
            failure == "settle" or captures % 2 == 0
        ):
            changed = io.BytesIO()
            Image.new("RGB", (100, 80), "black").save(changed, "PNG")
            return changed.getvalue()
        return png_bytes
    monkeypatch.setattr("agent_computer_use.channels.native.macos._capture_screenshot_macos",
                        screenshot)
    context = SubAgentContext(SubAgentAuthorization(frozenset({"desktop", "network"})),
        SubAgentBudget(), asyncio.Event(),
        model_data_scope=ModelDataScope(frozenset({"text"} if failure == "scope" else {"text", "image"})))
    context.runtime.configure_decision_model("task", DecisionModelProfile(
        "https://offline.invalid/v1/systemone", "jev-1.14.0", "KEY", images=failure != "receiver"),
        credential="test")
    plugin = create_subagent({"macos": macos_policy(), "selector": "jev-image", "advisor": "jev-image"})
    if failure == "effect_unknown":
        monkeypatch.setattr("agent_computer_use.channels.native.ax_press",
                            lambda ref: shared_world.sent.append(("press", ref)))
    elif failure == "bounds":
        from dataclasses import replace
        from agent_computer_use.channels.native import NativeAXChannel
        channel = plugin.controller.source
        assert isinstance(channel, NativeAXChannel)
        capture = channel.capture
        async def outside(snapshot, context):
            frame = await capture(snapshot, context)
            return replace(frame, bounds=tuple((ref, (90, 10, 20, 20)) for ref, _ in frame.bounds))
        monkeypatch.setattr(channel, "capture", outside)
    task = goal().model_dump(mode="json")
    task["completion"][0]["value"] = str(count)
    try:
        outputs = [o async for o in plugin.run(SubAgentRequest(
            "Increment to the requested result", "", "task", targeted(task)), context)]
        result = outputs[-1].metadata["task_result"]
        if failure and failure not in {"settle", "padding"}:
            expected = {"scope": "model_data_denied", "receiver": "decision_images_denied",
                "stale_image": "stale_reference", "revoked": "error", "unknown": "invalid_decision",
                "unoffered": "invalid_decision", "abstain": "none",
                "bounds": "visual_target_unavailable", "effect_unknown": "effect_unknown",
                "unstable": "unstable_visual_frame"}
            assert result["reason"] == expected[failure], result
            assert len(shared_world.sent) == (1 if failure == "effect_unknown" else 0)
            assert len(requests) == (0 if failure in {"scope", "receiver", "bounds", "unstable"} else 1)
            assert bool(context.budget.unknown_calls) == (failure == "unknown")
            return
        assert result["status"] == "completed"
        assert shared_world.value == str(count) and len(shared_world.sent) == count
        assert len(requests) == count and context.budget.total_tokens == 7 * count
        if count == 5:
            assert requests[3]["state"]["selection_reason"] == "goal_progress_unverified"
    finally:
        await plugin.aclose()
        await context.runtime.aclose()


def test_qwen_location_contract_uses_declared_thousand_scale(monkeypatch):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_image_eval as evaluation

    answer = evaluation.parse_location('{"cardinality":"one","bbox_2d":[100,340,360,520]}')
    assert answer == {"cardinality": "one", "box": [0.1, 0.34, 0.36, 0.52]}
    assert evaluation.parse_location('{"cardinality":"none","bbox_2d":null}') == {
        "cardinality": "none", "box": None}
    # Small coordinates still mean thousandths, never an inferred 0-1 scale.
    assert evaluation.parse_location('{"cardinality":"one","bbox_2d":[0.1,0.2,0.3,0.4]}')["box"] == [
        0.0001, 0.0002, 0.0003, 0.0004]


@pytest.mark.parametrize("answer", [
    '```json\n{"cardinality":"one","bbox_2d":[100,200,300,400]}\n```',
    '{"cardinality":"one","test":[100,200,300,400]}',
    '{"cardinality":"one","box":[0.1,0.2,0.3,0.4]}',
    '{"cardinality":"one","bbox_2d":[-1,200,300,400]}',
    '{"cardinality":"one","bbox_2d":[100,200,1001,400]}',
    '{"cardinality":"one","bbox_2d":[' + '9' * 400 + ',200,300,400]}',
    '{"cardinality":"one","bbox_2d":[true,200,300,400]}',
    '{"cardinality":"one","bbox_2d":[100,200,100,400]}',
    '{"cardinality":"one","bbox_2d":null}',
    '{"cardinality":"none","bbox_2d":[100,200,300,400]}',
    '{"cardinality":"several","bbox_2d":[100,200,300,400]}',
    '{"cardinality":"one","bbox_2d":[100,200,300,400],"units":"pixels"}',
    '{"cardinality":"one","cardinality":"none","bbox_2d":null}',
])
def test_qwen_location_contract_refuses_repair_and_ambiguous_geometry(monkeypatch, answer):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_image_eval as evaluation

    with pytest.raises(ValueError):
        evaluation.parse_location(answer)


def test_image_evaluation_prepares_five_arms_without_clients(monkeypatch, tmp_path):
    import json
    from pathlib import Path
    import httpx
    import httpx2

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_image_eval as evaluation

    def forbidden(*args, **kwargs):
        raise AssertionError("preparation must not allocate network clients")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    monkeypatch.setattr(httpx2, "AsyncClient", forbidden)
    output = tmp_path / "evaluation"
    frozen = evaluation.prepare(output)
    assert frozen["revision"] == "jev-image-evaluation-2"
    assert frozen["qwen_output_contract"]["coordinate_scale"] == 1000
    assert frozen["request_limit"] == 260
    assert len(frozen["schedule"]) == 300
    assert {row["arm"] for row in frozen["schedule"]} == {
        "text13", "text14", "image14", "box14", "qwen_box"}
    assert evaluation.load_freeze(output, frozen["sha256"]) == frozen
    previews = json.loads((output / "previews.json").read_text())
    assert len(previews) == 260
    assert "expected_choice" not in json.dumps(previews)
    assert "clickable_regions" not in json.dumps(previews)
    qwen = previews["dev-001-1-qwen_box"]
    assert qwen["response_format"] == {"type": "json_object"}
    assert "0-1000" in qwen["messages"][0]["content"]
    assert not (output / "started.json").exists()
    with pytest.raises(FileExistsError):
        evaluation.prepare(output)


def test_image_evaluation_refuses_a_differently_labeled_protocol(monkeypatch, tmp_path):
    import json
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_image_eval as evaluation

    output = tmp_path / "evaluation"
    frozen = evaluation.prepare(output)
    frozen["revision"] = "jev-image-evaluation-1"
    frozen["sha256"] = evaluation.dev.digest({k: v for k, v in frozen.items() if k != "sha256"})
    (output / "freeze.json").write_text(json.dumps(frozen))
    with pytest.raises(ValueError, match="freeze changed"):
        evaluation.load_freeze(output, frozen["sha256"])


@pytest.mark.parametrize("qwen_overflow", [False, True])
async def test_image_evaluation_runs_real_sdks_and_scores_without_gui(
    monkeypatch, tmp_path, qwen_overflow,
):
    import json
    from email.parser import BytesParser
    from email.policy import default
    from pathlib import Path
    import httpx
    import httpx2

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_image_eval as evaluation

    sent = []

    def payload(request):
        if "multipart" in request.headers.get("content-type", ""):
            message = BytesParser(policy=default).parsebytes(
                ("Content-Type: " + request.headers["content-type"] + "\r\n\r\n").encode()
                + request.content)
            parts = list(message.iter_parts())
            assert len(parts) == 2 and parts[1].get_content_type() == "image/png"
            raw = parts[0].get_payload(decode=True)
            assert isinstance(raw, bytes)
            return json.loads(raw)
        return json.loads(request.content)

    def respond(request):
        data = payload(request)
        sent.append(data)
        if "messages" in data:
            assert data["response_format"] == {"type": "json_object"}
            return httpx.Response(200, json={
                "id": "evaluation", "object": "chat.completion", "created": 1,
                "model": data["model"], "choices": [{"index": 0, "finish_reason": "stop",
                    "message": {"role": "assistant", "content": json.dumps({
                        "cardinality": "one", "bbox_2d": [
                            10**400 if qwen_overflow else 100, 340, 360, 520]})}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
        criteria = data["questions"].get("next_action", {}).get("criteria")
        if criteria:
            selected = "c1" if "c1" in criteria else "none"
            answers = {"next_action": {"type": "choice", "choice": selected,
                "confidence": 1.0, "probabilities": {key: float(key == selected) for key in criteria}}}
        else:
            answers = {
                "cardinality": {"type": "choice", "choice": "one", "confidence": 1.0,
                    "probabilities": {"none": 0.0, "one": 1.0, "several": 0.0}},
                "target": {"type": "box", "box": {
                    "left": 0.1, "top": 0.34, "right": 0.36, "bottom": 0.52}, "confidence": 0.8}}
        return httpx2.Response(200, json={"model": data["model"], "answers": answers,
                                         "usage": {"input_tokens": 10, "output_tokens": 5}})

    def text_http(request: httpx.Request) -> httpx.Response:
        response = respond(request)
        return httpx.Response(response.status_code, content=response.content)

    def image_http(request: httpx2.Request) -> httpx2.Response:
        response = respond(request)
        return httpx2.Response(response.status_code, content=response.content)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda **kwargs: httpx.MockTransport(text_http))
    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kwargs: httpx2.MockTransport(image_http))
    output = tmp_path / "evaluation"
    frozen = evaluation.prepare(output)
    report = await evaluation.run_batch(output, frozen["sha256"],
                                         jev_credential="test", qwen_credential="test")
    assert report["completed"] and len(sent) == 260
    assert len(report["rows"]) == 300
    assert sum(row["status"] == "excluded" for row in report["rows"]) == 40
    assert all(row.get("desktop_operations", 0) == 0 for row in report["rows"])
    assert report["spend"]["batch"]["known_tokens"] == 260 * 15
    assert report["spend"]["stop_reason"] is None
    first = {row["arm"]: row for row in report["rows"][:5]}
    assert first["image14"]["score"]["correct"] is True
    assert first["box14"]["score"]["center_hit"] is True
    if qwen_overflow:
        assert first["qwen_box"]["status"] == "invalid"
        assert first["qwen_box"]["reason"] == "invalid_location"
        assert first["qwen_box"]["input_tokens"] == 10
        assert first["qwen_box"]["output_tokens"] == 5
        assert report["summary"]["qwen_box"]["invalid"] == 52
    else:
        assert first["qwen_box"]["score"]["center_hit"] is True
    assert first["box14"]["answer"]["confidence"] == 0.8
    assert all(row["cleanup_confirmed"] for row in report["rows"] if row["status"] == "returned")
    assert report["summary"]["image14"]["planned"] == 60
    assert report["summary"]["image14"]["eligible"] == 52
    assert json.loads((output / "result.json").read_text()) == report
    with pytest.raises(FileExistsError):
        await evaluation.run_batch(output, frozen["sha256"],
                                   jev_credential="test", qwen_credential="test")


@pytest.mark.parametrize("failure", ["unknown", "http", "invalid", "budget", "audit", "cancel", "cleanup"])
async def test_image_evaluation_preserves_denominators_on_stop(monkeypatch, tmp_path, failure):
    import asyncio
    import json
    from pathlib import Path
    import httpx2
    from tank_backend.agents.task_runtime import TaskRuntime
    from tank_backend.llm.decision_model import DecisionModel

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_image_eval as evaluation

    sent = []

    async def respond(request):
        sent.append(request)
        if failure == "cancel":
            raise asyncio.CancelledError
        if failure == "http" or len(sent) > 1:
            return httpx2.Response(503, json={"error": "unavailable"})
        data = json.loads(request.content)
        criteria = data["questions"]["next_action"]["criteria"]
        response = {"model": data["model"], "answers": {"next_action": {
            "type": "choice", "choice": "outside" if failure == "invalid" else "c1",
            "confidence": 1.0, "probabilities": {key: float(key == "c1") for key in criteria}}},
            "usage": {"input_tokens": 10, "output_tokens": 5}}
        if failure == "unknown":
            response.pop("usage")
        return httpx2.Response(200, json=response)

    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kwargs: httpx2.MockTransport(respond))

    async def broken(*args, **kwargs):
        raise OSError("test persistence/cleanup failure")

    if failure == "audit":
        monkeypatch.setattr(TaskRuntime, "write_audit", broken)
    if failure == "cleanup":
        monkeypatch.setattr(DecisionModel, "aclose", broken)
    output = tmp_path / "evaluation"
    frozen = evaluation.prepare(output)
    if failure == "budget":
        frozen["nano_usd_limit"] = 0
        frozen["sha256"] = evaluation.dev.digest({key: value for key, value in frozen.items() if key != "sha256"})
        (output / "freeze.json").write_text(json.dumps(frozen))
    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await evaluation.run_batch(output, frozen["sha256"], jev_credential="test", qwen_credential="test")
        report = json.loads((output / "result.json").read_text())
    else:
        report = await evaluation.run_batch(output, frozen["sha256"], jev_credential="test", qwen_credential="test")
    assert not report["completed"] and report["spend"]["stop_reason"]
    assert len(report["rows"]) == 300
    assert sum(row["status"] == "excluded" for row in report["rows"]) == 40
    assert len(sent) == (0 if failure in {"audit", "budget"} else 2 if failure == "invalid" else 1)
    assert sum(row["status"] == "not_run" for row in report["rows"]) == (258 if failure == "invalid" else 259)
    if failure == "unknown":
        assert report["spend"]["batch"]["reserved_tokens"] > 0
        assert report["rows"][0]["input_tokens"] is None
    if failure == "invalid":
        assert report["rows"][0]["status"] == "invalid"
        assert report["rows"][0]["input_tokens"] == 10
    if failure == "cleanup":
        row = report["rows"][0]
        assert row["status"] == "error" and row["score"]["correct"]
        assert report["summary"][row["arm"]]["returned"] == 0
        assert report["summary"][row["arm"]]["correct"] == 0


def test_image_evaluation_scores_absent_multiple_and_box_interior(monkeypatch):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_image_eval as evaluation

    label = {"expected_cardinality": "one", "clickable_regions": [[70, 130, 230, 180]]}
    wrong = evaluation.score_answer("box14", {"cardinality": "one", "box": [0, 0, 0.1, 0.1]}, label, (640, 360))
    assert wrong["cardinality_correct"] and not wrong["correct"]
    for count in ("none", "several"):
        label = {"expected_cardinality": count, "clickable_regions": []}
        assert evaluation.score_answer("box14", {"cardinality": count, "box": [0, 0, 1, 1]}, label, (640, 360))["correct"]
        assert evaluation.score_answer("qwen_box", {"cardinality": "one", "box": [0, 0, 1, 1]}, label, (640, 360))["false_unique"]
    rows = [{"arm": "box14", "admission": "ready", "status": status,
             "score": {"correct": True, "false_unique": True}}
            for status in ("returned", "error")]
    summary = evaluation.summarize(rows)["box14"]
    assert summary["returned"] == summary["correct"] == summary["false_unique"] == 1


@pytest.mark.parametrize("asset", ["data/labels.json", "data/public.json", "data/images/dev-001-1.png", "previews.json"])
async def test_image_evaluation_refuses_tampering_before_network(monkeypatch, tmp_path, asset):
    from pathlib import Path
    import httpx
    import httpx2
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_image_eval as evaluation

    frozen = evaluation.prepare(tmp_path / "evaluation")
    path = tmp_path / "evaluation" / asset
    path.write_bytes(path.read_bytes() + b" ")

    def forbidden(*args, **kwargs):
        raise AssertionError("tampered recipes cannot create a client")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    monkeypatch.setattr(httpx2, "AsyncClient", forbidden)
    with pytest.raises(ValueError, match="freeze changed"):
        await evaluation.run_batch(tmp_path / "evaluation", frozen["sha256"],
                                   jev_credential="test", qwen_credential="test")
    assert not (tmp_path / "evaluation/started.json").exists()



@pytest.mark.parametrize("size", [(1920, 1080), (100, 40), (2000, 100)])
@pytest.mark.parametrize("orientation", [1, 3, 6, 8])
def test_jev_image_normalization_preserves_inverse_frame_mapping(size, orientation):
    from dataclasses import replace
    from agent_computer_use.jev_image import normalize_frame
    from agent_computer_use.visual_selector import VisualFrame
    import hashlib

    original = Image.new("RGB", size, "white")
    exif = Image.Exif()
    exif[274] = orientation
    buffer = io.BytesIO()
    original.save(buffer, "PNG", exif=exif)
    png = buffer.getvalue()
    frame, _ = Observation.capture(png, session_id="task", display_id=5,
        display_geometry=(5, -200, 100, *size, *size))
    frame = replace(frame, image_sha256=hashlib.sha256(png).hexdigest())
    normalized = normalize_frame(VisualFrame("obs", frame, png, ()))
    with Image.open(io.BytesIO(normalized.asset.data)) as prepared:
        assert prepared.format == "PNG" and prepared.getexif().get(274, 1) == 1
        assert 280 <= prepared.width <= 1568 and 280 <= prepared.height <= 1568
    # Image and screen centers must agree after resize/padding/EXIF orientation.
    assert normalized.map_box((0.45, 0.45, 0.55, 0.55)) == frame.map_point(size[0] / 2, size[1] / 2)


@pytest.mark.parametrize("orientation,expected", [
    (1, (20, 24)), (2, (80, 24)), (3, (80, 56)), (4, (20, 56)),
    (5, (30, 16)), (6, (30, 64)), (7, (70, 64)), (8, (70, 16)),
])
def test_jev_inverse_rotation_uses_asymmetric_target(orientation, expected):
    from dataclasses import replace
    from agent_computer_use.jev_image import normalize_frame
    from agent_computer_use.visual_selector import VisualFrame
    import hashlib

    original = Image.new("RGB", (100, 80), "white")
    exif = Image.Exif()
    exif[274] = orientation
    buffer = io.BytesIO()
    original.save(buffer, "PNG", exif=exif)
    png = buffer.getvalue()
    frame, _ = Observation.capture(png, session_id="task", display_id=1)
    frame = replace(frame, image_sha256=hashlib.sha256(png).hexdigest())
    prepared = normalize_frame(VisualFrame("obs", frame, png, ()))
    assert prepared.map_box((0.15, 0.25, 0.25, 0.35)) == expected


@pytest.mark.parametrize("condition,question", [
    (condition, "box") for condition in ("one", "none", "several", "stale", "revoked", "unknown", "scope", "receiver")
] + [("one", "choice")])
async def test_jev_box_probe_never_dispatches_and_rechecks_original_frame(
    monkeypatch, shared_world, condition, question,  # noqa: F811
):
    import asyncio
    import json
    import httpx2
    from agent_computer_use.channels.native import NativeAXChannel, NativeConfig
    from agent_computer_use.jev_image import JevImageProbe
    from tank_backend.agents.subagent import (
        SubAgentAuthorization, SubAgentBudget, SubAgentContext, SubAgentStopped,
    )
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.llm.model_data import ModelDataScope
    from .test_native import native_config

    count = condition if condition in {"none", "several"} else "one"
    captures, sent = [], []
    current = io.BytesIO()
    Image.new("RGB", (100, 80), "white").save(current, "PNG")
    png = current.getvalue()
    def capture(**kwargs):
        captures.append(True)
        return png
    async def respond(request: httpx2.Request) -> httpx2.Response:
        nonlocal png
        sent.append(request)
        if condition == "stale":
            changed = io.BytesIO()
            Image.new("RGB", (100, 80), "black").save(changed, "PNG")
            png = changed.getvalue()
        elif condition == "revoked":
            ctx.authorization.revoke()
        data = {"model": "jev-1.14.0", "answers": {
            "cardinality": {"type": "choice", "choice": count, "confidence": 1.0,
                "probabilities": {key: float(key == count) for key in ("none", "one", "several")}},
            "target": {"type": "box", "box": {"left": 0.1, "top": 0.1, "right": 0.3,
                "bottom": 0.4}, "confidence": 0.8}}, "usage": {"input_tokens": 13, "output_tokens": 4}}
        if question == "choice":
            data["answers"] = {"next_action": {"type": "choice", "choice": "c1", "confidence": 1.0,
                                              "probabilities": {"c1": 1.0}}}
        if condition == "unknown":
            data.pop("usage")
        return httpx2.Response(200, json=data)
    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kw: httpx2.MockTransport(respond))
    monkeypatch.setattr("agent_computer_use.channels.native.macos._capture_screenshot_macos", capture)
    ctx = SubAgentContext(SubAgentAuthorization(frozenset({"network", "desktop"})),
        SubAgentBudget(), asyncio.Event(), model_data_scope=ModelDataScope(
            frozenset({"text"} if condition == "scope" else {"text", "image"})))
    ctx.runtime.configure_decision_model("task", DecisionModelProfile(
        "https://offline.invalid/v1/systemone", "jev-1.14.0", "KEY",
        images=condition != "receiver"), credential="test")
    channel = NativeAXChannel(config=NativeConfig.model_validate_json(json.dumps(native_config())))
    probe = JevImageProbe(channel, ctx)
    try:
        snapshot = await channel.observe("counter", ctx)
        if condition in {"one", "none", "several"}:
            prepared, result = await probe.assess(snapshot, state={}, instructions="Increment button",
                                                  options={"c1": "Increment"} if question == "choice" else None)
            from tank_backend.llm.decision_model import BoxResult, ChoiceResult
            if question == "choice":
                assert isinstance(result, ChoiceResult) and result.choice == "c1"
            else:
                assert isinstance(result, BoxResult) and result.cardinality.choice == count
            assert prepared.source.observation_id == snapshot.observation_id
            assert ctx.budget.total_tokens == 17 and len(captures) == 2
        else:
            expected = {"scope": "decision_images_denied", "receiver": "decision_images_denied",
                        "stale": "stale_visual_frame", "revoked": "error", "unknown": "invalid_decision"}
            with pytest.raises(SubAgentStopped, match=expected[condition]):
                await probe.assess(snapshot, state={}, instructions="Increment button")
            if condition == "unknown":
                assert ctx.budget.unknown_calls
        assert shared_world.sent == []
        assert len(sent) == (0 if condition in {"scope", "receiver"} else 1)
        if condition in {"scope", "receiver"}:
            assert captures == []
    finally:
        await channel.aclose()
        await ctx.runtime.aclose()


def test_new_development_set_prepares_without_clients_and_separates_labels(monkeypatch, tmp_path):
    import copy
    import json
    from pathlib import Path
    import httpx2

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_image_dev as dev
    def forbidden(*args, **kwargs):
        raise AssertionError("preparation created a model client")
    monkeypatch.setattr(httpx2, "AsyncClient", forbidden)
    output = tmp_path / "new-dev"
    frozen = dev.prepare(output)
    assert frozen["purpose"] == "development-only"
    cases = json.loads((output / "public.json").read_text())
    assert len(cases) == 36
    assert {case["language"] for case in cases} == {"en", "zh"}
    assert {case["family"] for case in cases} >= {
        "structured", "missing-structure", "roundtrip", "recovery", "workflow", "absent", "ambiguous"}
    case = cases[0]
    png = (output / case["stages"][0]["image"]).read_bytes()
    requests = dev.requests(case["stages"][0], png)
    labels = json.loads((output / "labels.json").read_text())
    for public_case in cases:
        for stage in public_case["stages"]:
            assert labels[stage["id"]]["expected_choice"] in stage["options"]
            if public_case["family"] in {"missing-input", "stale-frame"}:
                assert dev.requests(stage, (output / stage["image"]).read_bytes()) == {}
    changed = copy.deepcopy(labels)
    for value in changed.values():
        value["expected_choice"] = "poison"
    (output / "labels.json").write_text(json.dumps(changed))
    assert dev.requests(case["stages"][0], png) == requests
    assert "expected_choice" not in json.dumps(requests)
    with pytest.raises(ValueError, match="freeze|changed"):
        dev.load_freeze(output, frozen["sha256"])
    with pytest.raises(FileExistsError):
        dev.prepare(output)


def test_development_source_drift_requires_a_new_freeze(monkeypatch, tmp_path):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import jev_image_dev as dev

    frozen = dev.prepare(tmp_path / "dev")
    source_hashes = dev.sources()
    source_hashes["core/src/tank_backend/tools/computer_observation.py"] = "changed"
    monkeypatch.setattr(dev, "sources", lambda: source_hashes)
    with pytest.raises(ValueError, match="freeze changed"):
        dev.load_freeze(tmp_path / "dev", frozen["sha256"])


async def test_repeated_state_visual_recovery_stays_bounded_with_advisor(monkeypatch):
    import json
    import httpx
    from agent_computer_use.contracts import AdvisorResult
    from agent_computer_use.controller import ComputerUseController
    from agent_computer_use.visual_selector import VisualFrame, VisualSelector
    from tank_backend.llm.model_data import ModelDataScope
    from tank_backend.llm.profile import LLMProfile
    from .test_jev import setup, reply
    from .test_ladder import WanderingWorld, wandering_request

    image = io.BytesIO()
    Image.new("RGB", (100, 80), "white").save(image, "PNG")
    requests = []
    async def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if "questions" in payload:
            return httpx.Response(200, json=reply(request))
        return httpx.Response(200, json={
            "id": "visual", "object": "chat.completion", "created": 1, "model": "vision",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": '{"choice":"c1"}'}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}})

    class World(WanderingWorld):
        async def dispatch(self, binding, action, ctx):
            receipt = await super().dispatch(binding, action, ctx)
            self.value = str(len(self.dispatched) % 2)
            return receipt

        async def capture(self, snapshot, ctx):
            frame, png = Observation.capture(image.getvalue(), session_id=ctx.runtime.task_id,
                                             display_id=1)
            return VisualFrame(snapshot.observation_id, frame, png,
                               tuple((e.ref, (10, 10, 20, 20)) for e in snapshot.elements))

    class Advisor:
        calls = 0
        async def assist(self, request, goal, snapshot, actions, ctx):
            self.calls += 1
            return AdvisorResult(actions.binding, "unable")

    ctx, _, _, _ = setup(monkeypatch, respond)
    object.__setattr__(ctx, "model_data_scope", ModelDataScope(frozenset({"text", "image"})))
    ctx.runtime.configure_visual_model("task", LLMProfile(
        "visual", "key", "vision", "https://offline.invalid/v1", max_tokens=128))
    world, advisor = World(), Advisor()
    try:
        result = await ComputerUseController(
            world, world, selector=VisualSelector(world), advisor=advisor).run(wandering_request(), ctx)
        assert result.reason == "advisor_unable", result
        assert ["jev" if "questions" in p else "visual" for p in requests] == [
            "jev", "jev", "visual", "visual"]
        assert len(world.dispatched) == 4 and advisor.calls == 1
    finally:
        await ctx.runtime.aclose()


@pytest.mark.parametrize("failure", [None, "visual_required", "repeat", "stale_image", "window", "revoked", "unknown", "unknown_visual", "missing_image", "denied", "invalid", "abstain", "effect_unknown", "bounds"])
async def test_same_task_jev_image_jev_loop(monkeypatch, shared_world, failure):  # noqa: F811
    import json
    import httpx
    from agent_computer_use.channels.native import NativeAXChannel, NativeConfig
    from agent_computer_use.controller import ComputerUseController
    from agent_computer_use.visual_selector import VisualSelector
    from tank_backend.agents.subagent import SubAgentRequest
    from tank_backend.llm.model_data import ModelDataScope
    from tank_backend.llm.profile import LLMProfile
    from .test_jev import setup, reply
    from .test_native import native_config, goal

    requests = []
    image_changed = False
    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal image_changed
        payload = json.loads(request.content)
        requests.append(payload)
        if "questions" in payload:
            data = reply(request, "need_more_context" if shared_world.value == "1"
                         and failure not in {"visual_required", "repeat"} else None)
        else:
            data = {"id": "visual", "object": "chat.completion", "created": 1,
                    "model": "vision", "choices": [{"index": 0, "finish_reason": "stop",
                    "message": {"role": "assistant", "content": '{"choice":"c1"}'}}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}
        if shared_world.value == "1":
            if failure == "revoked":
                ctx.authorization.revoke()
            elif failure == "unknown":
                data.pop("usage", None)
            elif "questions" not in payload:
                if failure == "stale_image":
                    image_changed = True
                elif failure == "window":
                    from dataclasses import replace
                    shared_world.window = replace(shared_world.window, bounds=(1, 0, 99, 80))
                elif failure == "invalid":
                    data["choices"][0]["message"]["content"] = '{"choice":"invented"}'
                elif failure == "abstain":
                    data["choices"][0]["message"]["content"] = '{"choice":"need_more_context"}'
                elif failure == "unknown_visual":
                    data.pop("usage", None)
        return httpx.Response(200, json=data)

    ctx, _, _, _ = setup(monkeypatch, respond)
    object.__setattr__(ctx, "model_data_scope", ModelDataScope(frozenset({"text", "image"})))
    ctx.runtime.configure_visual_model("task", LLMProfile(
        "visual", "key", "vision", "https://offline.invalid/v1", max_tokens=128))
    png = io.BytesIO()
    Image.new("RGB", (100, 80), "white").save(png, "PNG")
    black = io.BytesIO()
    Image.new("RGB", (100, 80), "black").save(black, "PNG")
    monkeypatch.setattr("agent_computer_use.channels.native.macos._capture_screenshot_macos",
                        lambda **kwargs: b"" if failure == "missing_image" else
                        black.getvalue() if image_changed else png.getvalue())
    if failure == "denied":
        object.__setattr__(ctx, "model_data_scope", ModelDataScope())
    if failure == "visual_required":
        from dataclasses import replace
        from tank_backend.tools.computer_ax import AXElementRef
        shared_world.buttons.append(replace(
            shared_world.button, index=3, frame=(60, 10, 20, 20),
            element=AXElementRef(object(), False, 80)))
    elif failure == "repeat":
        press = shared_world.press
        cycled = False
        def cycle(ref):
            nonlocal cycled
            if shared_world.value == "1" and not cycled:
                shared_world.sent.append(("press", ref))
                shared_world.value = "0"
                cycled = True
            else:
                press(ref)
        monkeypatch.setattr("agent_computer_use.channels.native.ax_press", cycle)
    elif failure == "effect_unknown":
        press = shared_world.press
        def unchanged(ref):
            if shared_world.value == "1":
                shared_world.sent.append(("press", ref))
            else:
                press(ref)
        monkeypatch.setattr("agent_computer_use.channels.native.ax_press", unchanged)
    channel = NativeAXChannel(config=NativeConfig.model_validate_json(json.dumps(native_config())))
    if failure == "bounds":
        from dataclasses import replace
        capture = channel.capture
        async def outside(snapshot, context):
            captured = await capture(snapshot, context)
            return replace(captured, bounds=tuple((ref, (90, 10, 20, 20))
                                                  for ref, _ in captured.bounds))
        monkeypatch.setattr(channel, "capture", outside)
    controller = ComputerUseController(channel, channel, selector=VisualSelector(channel),
                                       completion_keys=channel.completion_keys)
    task = goal().model_dump(mode="json")
    task["completion"][0]["value"] = "2" if failure == "repeat" else "3"
    deadline, budget, runtime = ctx.deadline, ctx.budget, ctx.runtime
    try:
        result = await controller.run(SubAgentRequest("Increment three times", "", "task", task), ctx)
        if failure not in {None, "visual_required", "repeat"}:
            reasons = {"stale_image": "stale_reference", "window": "stale_reference",
                       "revoked": "error", "unknown": "invalid_decision", "unknown_visual": "unknown_usage",
                       "missing_image": "invalid_visual_frame", "denied": "model_data_denied",
                       "invalid": "invalid_decision", "abstain": "no_progress",
                       "effect_unknown": "effect_unknown", "bounds": "visual_target_unavailable"}
            assert result.reason == reasons[failure], result
            assert result.status == ("unknown" if failure == "effect_unknown" else "partial")
            if failure == "revoked":
                assert not ctx.authorization.active
            if failure in {"unknown", "unknown_visual"}:
                assert ctx.budget.unknown_calls
            assert len(shared_world.sent) == (2 if failure == "effect_unknown" else 1)
            if failure in {"revoked", "unknown", "missing_image", "denied", "bounds"}:
                assert not any("messages" in p for p in requests)
            if failure in {"abstain", "effect_unknown", "unknown_visual"}:
                assert sum("messages" in p for p in requests) == (2 if failure == "abstain" else 1)
                assert "messages" in requests[-1]
            return
        assert result.status == "completed", result
        if failure in {"visual_required", "repeat"}:
            assert any("messages" in p for p in requests)
            if failure == "visual_required":
                assert all("messages" in p for p in requests)
            assert ctx.runtime is runtime and ctx.budget is budget
            return
        assert len(shared_world.sent) == 3
        assert ["jev" if "questions" in p else "visual" for p in requests] == [
            "jev", "jev", "visual", "jev"]
        parts = requests[2]["messages"][1]["content"]
        assert parts[1]["type"] == "image_url"
        import base64
        assert base64.b64decode(parts[1]["image_url"]["url"].split(",", 1)[1]) == png.getvalue()
        assert ctx.runtime is runtime and ctx.budget is budget and ctx.deadline == deadline
        assert ctx.budget.total_tokens == 46
        receipts = result.details["receipts"]
        assert isinstance(receipts, list) and len(receipts) == 3
        assert result.details["goal_version"] == 1
    finally:
        await channel.aclose()
        await ctx.runtime.aclose()


async def test_native_visual_candidates_map_into_the_bound_crop(monkeypatch, shared_world):  # noqa: F811
    import json
    from dataclasses import replace
    from agent_computer_use.channels.native import NativeAXChannel, NativeConfig
    from .test_native import context, native_config

    shared_world.window = replace(shared_world.window, bounds=(5, 5, 80, 60))
    image = io.BytesIO()
    Image.new("RGB", (100, 80), "white").save(image, "PNG")
    monkeypatch.setattr("agent_computer_use.channels.native.macos._capture_screenshot_macos",
                        lambda **kwargs: image.getvalue())
    ctx = context()
    ctx.runtime.bind("task")
    channel = NativeAXChannel(config=NativeConfig.model_validate_json(json.dumps(native_config())))
    try:
        snapshot = await channel.observe("counter", ctx)
        captured = await channel.capture(snapshot, ctx)
        assert captured.frame.crop == (5, 5, 85, 65)
        assert captured.frame.window_id == shared_world.window.window_id
        assert captured.frame.screen_size == (100, 80)
        button = next(e for e in snapshot.elements if e.label == "Increment")
        x, y, width, height = dict(captured.bounds)[button.ref]
        assert captured.frame.map_point(x + width / 2, y + height / 2) == (20, 20)
        with Image.open(io.BytesIO(captured.png)) as cropped:
            assert cropped.size == captured.frame.image_size
            assert cropped.width / cropped.height == 80 / 60
        assert captured.png != image.getvalue()
    finally:
        await channel.aclose()
        await ctx.runtime.aclose()


def image_frame() -> tuple[Observation, bytes]:
    image = io.BytesIO()
    Image.new("RGB", (200, 100), "white").save(image, "PNG")
    return Observation.capture(image.getvalue(), session_id="task", display_id=5,
                               window_id=7, window_bounds=(20, 10, 180, 90),
                               display_geometry=(5, -200, 100, 200, 100, 400, 200))


def native_vision(monkeypatch, *, text: str = "保存", box=(0.25, 0.25, 0.5, 0.5)):
    from agent_computer_use import vision

    recognized = Mock()
    recognized.string.return_value = text
    recognized.confidence.return_value = 0.95
    observation = Mock()
    observation.topCandidates_.return_value = [recognized]
    observation.boundingBox.return_value = SimpleNamespace(
        origin=SimpleNamespace(x=box[0], y=box[1]),
        size=SimpleNamespace(width=box[2], height=box[3]),
    )
    request, handler = Mock(), Mock()
    request.results.return_value = [observation]
    handler.performRequests_error_.return_value = (True, None)
    module = Mock()
    module.VNRecognizeTextRequest.alloc.return_value.init.return_value = request
    module.VNImageRequestHandler.alloc.return_value.initWithData_options_.return_value = handler
    monkeypatch.setattr(vision.importlib, "import_module", lambda name: module)
    return request, handler


def test_vision_uses_bound_crop_and_emits_only_text_regions(monkeypatch) -> None:
    from agent_computer_use.vision import recognize_text

    request, _ = native_vision(monkeypatch)
    frame, png = image_frame()
    elements = recognize_text(frame, png)
    assert len(elements) == 1
    region = elements[0]
    assert region.label == "保存" and region.source == "ocr"
    assert region.kind == "text_region" and region.actions == ()
    assert region.bounds is not None
    x, y, w, h = region.bounds
    assert frame.map_point(x + w / 2, y + h / 2) == (-100, 150)
    request.setUsesLanguageCorrection_.assert_called_once_with(False)
    request.setRecognitionLanguages_.assert_called_once_with(["zh-Hans", "en-US"])


@pytest.mark.parametrize("case", ["hash", "size", "bounds", "failure", "oversize"])
def test_vision_rejects_invalid_frame_or_native_result(monkeypatch, case: str) -> None:
    from dataclasses import replace
    from agent_computer_use.vision import recognize_text

    request, handler = native_vision(monkeypatch, box=(0.9, 0.2, 0.5, 0.1)
                                     if case == "bounds" else (0.1, 0.1, 0.2, 0.2))
    frame, png = image_frame()
    if case == "hash":
        png += b"wrong"
    elif case == "size":
        frame = replace(frame, image_size=(1, 1))
    elif case == "failure":
        handler.performRequests_error_.return_value = (False, "error")
    elif case == "oversize":
        request.results.return_value = request.results.return_value * 501
    with pytest.raises((ValueError, RuntimeError)):
        recognize_text(frame, png)
    if case in {"hash", "size"}:
        handler.performRequests_error_.assert_not_called()


async def test_ocr_missing_dependency_is_unavailable_without_actions(monkeypatch) -> None:
    import asyncio
    from agent_computer_use.vision import VisionObservationSource
    from tank_backend.agents.subagent import (
        SubAgentAuthorization, SubAgentBudget, SubAgentContext,
    )

    frame, png = image_frame()

    async def capture():
        return frame, png

    def missing(name):
        raise ModuleNotFoundError("Vision")

    monkeypatch.setattr("agent_computer_use.vision.importlib.import_module", missing)
    ctx = SubAgentContext(SubAgentAuthorization(frozenset({"desktop"})),
                          SubAgentBudget(), asyncio.Event())
    ctx.runtime.bind("task")
    source = VisionObservationSource(frame, "window-7", capture)
    snapshot = await source.observe("window-7", ctx)
    assert not snapshot.ready and not snapshot.elements


def test_frozen_vision_uses_revision_three(monkeypatch) -> None:
    from agent_computer_use.vision import recognize_text

    request, _ = native_vision(monkeypatch)
    frame, png = image_frame()
    recognize_text(frame, png)
    request.setRevision_.assert_called_once_with(3)


def test_acceptance_scoring_never_reuses_a_duplicate_or_wrong_region(monkeypatch) -> None:
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3]))
    from agent_computer_use.contracts import Element
    from benchmarks.computer_use.s1_acceptance import score_regions

    truth = [{"text": "保存", "bounds": [10, 10, 20, 20]},
             {"text": "保存", "bounds": [40, 10, 50, 20]}]
    region = Element("ocr", "text", "保存", (), kind="text_region", bounds=(10, 10, 10, 10))
    result = score_regions((region, region), truth)
    assert result["hits"] == 1 and result["false_matches"] == 1
    assert result["expected"] == 2
    assert score_regions((region,), [])['false_matches'] == 1


@pytest.mark.parametrize("case", ["cancel", "scope", "closed"])
async def test_ocr_checks_after_capture_before_native(monkeypatch, case: str) -> None:
    import asyncio
    from dataclasses import replace
    from agent_computer_use.vision import VisionObservationSource
    from tank_backend.agents.subagent import (
        SubAgentAuthorization, SubAgentBudget, SubAgentContext, SubAgentStopped,
    )

    frame, png = image_frame()
    ctx = SubAgentContext(SubAgentAuthorization(frozenset({"desktop"})),
                          SubAgentBudget(), asyncio.Event())
    ctx.runtime.bind("task")
    native = Mock()
    monkeypatch.setattr("agent_computer_use.vision.recognize_text", native)

    async def capture():
        if case == "cancel":
            ctx.cancel.set()
        elif case == "closed":
            await source.aclose()
        return (replace(frame, window_id=99) if case == "scope" else frame), png

    source = VisionObservationSource(frame, "window-7", capture)
    with pytest.raises((SubAgentStopped, asyncio.CancelledError)):
        await source.observe("window-7", ctx)
    native.assert_not_called()
