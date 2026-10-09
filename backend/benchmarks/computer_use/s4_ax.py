"""Frozen, opt-in native AX pilot. Preparing a recipe never accesses the desktop or a model."""

from __future__ import annotations

import hashlib
import inspect
import json
import asyncio
import importlib
import os
import signal
import tempfile
import time
import unicodedata
from contextlib import ExitStack, contextmanager
from collections.abc import Callable, Coroutine, Iterator
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypedDict
from unittest.mock import MagicMock, patch

from agent_computer_use import action_builder, advisor, agent, contracts, controller, factory, observation, jev, model_view
from agent_computer_use.channels import native
from tank_backend.tools import computer_ax, computer_native, computer_use_macos

from benchmarks.computer_use.s3_replay import MODELS, digest

if TYPE_CHECKING:
    import httpx2

BUNDLES = {"calculator": "com.apple.calculator", "textedit": "com.apple.TextEdit"}
BLOCKED_IDS = ["MemoryClear", "MemoryAdd", "MemorySubtract", "MemoryRecall", "Shift", "Radians"]
BLOCKED_LABELS = ["Mode", "Show Sidebar", "Hide Sidebar"]
FAKE_ENDPOINT = "https://s4-ax.invalid/v1/systemone"
FAKE_ADVISOR_ENDPOINT = "https://s4-advisor.invalid/v1/chat/completions"


@contextmanager
def fake_model_http(respond: Callable[[httpx2.Request], Coroutine[None, None, httpx2.Response]]) -> Iterator[None]:
    """Replace the installed SDK's actual network boundary, including proxy routing."""
    import httpx2

    class OfflineClient(httpx2.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx2.MockTransport(respond)
            kwargs["trust_env"] = False
            super().__init__(*args, **kwargs)

    with patch("httpx2.AsyncClient", OfflineClient):
        yield

class PilotObserver:
    """Persist bounded diagnostic metadata, never SDK messages, headers or bodies."""

    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def on_event(self, kind: str, metadata: dict[str, Any]) -> None:
        if kind not in {"decision_error", "computer_use_error", "model_call", "computer_use_advisor",
                        "computer_use_proposal"}:
            return
        keys = {"task_id", "call_id", "phase", "status", "prompt_tokens",
                "completion_tokens", "elapsed_ms", "error_type", "http_status", "cause_type",
                "reason", "call_number", "observation_id", "advice_kind", "source",
                "model_choice", "action_id", "candidate_set_id"}
        self.events.append({"kind": kind, **{key: value for key, value in metadata.items()
                           if key in keys and (value is None or type(value) in (str, int, float))}})


class PilotCase(TypedDict):
    id: str
    application: Literal["calculator", "textedit"]
    dispatch: Literal["ax_press", "quartz"]
    repeat: int
    max_decisions: int
    move_window: bool


CASES: tuple[PilotCase, ...] = tuple(
    PilotCase(id=f"calculator-{mode}-{repeat}", application="calculator", dispatch=mode,
              repeat=repeat, max_decisions=12, move_window=repeat == 1)
    for mode in ("ax_press", "quartz") for repeat in range(3)
) + tuple(
    PilotCase(id=f"textedit-{repeat}", application="textedit", dispatch="ax_press",
              repeat=repeat, max_decisions=2, move_window=repeat == 1)
    for repeat in range(3)
)


def task_goal(case: PilotCase) -> dict[str, Any]:
    if case["application"] == "calculator":
        objective = "Use Calculator buttons to enter exactly 7×8 and evaluate it. Do not enter 56 directly."
        inputs: list[dict[str, Any]] = []
        completion = [{"key": "ax:value:expression", "value": "7×8"},
                      {"key": "ax:value:result", "value": "56"}]
        operations = ["click"]
    else:
        text = f"Tank AX / Jev\n中文验证 {case['repeat']}\n"
        objective = "Replace the body of this temporary TextEdit document with the supplied text. Do not save or close it."
        inputs = [{"key": "body", "purpose": "the complete document body", "value": text}]
        completion = [{"key": "ax:value:document", "value": text}]
        operations = ["fill"]
    return {"schema_version": 2, "goal_id": case["id"], "intent": objective,
            "objective": objective, "scope": case["id"], "authorization_ref": "current_task",
            "allowed_operations": operations, "inputs": inputs, "completion": completion,
            "constraints": ["Operate only this bound application window; do not change modes or memory."]}


def channel_readouts(application: str) -> list[dict[str, Any]]:
    if application == "calculator":
        return [{"name": "expression", "role": "AXStaticText", "aggregation": "compact_text",
                 "ancestor_identifier": "StandardResultView", "allow_empty": True},
                {"name": "result", "role": "AXStaticText", "aggregation": "compact_text",
                 "ancestor_identifier": "StandardInputView"}]
    return [{"name": "document", "role": "AXTextArea", "identifier": "First Text View"}]


def freeze_inputs() -> dict[str, Any]:
    from tank_backend.agents import subagent, task_runtime, runner, subagent_adapter, task_resources
    from tank_backend.llm import decision_model, task_decision_model, model_call, decision_profile, task_model
    from tank_backend.benchmarks import model_policy, spend_ledger
    from benchmarks.computer_use import jev_smoke

    root = Path(__file__).resolve().parents[2]
    paths = [Path(__file__), root / "plugins/agent-computer-use/plugin.yaml",
             *(Path(inspect.getfile(module)) for module in (
        action_builder, contracts, controller, factory, observation, native, computer_ax,
        computer_native, computer_use_macos, subagent, task_runtime, decision_model,
        task_decision_model, model_call, agent, jev, runner, subagent_adapter, task_resources,
        decision_profile, jev_smoke, advisor, task_model, model_policy, spend_ledger, model_view,
    ))]
    data = {"revision": "s4-ax-focus-1", "cases": list(CASES), "model": MODELS["jev"],
            "advisor_model": {**MODELS["qwen"], "output_ceiling": 2048},
            "fake_advisor_endpoint": FAKE_ADVISOR_ENDPOINT,
            "advisor_call_limit": 4,
            "accounting": "shared SDK-call limit; inherited conservative price estimates, not provider invoices",
            "fake_endpoint": FAKE_ENDPOINT,
            "request_limit": sum(case["max_decisions"] for case in CASES),
            "nano_usd_limit": 250_000_000, "seconds_per_task": 120,
            "readouts": {app: channel_readouts(app) for app in ("calculator", "textedit")},
            "calculator_exclusions": {"identifiers": BLOCKED_IDS, "labels": BLOCKED_LABELS},
            "goals": {case["id"]: task_goal(case) for case in CASES},
            "scope": "new owned Calculator and temporary TextEdit documents, main display only",
            "setup": "fresh process; Calculator All Clear; optional window move before observation",
            "acceptance": "all nine goals independently verified, at least one model-selected native action per trial, cleanup confirmed",
            "stop_policy": "stop on any failed/unknown outcome, unknown usage or cleanup; retain all planned rows",
            "source_sha256": {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in paths}}
    data["sha256"] = digest(data)
    return data


def prepare(output: Path) -> dict[str, Any]:
    frozen = freeze_inputs()
    output.mkdir(parents=True, exist_ok=False)
    (output / "freeze.json").write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n")
    return frozen


def load_freeze(output: Path, approved: str) -> dict[str, Any]:
    frozen = freeze_inputs()
    if frozen["sha256"] != approved or json.loads((output / "freeze.json").read_text()) != frozen:
        raise ValueError("Native pilot freeze changed; prepare and approve a new recipe")
    return frozen


def pump(seconds: float = 0.05) -> None:
    foundation = importlib.import_module("Foundation")
    foundation.NSRunLoop.currentRunLoop().runUntilDate_(
        foundation.NSDate.dateWithTimeIntervalSinceNow_(seconds))


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def setup_position(bounds: dict[str, float], geometry: tuple[int, ...], shifted: bool) -> tuple[float, float] | None:
    x, y, width, height = (bounds[key] for key in ("X", "Y", "Width", "Height"))
    if width <= 0 or height <= 0 or width > geometry[3] or height > geometry[4]:
        raise RuntimeError("Owned window does not fit the primary display")
    if not shifted and 0 <= x <= geometry[3] - width and 0 <= y <= geometry[4] - height:
        return None
    return (min(280.0 if shifted else 240.0, geometry[3] - width),
            min(180.0 if shifted else 160.0, geometry[4] - height))


class OwnedApplication:
    """Pilot-only process owner; production channels merely borrow their bound window."""

    def __init__(self, case: PilotCase) -> None:
        self.case = case
        self.app: Any = None
        self.pid: int | None = None
        self.identity: native.ProcessIdentity | None = None
        self.unverified_launch = False
        self.window_id: int | None = None
        self.path: Path | None = None
        self.original_front: Any = None
        self.window_element: Any = None
        self.original_position: Any = None
        self.sidebar_hidden = False
        self.launch_pending = False
        self.setup_actions: list[str] = []

    def windows(self) -> list[Any]:
        quartz = computer_use_macos._load_quartz()
        return [w for w in quartz.CGWindowListCopyWindowInfo(quartz.kCGWindowListOptionOnScreenOnly, 0) or []
                if w.get("kCGWindowOwnerPID") == self.pid and w.get("kCGWindowLayer") == 0]

    def bound_ax_window(self, api: dict[str, Any]) -> Any:
        quartz = [w for w in self.windows() if w["kCGWindowNumber"] == self.window_id]
        if len(quartz) != 1:
            raise RuntimeError("Independent Quartz window unavailable")
        rect = quartz[0]["kCGWindowBounds"]
        bounds = (int(rect["X"]), int(rect["Y"]), int(rect["Width"]), int(rect["Height"]))
        app = api["AXUIElementCreateApplication"](self.pid)
        error, windows = api["AXUIElementCopyAttributeValue"](app, "AXWindows", None)
        if error:
            raise RuntimeError(f"Independent AX windows unavailable: {error}")
        height = computer_use_macos._main_geometry(computer_use_macos._active_displays())[4]
        matches = [window for window in windows or []
                   if any(frame is not None and computer_ax._frames_close(frame, bounds)
                          for frame in (computer_ax._top_left_frame(api, window, height),
                                        computer_ax._flipped_frame(api, window, height)))]
        if len(matches) != 1:
            raise RuntimeError("Independent AX window binding unavailable or ambiguous")
        return matches[0]

    def start(self) -> native.NativeConfig:
        appkit = importlib.import_module("AppKit")
        foundation = importlib.import_module("Foundation")
        workspace = appkit.NSWorkspace.sharedWorkspace()
        bundle = BUNDLES[self.case["application"]]
        pump()
        if any(app.bundleIdentifier() == bundle for app in workspace.runningApplications()):
            raise RuntimeError("Target app already running; pilot does not touch existing sessions")
        self.original_front = workspace.frontmostApplication()
        configuration = appkit.NSWorkspaceOpenConfiguration.configuration()
        configuration.setCreatesNewApplicationInstance_(True)
        configuration.setActivates_(True)
        configuration.setArguments_(["-ApplePersistenceIgnoreState", "YES"])
        app_url = workspace.URLForApplicationWithBundleIdentifier_(bundle)
        if app_url is None:
            raise RuntimeError("Required pilot application is unavailable")
        completed: list[tuple[Any, Any]] = []
        launch_after_us = int(time.time() * 1_000_000)

        def launched(app: Any, error: Any) -> None:
            self.launch_pending = False
            if app is not None:
                try:
                    pid = int(app.processIdentifier())
                    identity = native.process_identity(pid)
                    seconds, micros = (int(part) for part in identity.start.split(":"))
                    if identity.bundle_id != bundle or seconds * 1_000_000 + micros < launch_after_us:
                        raise RuntimeError("Launch did not create the requested application instance")
                    self.app, self.pid, self.identity = app, pid, identity
                except Exception as exc:
                    self.unverified_launch = True
                    completed.append((None, exc))
                    return
            completed.append((app, error))

        self.launch_pending = True
        if self.case["application"] == "textedit":
            fd, filename = tempfile.mkstemp(prefix="tank-s4-ax-", suffix=".txt")
            os.close(fd)
            self.path = Path(filename)
            workspace.openURLs_withApplicationAtURL_configuration_completionHandler_(
                [foundation.NSURL.fileURLWithPath_(filename)], app_url, configuration, launched)
        else:
            workspace.openApplicationAtURL_configuration_completionHandler_(app_url, configuration, launched)
        deadline = time.monotonic() + 10
        while not completed and time.monotonic() < deadline:
            pump()
        if not completed or completed[0][0] is None:
            raise RuntimeError("Application launch unconfirmed")
        assert self.app is not None and self.pid is not None and self.identity is not None
        for _ in range(20):
            pump()
        windows = self.windows()
        if len(windows) != 1:
            raise RuntimeError("Expected exactly one new owned window")
        self.window_id = int(windows[0]["kCGWindowNumber"])
        api = computer_ax._load_ax()
        self.window_element = self.bound_ax_window(api)
        self.original_position = computer_ax._attr(api, self.window_element, "AXPosition")
        geometry = computer_use_macos._main_geometry(computer_use_macos._active_displays())
        position = setup_position(dict(windows[0]["kCGWindowBounds"]), geometry, self.case["move_window"])
        if position is not None:
            # Setup varies placement, never the task's action sequence or candidate identities.
            functions: dict[str, Any] = {}
            objc = importlib.import_module("objc")
            bundle_obj = foundation.NSBundle.bundleWithPath_(
                "/System/Library/Frameworks/ApplicationServices.framework/Frameworks/HIServices.framework")
            objc.loadBundleFunctions(bundle_obj, functions, [("AXValueCreate", b"@in^{CGPoint=dd}")])
            point = functions["AXValueCreate"](1, position)
            if api["AXUIElementSetAttributeValue"](self.window_element, "AXPosition", point):
                raise RuntimeError("Window setup move failed")
            self.setup_actions.append("move_owned_window")
            for _ in range(5):
                pump()
        config = native.NativeConfig.model_validate_json(json.dumps({
            "scope": self.case["id"], "bundle_id": bundle, "pid": self.pid,
            "process_start": self.identity.start,
            "window_id": self.window_id, "dispatch": self.case["dispatch"],
            "labels": "identifier" if self.case["application"] == "textedit" else "accessible_name",
            "readouts": channel_readouts(self.case["application"]),
            "blocked_identifiers": BLOCKED_IDS if self.case["application"] == "calculator" else [],
            "blocked_labels": BLOCKED_LABELS if self.case["application"] == "calculator" else [],
        }))
        window = native.read_window(config)
        if self.case["application"] == "calculator":
            candidates, incomplete = computer_ax.ax_window_candidates(self.window_id, window.display_geometry)
            if incomplete:
                raise RuntimeError("Calculator setup evidence incomplete")
            hide = [c for c in candidates if c.description == "Hide Sidebar"]
            if hide:
                if len(hide) != 1:
                    raise RuntimeError("Sidebar setup ambiguous")
                computer_ax.ax_press(hide[0].element)
                self.sidebar_hidden = True
                self.setup_actions.append("hide_owned_sidebar")
                pump(0.2)
            clear = [c for c in candidates if c.identifier == "AllClear"]
            if len(clear) != 1:
                raise RuntimeError("Calculator reset unavailable")
            computer_ax.ax_press(clear[0].element)
            self.setup_actions.append("clear_owned_calculator")
            pump(0.2)
            if self.read_values().get("result") != "0":
                raise RuntimeError("Calculator reset was not observed")
        return config

    def read_values(self) -> dict[str, str]:
        for attempt in range(3):
            pump(0.05)
            try:
                return self.read_values_once()
            except RuntimeError:
                if attempt == 2:
                    raise
        raise AssertionError("Unreachable readback state")

    def read_values_once(self) -> dict[str, str]:
        """Independent fresh AX traversal; never reads controller snapshots or model answers."""
        if self.pid is None or computer_ax.ax_focused_pid() != self.pid:
            raise RuntimeError("Pilot application is no longer foreground")
        api = computer_ax._load_ax()
        result: dict[str, str] = {}
        queue: list[tuple[Any, int, str | None]] = [(self.bound_ax_window(api), 0, None)]
        count = 0
        while queue:
            element, depth, region = queue.pop(0)
            count += 1
            if count > 2000 or depth > 12:
                raise RuntimeError("Independent readback truncated")
            identifier = computer_ax._attr(api, element, "AXIdentifier")
            role = computer_ax._attr(api, element, "AXRole")
            if identifier in ("StandardInputView", "StandardResultView"):
                region = "result" if identifier == "StandardInputView" else "expression"
                if region in result:
                    raise RuntimeError("Independent display region ambiguous")
                result[region] = ""
            value = computer_ax._attr(api, element, "AXValue")
            if role == "AXStaticText" and region is not None and isinstance(value, str):
                result[region] += "".join(c for c in value if not c.isspace()
                                         and unicodedata.category(c) != "Cf")
            if role == "AXTextArea" and identifier == "First Text View":
                if "document" in result or not isinstance(value, str):
                    raise RuntimeError("Independent document ambiguous")
                result["document"] = value
            error, children = api["AXUIElementCopyAttributeValue"](element, "AXChildren", None)
            if error not in (0, -25205, -25212):
                raise RuntimeError("Independent readback incomplete")
            queue.extend((child, depth + 1, region) for child in (children or []))
        return result

    def close(self) -> dict[str, Any]:
        evidence: dict[str, Any] = {"confirmed": False}
        deadline = time.monotonic() + 10
        while self.launch_pending and time.monotonic() < deadline:
            pump()
        if self.launch_pending:
            raise RuntimeError("Late application launch cleanup unconfirmed")
        if self.unverified_launch:
            raise RuntimeError("Application launch identity unconfirmed; no process was terminated")
        front = computer_ax.ax_focused_pid()
        restore_front = front in {self.pid, self.original_front.processIdentifier()
                                  if self.original_front is not None else None}
        if self.pid is not None and process_alive(self.pid):
            if self.identity is None or native.process_identity(self.pid) != self.identity:
                raise RuntimeError("Owned process identity changed; cleanup refused")
            windows = self.windows()
            # A verified launch may fail before window setup (including a late callback).
            # Its sole new window belongs to this process; multiple windows remain ambiguous.
            if (len(windows) > 1 if self.window_id is None else
                    any(w["kCGWindowNumber"] != self.window_id for w in windows)):
                raise RuntimeError("Unowned window appeared; application left running")
            api = computer_ax._load_ax()
            if self.window_element is not None and self.original_position is not None:
                evidence["position_restored"] = not api["AXUIElementSetAttributeValue"](
                    self.window_element, "AXPosition", self.original_position)
            if self.sidebar_hidden and self.window_id is not None:
                candidates, incomplete = computer_ax.ax_window_candidates(
                    self.window_id, computer_use_macos._main_geometry(computer_use_macos._active_displays()))
                show = [c for c in candidates if c.description == "Show Sidebar"]
                if incomplete or len(show) != 1:
                    raise RuntimeError("Sidebar restoration unconfirmed")
                computer_ax.ax_press(show[0].element)
            os.kill(self.pid, signal.SIGTERM)
            for _ in range(40):
                pump()
                if not process_alive(self.pid):
                    break
            if process_alive(self.pid):
                raise RuntimeError("Owned application did not terminate")
        if self.path is not None:
            self.path.unlink(missing_ok=True)
        if self.original_front is not None and restore_front:
            self.original_front.activateWithOptions_(0)
            pump(0.1)
            evidence["frontmost_restored"] = computer_ax.ax_focused_pid() == self.original_front.processIdentifier()
        elif self.original_front is not None:
            evidence["user_focus_preserved"] = True
        evidence["confirmed"] = ((self.pid is None or not process_alive(self.pid))
                                 and evidence.get("position_restored", True)
                                 and evidence.get("frontmost_restored", True))
        return evidence


async def run_batch(output: Path, approved: str, *, mode: str, credential: str = "",
                    advisor_credential: str = "") -> dict[str, Any]:
    """Run only an already-frozen recipe; fake replaces model HTTP, never the native application."""
    import httpx2 as httpx
    import httpx as text_http
    from tank_backend.agents.approval import PendingToolCallStore, ToolApprovalPolicy
    from tank_backend.agents.definition import AgentDefinition
    from tank_backend.agents.resources import DesktopResource
    from tank_backend.agents.runner import AgentRunner
    from tank_backend.agents.subagent import SubAgentAuthorization
    from tank_backend.benchmarks.desktop_cleanup import MacOSInputCleanup
    from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
    from tank_backend.benchmarks.spend_http import ContextWindowContract
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, SpendLimitExceeded, TokenAllowance
    from tank_backend.config.app_config import AppConfig
    from tank_backend.llm.llm import LLM
    from tank_backend.pipeline.bus import Bus
    from tank_backend.plugin.manifest import read_manifest_from_yaml
    from tank_backend.plugin.registry import ExtensionRegistry
    from tank_backend.tools.manager import ToolManager
    from benchmarks.computer_use.jev_smoke import Capture

    frozen = load_freeze(output, approved)
    if mode not in {"fake", "live"} or mode == "live" and not (credential.strip() and advisor_credential.strip()):
        raise ValueError("Choose fake or provide an explicitly configured live credential")
    marker = output / "started.json"
    with marker.open("x") as stream:
        json.dump({"mode": mode, "sha256": approved}, stream)
    ledger = SpendLedger(SpendLimit(12_000_000, frozen["nano_usd_limit"]),
                         request_limit=frozen["request_limit"], journal=output / "spend.jsonl")
    registry = ExtensionRegistry()
    manifest = read_manifest_from_yaml(Path(__file__).resolve().parents[2] / "plugins/agent-computer-use/plugin.yaml")
    for extension in manifest.extensions:
        registry.register(manifest.plugin_name, extension)
    definition = AgentDefinition("s4-ax", "Native AX pilot", "Use only the bound application.",
                                 extension="agent-computer-use:agent", decision_model="jev", model="advisor")
    resource = DesktopResource()
    rows = [{"case_id": case["id"], "status": "not_run", "passed": False} for case in frozen["cases"]]
    active_case, fake_index, fake_received = frozen["cases"][0], 0, 0
    endpoint = frozen["model"]["url"] if mode == "live" else frozen["fake_endpoint"]
    advisor_model = frozen["advisor_model"]
    advisor_endpoint = advisor_model["url"] if mode == "live" else frozen["fake_advisor_endpoint"]
    fake_escalated = False

    async def fake_http(request: httpx.Request) -> httpx.Response:
        nonlocal fake_index, fake_received, fake_escalated
        fake_received += 1
        payload = json.loads(request.content)
        criteria = payload["questions"]["next_action"]["criteria"]
        if active_case["application"] == "calculator":
            if not fake_escalated:
                fake_escalated = True
                return httpx.Response(200, json={"model": frozen["model"]["model"], "answers": {
                    "next_action": {"type": "choice", "choice": "escalate", "confidence": 1,
                                    "probabilities": {key: int(key == "escalate") for key in criteria}}},
                    "usage": {"input_tokens": 12, "output_tokens": 0}})
            labels = ("7", "Multiply", "8", "Equals")
            label = labels[fake_index] if fake_index < len(labels) else None
            choice = next((key for key, value in criteria.items()
                           if isinstance(value, dict) and value.get("label") == label), "none")
        else:
            choice = next((key for key, value in criteria.items()
                           if isinstance(value, dict) and value.get("operation") == "fill"), "none")
        fake_index += 1
        return httpx.Response(200, json={"model": frozen["model"]["model"], "answers": {
            "next_action": {"type": "choice", "choice": choice, "confidence": 1,
                            "probabilities": {key: int(key == choice) for key in criteria}}},
            "usage": {"input_tokens": 12, "output_tokens": 0}})

    async def fake_advice(request: text_http.Request) -> text_http.Response:
        nonlocal fake_index, fake_received
        fake_received += 1
        payload = json.loads(json.loads(request.content)["messages"][1]["content"])
        label = ("7", "Multiply", "8", "Equals")[fake_index]
        choice = next(key for key, value in payload["actions"].items() if value["label"] == label)
        fake_index += 1
        return text_http.Response(200, json={"id": "native-advice", "object": "chat.completion", "created": 1,
            "model": advisor_model["model"], "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps({"kind": "candidate", "candidate_id": choice})}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17}})

    class PilotCapture(Capture):
        async def response(self, call_id, response):
            await super().response(call_id, response)
            if "choices" in response:
                self.calls[call_id]["response"]["choices"] = response["choices"]

    class Policy(BenchmarkModelPolicy):
        def __init__(self, maximum: int):
            model = frozen["model"]
            super().__init__(ledger, (ContextWindowContract(
                endpoint, model["model"], TokenAllowance(
                    model["input_ceiling"], model["output_ceiling"], model["input_price"], model["output_price"]),
                "Frozen Jev conservative token-price contract", output_cap_required=False),
                ContextWindowContract(advisor_endpoint, advisor_model["model"], TokenAllowance(
                    advisor_model["input_ceiling"], advisor_model["output_ceiling"],
                    advisor_model["input_price"], advisor_model["output_price"]),
                    "Inherited S3 Qwen conservative reservation; output capped at 2048")))
            self.calls = 0
            self.maximum = maximum

        def reserve(self, call_id, request):
            if self.calls >= self.maximum:
                ledger.stop("trial_call_limit")
                raise SpendLimitExceeded("trial_call_limit")
            super().reserve(call_id, request)
            self.calls += 1

    report: dict[str, Any] = {"revision": frozen["revision"], "mode": mode, "sha256": approved,
                              "completed": False, "rows": rows}
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {"TANK_S4_JEV_KEY": credential if mode == "live" else "fake-native-pilot"}))
        if mode == "fake":
            stack.enter_context(fake_model_http(fake_http))
            stack.enter_context(patch("httpx.AsyncHTTPTransport", lambda *args, **kwargs: text_http.MockTransport(fake_advice)))
        try:
            for case, row in zip(frozen["cases"], rows, strict=True):
                load_freeze(output, approved)
                active_case, fake_index, fake_escalated = case, 0, False
                owner = OwnedApplication(case)
                capture, audits = PilotCapture(), []
                observer = PilotObserver()
                ledger.start_trial(case["id"], SpendLimit(4_000_000, frozen["nano_usd_limit"]))
                started = time.monotonic()
                row.update(status="started", dispatch=case["dispatch"])

                async def audit(record):
                    audits.append(asdict(record))

                try:
                    config = owner.start()
                    row["binding"] = config.model_dump(mode="json")
                    row["setup_actions"] = owner.setup_actions
                    app_config = AppConfig.from_raw_dict({
                        "llm": {"default": {"model": "unused", "api_key": "unused", "base_url": "https://unused.invalid/v1"},
                            "advisor": {"model": advisor_model["model"],
                                "api_key": advisor_credential if mode == "live" else "fake-advisor",
                                "base_url": advisor_endpoint.removesuffix("/chat/completions"),
                                "max_tokens": advisor_model["output_ceiling"], "temperature": 0,
                                "extra_body": {"enable_thinking": False}}},
                        "decision_models": {"jev": {"url": endpoint,
                            "model": frozen["model"]["model"], "credential_env": "TANK_S4_JEV_KEY"}},
                        "subagents": {"agent-computer-use:agent": {"config": {
                            "macos": config.model_dump(mode="json"), "selector": "jev", "advisor": "llm"}}},
                    })
                    runner = AgentRunner(MagicMock(spec=LLM), MagicMock(spec=ToolManager), Bus(),
                        ToolApprovalPolicy(computer_mode="allow"), PendingToolCallStore(),
                        {definition.name: definition}, registry=registry, app_config=app_config,
                        desktop_resource=resource)
                    outputs = [item async for item in runner.run_agent(
                        definition, [], task_id=case["id"], task_input=task_goal(case),
                        authorization=SubAgentAuthorization(frozenset({"desktop", "network"})),
                        model_policy=Policy(case["max_decisions"]), model_capture=capture, audit=audit,
                        observer=observer,
                        max_actions=case["max_decisions"], max_observations=1 + 3 * case["max_decisions"],
                        deadline=time.monotonic() + frozen["seconds_per_task"], desktop_cleanup=MacOSInputCleanup(),
                    )]
                    result = next(item.metadata["task_result"] for item in outputs if "task_result" in item.metadata)
                    row["result"] = result
                    values = owner.read_values()
                    row["independent_values"] = values
                    if case["application"] == "calculator":
                        valid = values.get("expression") == "7×8" and values.get("result") == "56"
                    else:
                        valid = values.get("document") == task_goal(case)["inputs"][0]["value"]
                    resolved = {(event["candidate_set_id"], event["model_choice"]): event["action_id"]
                                for event in observer.events if event["kind"] == "computer_use_proposal"
                                and event.get("source") == "jev"}
                    choices = {(call["request"]["state"]["binding"]["candidate_set_id"],
                                resolved.get((call["request"]["state"]["binding"]["candidate_set_id"],
                                              call["response"]["answers"]["next_action"]["choice"])))
                               for call in capture.calls.values() if call.get("response", {}).get("answers")}
                    executed = {(r["candidate_set_id"], r["action_id"]) for r in result["details"]["receipts"]
                                if r["status"] != "not_sent"}
                    row["passed"] = bool(valid and result["status"] == "completed"
                                         and result["cleanup"] == "confirmed" and choices & executed)
                    row["status"] = "finished"
                except asyncio.CancelledError:
                    ledger.stop("cancelled")
                    row["status"] = "cancelled"
                    raise
                except Exception as exc:
                    row.update(status="error", error_type=type(exc).__name__, error=str(exc))
                finally:
                    try:
                        row["application_cleanup"] = owner.close()
                    except Exception as exc:
                        row["application_cleanup"] = {"confirmed": False, "error": str(exc)}
                    row["passed"] = row["passed"] and row["application_cleanup"]["confirmed"]
                    row.update(calls=list(capture.calls.values()), audit=audits, events=observer.events,
                               elapsed_ms=(time.monotonic() - started) * 1000)
                    ledger.finish_trial()
                    (output / "result.json").write_text(json.dumps({**report, "spend": ledger.snapshot()}, ensure_ascii=False, indent=2) + "\n")
                print(json.dumps({"case_id": case["id"], "status": row["status"], "passed": row["passed"],
                                  "model_calls": len(row["calls"]), "error": row.get("error")}), flush=True)
                if not row["passed"] or ledger.snapshot()["stop_reason"]:
                    ledger.stop("native_case_failed")
                    break
            report["completed"] = all(row["passed"] for row in rows)
        finally:
            report["spend"] = ledger.snapshot()
            report["fake_http_requests"] = fake_received
            report["external_model_requests"] = sum(len(r.get("calls", [])) for r in rows) if mode == "live" else 0
            ledger.close()
            (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run", choices=("fake", "live"))
    parser.add_argument("--approved-sha256")
    args = parser.parse_args()
    if args.run is None:
        print(json.dumps({k: v for k, v in prepare(args.output).items()
                          if k in {"sha256", "request_limit", "nano_usd_limit"}}))
    else:
        if not args.approved_sha256:
            parser.error("Execution requires the frozen recipe digest")
        load_freeze(args.output, args.approved_sha256)
        credential = ""
        advisor_credential = ""
        if args.run == "live":
            from dotenv import dotenv_values
            credential = os.environ.get("TYPESAFE_API_KEY") or dotenv_values(
                Path(__file__).resolve().parents[2] / "core/.env").get("TYPESAFE_API_KEY") or ""
            advisor_credential = os.environ.get("BAILIAN_API_KEY") or dotenv_values(
                Path(__file__).resolve().parents[2] / "core/.env").get("BAILIAN_API_KEY") or ""
        result = asyncio.run(run_batch(args.output, args.approved_sha256, mode=args.run,
                                      credential=credential, advisor_credential=advisor_credential))
        raise SystemExit(0 if result["completed"] else 1)
