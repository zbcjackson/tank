"""Frozen TextEdit text/image comparison; private color oracle never enters requests."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import inspect
import json
import platform
import plistlib
import time
from contextlib import ExitStack
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from dataclasses import replace
from typing import cast
from unittest.mock import patch

from agent_computer_use.channels.native import NativeAXChannel
from agent_computer_use.contracts import ActionSet, DecisionResult, GoalContract, Snapshot
from agent_computer_use.jev import check_eligible
from agent_computer_use.jev_image import JevImage, JevImageProbe, normalize_frame
from agent_computer_use.model_selector import ModelSelector
from agent_computer_use.model_view import Control, candidate_aliases, decision_question
from agent_computer_use.visual_selector import VisualFrame, VisualSelector
from tank_backend.agents.subagent import SubAgentContext, SubAgentStopped
from tank_backend.agents.task_runtime import TaskOperation
from tank_backend.llm.model_call import model_purpose
from tank_backend.tools.computer_native import run_native

from benchmarks.computer_use import jev_image_native, s4_ax
from benchmarks.computer_use.jev_image_dev import digest

ROOT = Path(__file__).resolve().parents[2]
BODY = "Jev visual probe\nNorth\nSouth\n"
VARIANTS = {"north": "Jev visual probe\nDONE\nSouth\n",
            "south": "Jev visual probe\nNorth\nDONE\n"}
INSTRUCTION = (
    "Replace only the red North or South line with DONE. Keep all other text unchanged. "
    "Choose exactly one of the supplied full-body replacement alternatives, not both. "
    "Formatting preservation is outside this test. Do not save or close the document."
)
BOXES = (
    {"id": "small", "target": "the italic button in the formatting toolbar", "cardinality": "one"},
    {"id": "absent", "target": "the Export CSV button in this document window", "cardinality": "none"},
    {"id": "several", "target": "the alignment buttons in the formatting toolbar", "cardinality": "several"},
)


def documents() -> dict[str, bytes]:
    prefix = (r"{\rtf1\ansi\deff0{\fonttbl{\f0 Helvetica;}}"
              r"{\colortbl;\red0\green0\blue0;\red220\green30\blue30;\red20\green80\blue210;}"
              r"\f0\fs36\cf1 Jev visual probe\par ")
    return {"scene-01": (prefix + r"\cf2 North\par \cf3 South\par }").encode(),
            "scene-02": (prefix + r"\cf3 North\par \cf2 South\par }").encode()}


def inputs() -> dict[str, bytes]:
    public = {"body": BODY, "variants": VARIANTS, "instruction": INSTRUCTION,
              "scene_ids": list(documents())}
    labels = {"scene-01": {"expected_variant": "north", "expected_body": VARIANTS["north"]},
              "scene-02": {"expected_variant": "south", "expected_body": VARIANTS["south"]}}
    return {"public.json": (json.dumps(public, ensure_ascii=False, indent=2) + "\n").encode(),
            "private/labels.json": (json.dumps(labels, indent=2) + "\n").encode(),
            **{"private/" + name + ".rtf": data for name, data in documents().items()}}


def trials(*, text_controls: bool = False) -> list[dict]:
    rows = []
    for position in range(2):
        for index, scene in enumerate(documents()):
            order = ("text", "image") if (index + position) % 2 == 0 else ("image", "text")
            for arm in order:
                rows.append({"id": f"{scene}-p{position}-{arm}", "scene": scene,
                    "kind": "task", "arm": arm, "move_window": bool(position)})
    if text_controls:
        for position in range(2):
            for index, scene in enumerate(documents()):
                for arm in (("text", "image") if (index + position) % 2 == 0 else ("image", "text")):
                    rows.append({"id": f"named-{scene}-p{position}-{arm}", "scene": scene,
                        "kind": "task", "arm": arm, "move_window": bool(position),
                        "named_target": "north" if index == 0 else "south"})
    rows.extend({"id": scene + "-box", "scene": scene, "kind": "box", "arm": "image",
                 "move_window": bool(index)} for index, scene in enumerate(documents()))
    return rows


def freeze_inputs(*, record_only: bool = False, text_controls: bool = False) -> dict:
    sources = jev_image_native.freeze_inputs()["source_sha256"].copy()
    sources[str(Path(__file__).relative_to(ROOT))] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    # The existing recipe pins the controller, models, geometry, source and owner.
    sources[str(Path(inspect.getfile(s4_ax)).relative_to(ROOT))] = hashlib.sha256(
        Path(inspect.getfile(s4_ax)).read_bytes()).hexdigest()
    path = Path("/System/Applications/TextEdit.app/Contents/Info.plist")
    info = plistlib.loads(path.read_bytes()) if path.exists() else {}
    return {"revision": "jev-image-ablation-2", "trials": trials(text_controls=text_controls),
        "record_only": record_only, "text_controls": text_controls, "boxes": list(BOXES),
        "source_sha256": sources,
        "input_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in inputs().items()},
        "model": dict(jev_image_native.MODEL),
        "application": {"bundle_id": "com.apple.TextEdit", "version": info.get("CFBundleShortVersionString"),
                        "build": info.get("CFBundleVersion"), "macos": platform.mac_ver()[0]},
        "versions": {name: version(name) for name in ("typesafe-sdk", "pillow")},
        "request_limit": None if record_only else (22 if text_controls else 14),
        "nano_usd_limit": 0 if record_only else 100_000_000, "token_limit": 0 if record_only else 4_000_000,
        "seconds_per_trial": 120, "primary_calls_per_trial": 1,
        "price_evidence": "https://docs.typesafe.ai/models ; 2026-10-18 ; frozen conservative context reservation",
        "scope": "new owned TextEdit process and seeded temporary RTF only; refuse existing sessions",
        "design": "two color assignments x two positions x two arms; one choice and at most one fill per task",
        "public_projection": "same current AX content, alternatives and instructions; private completion omitted; only image arm sends PNG",
        "boundary": "current plain AX observation package, not AX attributed-string capability ceiling",
        "box_interior_inset": 0.1, "retries": 0}


def prepare(output: Path, *, record_only: bool = False, text_controls: bool = False) -> dict:
    frozen = freeze_inputs(record_only=record_only, text_controls=text_controls)
    frozen["sha256"] = digest(frozen)
    output.mkdir(parents=True, exist_ok=False)
    (output / "private").mkdir()
    for name, data in inputs().items():
        (output / name).write_bytes(data)
    (output / "freeze.json").write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n")
    return frozen


def load_freeze(output: Path, approved: str) -> dict:
    stored = json.loads((output / "freeze.json").read_text())
    frozen = freeze_inputs(record_only=bool(stored.get("record_only")),
                           text_controls=bool(stored.get("text_controls")))
    frozen["sha256"] = digest(frozen)
    if (approved != frozen["sha256"]
            or json.loads((output / "freeze.json").read_text()) != frozen
            or any(hashlib.sha256((output / name).read_bytes()).hexdigest() != sha
                   for name, sha in frozen["input_sha256"].items())):
        raise ValueError("ablation freeze changed; prepare a new directory")
    return frozen


def instruction(trial: dict) -> str:
    if trial.get("named_target"):
        return (f"Replace only the {trial['named_target'].title()} line with DONE. Keep all other text unchanged. "
                "Choose exactly one supplied full-body alternative. Formatting preservation is outside this test. "
                "Do not save or close the document.")
    return INSTRUCTION


def goal(trial: dict, expected_body: str) -> dict:
    alternatives = list(VARIANTS.items())
    if trial.get("move_window"):
        alternatives.reverse()
    return {"schema_version": 2, "goal_id": trial["id"], "scope": trial["id"],
        "target": {"application": "com.apple.TextEdit"}, "authorization_ref": "current_task",
        "intent": instruction(trial), "objective": instruction(trial), "allowed_operations": ["fill"],
        "inputs": [{"key": name, "purpose": "Alternative complete-body replacement; choose only one",
                    "field_label": "First Text View", "value": value} for name, value in alternatives],
        "completion": [{"key": "ax:value:document", "value": expected_body}]}


def question(goal: GoalContract, snapshot: Snapshot, actions: ActionSet,
             image: JevImage, full_ax: dict) -> dict:
    """Identical semantic packet for both arms; the SDK adds only the image part."""
    if image.orientation != 1:
        raise ValueError("ablation requires upright images")
    packet = decision_question(goal, snapshot, actions)
    state = cast(dict[str, object], packet["state"])
    # This is a benchmark-only public projection. The controller retains its
    # original private completion and verifies it against fresh native values.
    cast(dict[str, object], state["goal"]).pop("completion")
    left, top, right, bottom = image.content
    sx = (right - left) / image.source.frame.image_size[0]
    sy = (bottom - top) / image.source.frame.image_size[1]
    bounds = dict(image.source.bounds)
    state.update(full_ax=full_ax, image_metadata=image.metadata(), image_candidates={
        alias: [left + bounds[action.target_ref][0] * sx, top + bounds[action.target_ref][1] * sy,
                bounds[action.target_ref][2] * sx, bounds[action.target_ref][3] * sy]
        for alias, action in candidate_aliases(actions).items()})
    questions = cast(dict[str, dict[str, object]], packet["questions"])
    questions["next_action"]["instructions"] = (
        "Choose one offered full-body replacement for the stated task, or abstain if evidence "
        "does not distinguish them. Input variants are alternatives, not sequential requirements. "
        "Completion is checked independently. Both arms retain all current AX descriptors; only "
        "the image arm attaches a PNG. image_candidates are [x,y,width,height] in attached-image "
        "pixels; snapshot bounds describe source geometry. Never infer text color from option "
        "order, opaque IDs or the private completion, which is not supplied."
    )
    return packet


async def full_ax(channel: NativeAXChannel, snapshot: Snapshot, context: SubAgentContext) -> dict:
    """Retain actual descriptions as extra evidence, without changing action admission."""
    def read() -> dict:
        window = channel.bound_window(context)
        if snapshot != channel.previous:
            raise SubAgentStopped("stale_reference")
        candidates, incomplete = s4_ax.computer_ax.ax_window_candidates(window.window_id, window.display_geometry)
        if channel.bound_window(context) != window:
            raise SubAgentStopped("window_changed")
        return {"incomplete": incomplete, "elements": [
            {name: getattr(item, name) for name in (
                "role", "title", "value", "description", "identifier", "actions", "enabled", "frame", "ancestors")}
            for item in candidates]}
    return await run_native(read)


class PairedSelector:
    """Benchmark-only one-decision selector; existing controller/executor remain authoritative."""

    def __init__(self, source: NativeAXChannel, arm: str) -> None:
        if arm not in {"text", "image"}:
            raise ValueError("unknown comparison arm")
        self.source, self.arm = source, arm
        self.visual = VisualSelector(source)
        self.extra: TaskOperation[Snapshot, dict] | None = None
        self.called = False
        self.image: JevImage | None = None
        self.captures: list[VisualFrame] = []

    def register(self, context: SubAgentContext) -> None:
        self.visual.register(context)
        self.extra = TaskOperation("ablation.full_ax", frozenset({"desktop"}), "read",
                                   lambda snapshot: full_ax(self.source, snapshot, context))
        context.runtime.register(self.extra)

    async def choose(self, goal: GoalContract, snapshot: Snapshot, actions: ActionSet,
                     context: SubAgentContext) -> DecisionResult:
        ModelSelector.check(context)
        if self.called:
            raise SubAgentStopped("comparison_decision_limit")
        check_eligible(goal, snapshot, replace(actions, reason="jev_eligible"))
        model = context.runtime.decision_model
        if model is None or not model.images_enabled:
            raise SubAgentStopped("decision_images_denied")
        previous = await self.visual.capture_frame(snapshot, actions, context)
        self.captures.append(previous)
        for _ in range(2):
            await asyncio.sleep(0.1)
            current = await self.visual.capture_frame(snapshot, actions, context)
            self.captures.append(current)
            if (current.frame.image_sha256, current.frame.image_size, current.frame.window_bounds) == (
                    previous.frame.image_sha256, previous.frame.image_size, previous.frame.window_bounds):
                break
            previous = current
        else:
            raise SubAgentStopped("unstable_visual_frame")
        image = normalize_frame(current)
        self.image = image
        assert self.extra is not None
        extra = await context.runtime.execute(self.extra, snapshot)
        packet = question(goal, snapshot, actions, image, extra)
        q = packet["questions"]["next_action"]
        self.called = True
        with model_purpose("computer_use.ablation." + self.arm):
            if self.arm == "image":
                answer = await model.choose_image(state=packet["state"], image=image.asset,
                    instructions=q["instructions"], options=q["criteria"])
            else:
                answer = await model.choose(state=packet["state"], instructions=q["instructions"], options=q["criteria"])
        ModelSelector.check(context)
        context.observe("computer_use_decision", source="ablation_" + self.arm,
            confidence=answer.confidence, probabilities=answer.probabilities, candidates=len(actions.actions))
        if answer.choice in {"none", "ambiguous", "need_more_context", "escalate"}:
            return DecisionResult(actions.binding, cast(
                Control, answer.choice), confidence=answer.confidence, probabilities=tuple(answer.probabilities.items()))
        action = candidate_aliases(actions).get(answer.choice)
        if action is None:
            raise SubAgentStopped("invalid_decision")
        context.observe("computer_use_proposal", source="ablation_" + self.arm, action_id=action.id,
            candidate_set_id=actions.binding.candidate_set_id, value=action.value,
            image_sent=self.arm == "image", confidence=answer.confidence)
        return DecisionResult(actions.binding, "candidate", action.id, answer.confidence, tuple(answer.probabilities.items()))


def preflight() -> None:
    quartz = importlib.import_module("Quartz")
    if (quartz.CGSessionCopyCurrentDictionary() or {}).get("CGSSessionScreenIsLocked", False):
        raise RuntimeError("desktop locked")
    foundation = importlib.import_module("Foundation")
    objc = importlib.import_module("objc")
    functions = {}
    bundle = foundation.NSBundle.bundleWithPath_(
        "/System/Library/Frameworks/ApplicationServices.framework/Frameworks/HIServices.framework")
    objc.loadBundleFunctions(bundle, functions, [("AXIsProcessTrusted", b"Z")])
    if not functions["AXIsProcessTrusted"]() or not quartz.CGPreflightScreenCaptureAccess():
        raise RuntimeError("Accessibility and screen capture permissions required")
    appkit = importlib.import_module("AppKit")
    if any(app.bundleIdentifier() == "com.apple.TextEdit"
           for app in appkit.NSWorkspace.sharedWorkspace().runningApplications()):
        raise RuntimeError("existing TextEdit session is not borrowed")


def select_heading(owner: s4_ax.OwnedApplication, config: s4_ax.native.NativeConfig) -> None:
    """Fixture setup: stop caret animation by selecting only the neutral title."""
    window = s4_ax.native.read_window(config)
    if not s4_ax.native.inputs_idle() or owner.read_values() != {"document": BODY}:
        raise RuntimeError("header selection setup unavailable")
    nodes, incomplete = s4_ax.computer_ax.ax_window_candidates(
        window.window_id, window.display_geometry, include_descriptions=False)
    bodies = [item for item in nodes if item.role == "AXTextArea"
              and item.identifier == "First Text View" and item.pid == owner.pid]
    if incomplete or len(bodies) != 1:
        raise RuntimeError("header selection target unavailable")
    foundation = importlib.import_module("Foundation")
    objc = importlib.import_module("objc")
    functions = {}
    bundle = foundation.NSBundle.bundleWithPath_(
        "/System/Library/Frameworks/ApplicationServices.framework/Frameworks/HIServices.framework")
    objc.loadBundleFunctions(bundle, functions, [("AXValueCreate", b"@in^{_CFRange=qq}")])
    value = functions["AXValueCreate"](4, (0, len("Jev visual probe")))
    api = s4_ax.computer_ax._load_ax()
    error = api["AXUIElementSetAttributeValue"](bodies[0].element.native, "AXSelectedTextRange", value)
    s4_ax.pump(0.2)
    actual = api["AXUIElementCopyAttributeValue"](bodies[0].element.native, "AXSelectedText", None)
    if (error or actual != (0, "Jev visual probe") or owner.read_values() != {"document": BODY}
            or s4_ax.native.read_window(config) != window):
        raise RuntimeError("header selection not independently confirmed")
    owner.setup_actions.append("select_neutral_header")


def annotation(owner: s4_ax.OwnedApplication, box_id: str) -> list[tuple[int, int, int, int]]:
    """Independent bounded traversal; never query optional TextArea descriptions."""
    api = s4_ax.computer_ax._load_ax()
    height = s4_ax.computer_use_macos._main_geometry(s4_ax.computer_use_macos._active_displays())[4]
    queue = [(owner.bound_ax_window(api), 0)]
    found = []
    visited = 0
    labels = {"small": {"italic"}, "absent": {"Export CSV"},
              "several": {"align left", "align center", "align right", "fully justify"}}[box_id]
    while queue:
        element, depth = queue.pop(0)
        visited += 1
        if visited > 2000 or depth > 12:
            raise RuntimeError("annotation truncated")
        error, role = api["AXUIElementCopyAttributeValue"](element, "AXRole", None)
        if error or not role:
            raise RuntimeError("annotation role unreadable")
        if role in {"AXButton", "AXCheckBox", "AXPopUpButton", "AXMenuButton"}:
            names = []
            for key in ("AXTitle", "AXDescription", "AXIdentifier"):
                error, value = api["AXUIElementCopyAttributeValue"](element, key, None)
                if error not in (0, -25205, -25212):
                    raise RuntimeError("annotation label unreadable")
                names.append(value)
            if any(name in labels for name in names if isinstance(name, str)):
                rect = s4_ax.computer_ax._top_left_frame(api, element, height)
                if rect is None:
                    raise RuntimeError("annotation rectangle unavailable")
                found.append(rect)
        error, children = api["AXUIElementCopyAttributeValue"](element, "AXChildren", None)
        if error not in (0, -25205, -25212) or children is not None and len(children) > 64:
            raise RuntimeError("annotation children unreadable")
        queue.extend((child, depth + 1) for child in children or [])
    if len(found) != {"small": 1, "absent": 0, "several": 4}[box_id]:
        raise RuntimeError("independent target cardinality changed")
    return found


async def run_batch(output: Path, approved: str, *, mode: str, credential: str = "") -> dict:
    import httpx2
    from agent_computer_use import create_subagent
    from agent_computer_use.channels import native
    from tank_backend.agents.resources import DESKTOP_RESOURCE
    from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentRequest
    from tank_backend.agents.task_result import TaskResult
    from tank_backend.agents.task_runtime import ExecutionRecord
    from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
    from tank_backend.benchmarks.spend_http import ContextWindowContract
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, SpendLimitExceeded, TokenAllowance
    from tank_backend.llm.decision_model import BoxResult
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.llm.model_data import ModelDataScope, ModelRequest

    frozen = load_freeze(output, approved)
    if mode not in {"fake", "live"} or mode == "live" and not credential.strip():
        raise ValueError("choose fake or supply Jev credential")
    if any((output / name).exists() for name in ("started.json", "result.json", "calls.jsonl", "audit.jsonl", "actions.jsonl", "spend.jsonl")):
        raise FileExistsError("started ablation directories cannot be resumed")
    if mode == "live":
        preflight()
    (output / "started.json").write_text(json.dumps({"mode": mode, "sha256": approved}) + "\n")
    (output / "images").mkdir()
    rows = [{**trial, "status": "not_run", "passed": False, "native_actions": [], "frames": [],
             **({"boxes": [{**b, "status": "not_run"} for b in frozen["boxes"]]} if trial["kind"] == "box" else {})}
            for trial in frozen["trials"]]
    report = {"sha256": approved, "mode": mode, "completed": False, "rows": rows}
    labels = json.loads((output / "private/labels.json").read_text())
    ledger = SpendLedger(SpendLimit(frozen["token_limit"], frozen["nano_usd_limit"]),
        request_limit=frozen["request_limit"], record_only=frozen["record_only"], journal=output / "spend.jsonl")
    model = frozen["model"]
    endpoint = model["url"] if mode == "live" else "https://ablation.invalid/v1/systemone"
    contract = ContextWindowContract(endpoint, model["model"], TokenAllowance(
        model["input_ceiling"], model["output_ceiling"], model["input_price"], model["output_price"]),
        frozen["price_evidence"], output_cap_required=False)

    def persist() -> None:
        report["spend"] = ledger.snapshot()
        (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    try:
        with ExitStack() as files:
            calls = files.enter_context((output / "calls.jsonl").open("x"))
            audit_file = files.enter_context((output / "audit.jsonl").open("x"))
            actions_file = files.enter_context((output / "actions.jsonl").open("x"))
            for row in rows:
                load_freeze(output, approved)
                ledger.start_trial(row["id"], SpendLimit(2_000_000, frozen["nano_usd_limit"]))
                owner = s4_ax.OwnedApplication(cast(s4_ax.PilotCase, {"id": row["id"], "application": "textedit",
                    "dispatch": "ax_press", "repeat": 0, "max_decisions": 1, "move_window": row["move_window"]}),
                    rtf=(output / ("private/" + row["scene"] + ".rtf")).read_bytes())
                context = plugin = selector = channel = None
                class Observer(s4_ax.PilotObserver):
                    def on_event(self, kind: str, metadata: dict[str, object]) -> None:
                        if kind == "computer_use_freshness":
                            self.events.append({"kind": kind, **metadata})
                        else:
                            super().on_event(kind, metadata)
                observer = Observer()
                started = time.monotonic()
                expected = VARIANTS[row["named_target"]] if row.get("named_target") else labels[row["scene"]]["expected_body"]
                box_label = None

                class Policy(BenchmarkModelPolicy):
                    count = 0

                    def reserve(self, call_id: str, request: ModelRequest) -> None:
                        limit = 3 if row["kind"] == "box" else 1
                        images = int(row["arm"] == "image")
                        if self.count >= limit or len(request.images) != images:
                            ledger.stop("ablation_call_policy")
                            raise SpendLimitExceeded("ablation_call_policy")
                        super().reserve(call_id, request)
                        self.count += 1

                class Capture:
                    async def request(self, call_id: str, request: ModelRequest) -> None:
                        images = []
                        for asset in request.images:
                            path = output / "images" / (call_id + ".png")
                            with path.open("xb") as stream:
                                stream.write(asset.data)
                            images.append({"path": str(path.relative_to(output)), "part": asset.part,
                                "sha256": hashlib.sha256(asset.data).hexdigest(), "bytes": len(asset.data)})
                        calls.write(json.dumps({"trial": row["id"], "call_id": call_id, "purpose": request.purpose,
                            "request": request.parameters, "images": images, "headers": dict(request.headers)}, ensure_ascii=False) + "\n")
                        calls.flush()
                        if row["kind"] == "task":
                            questions = cast(dict[str, dict[str, object]], request.parameters["questions"])
                            row["criteria"] = questions["next_action"]["criteria"]

                    async def response(self, call_id: str, response: dict[str, object]) -> None:
                        calls.write(json.dumps({"trial": row["id"], "call_id": call_id, "response": response}, ensure_ascii=False) + "\n")
                        calls.flush()
                        if row["kind"] == "task":
                            row["model_answer"] = response

                async def audit(record: ExecutionRecord) -> None:
                    audit_file.write(json.dumps(asdict(record)) + "\n")
                    audit_file.flush()

                async def fake_http(request: httpx2.Request) -> httpx2.Response:
                    from email.parser import BytesParser
                    from email.policy import default
                    if request.headers["content-type"].startswith("multipart/"):
                        message = BytesParser(policy=default).parsebytes(
                            ("Content-Type: " + request.headers["content-type"] + "\r\n\r\n").encode() + request.content)
                        raw = list(message.iter_parts())[0].get_payload(decode=True)
                        assert isinstance(raw, bytes)
                        payload = json.loads(raw)
                    else:
                        payload = json.loads(request.content)
                    if row["kind"] == "box":
                        answers = {"cardinality": {"type": "choice", "choice": "one", "confidence": 1,
                            "probabilities": {"none": 0, "one": 1, "several": 0}},
                            "target": {"type": "box", "box": {"left": .1, "top": .1, "right": .2, "bottom": .2}, "confidence": .5}}
                    else:
                        criteria = payload["questions"]["next_action"]["criteria"]
                        choice = ("need_more_context" if row["arm"] == "text" and not row.get("named_target") else next(k for k, v in criteria.items()
                            if isinstance(v, dict) and v.get("value") == expected))
                        answers = {"next_action": {"type": "choice", "choice": choice, "confidence": 1,
                            "probabilities": {k: float(k == choice) for k in criteria}}}
                    return httpx2.Response(200, json={"model": model["model"], "answers": answers,
                                                    "usage": {"input_tokens": 10, "output_tokens": 2}})

                original_capture = NativeAXChannel.capture

                async def recorded_capture(source: NativeAXChannel, snapshot: Snapshot,
                                           ctx: SubAgentContext) -> VisualFrame:
                    captured = await original_capture(source, snapshot, ctx)
                    path = "images/" + row["id"] + f"-trace-{len(row['frames'])}.png"
                    (output / path).write_bytes(captured.png)
                    row["frames"].append({"box": box_label, "path": path,
                        "observation_id": captured.observation_id, "frame": asdict(captured.frame)})
                    persist()
                    return captured

                original_fill = native.ax_set_value

                def witnessed_fill(ref: s4_ax.computer_ax.AXElementRef, value: str) -> None:
                    api = s4_ax.computer_ax._load_ax()
                    error, pid = api["AXUIElementGetPid"](ref.native, None)
                    if (row["kind"] != "task" or error or pid != owner.pid or value not in VARIANTS.values()
                            or s4_ax.computer_ax._attr(api, ref.native, "AXRole") != "AXTextArea"
                            or s4_ax.computer_ax._attr(api, ref.native, "AXIdentifier") != "First Text View"):
                        raise RuntimeError("fill outside owned comparison document")
                    item = {"pid": pid, "value": value, "status": "unknown"}
                    row["native_actions"].append(item)
                    actions_file.write(json.dumps({"trial": row["id"], **item}) + "\n")
                    actions_file.flush()
                    original_fill(ref, value)
                    item["status"] = "returned"
                    actions_file.write(json.dumps({"trial": row["id"], **item}) + "\n")
                    actions_file.flush()

                async with DESKTOP_RESOURCE.acquire(started + frozen["seconds_per_trial"]):
                    with ExitStack() as stack:
                        if mode == "fake":
                            stack.enter_context(s4_ax.fake_model_http(fake_http))
                        stack.enter_context(patch.object(native, "ax_set_value", witnessed_fill))
                        stack.enter_context(patch.object(NativeAXChannel, "capture", recorded_capture))
                        try:
                            row["status"] = "started"
                            config = owner.start()
                            select_heading(owner, config)
                            row.update(binding=config.model_dump(mode="json"), setup_actions=owner.setup_actions,
                                       initial_values=owner.read_values())
                            if row["initial_values"] != {"document": BODY}:
                                raise RuntimeError("RTF did not render expected body")
                            context = SubAgentContext(SubAgentAuthorization(frozenset({"desktop", "network"})),
                                SubAgentBudget(), asyncio.Event(), deadline=started + frozen["seconds_per_trial"],
                                max_actions=2, max_observations=64, observer=observer, audit=audit,
                                model_policy=Policy(ledger, (contract,)), model_capture=Capture(),
                                model_data_scope=ModelDataScope(frozenset({"text", "image"}), 32 * 1024 * 1024))
                            context.runtime.configure_decision_model(row["id"], DecisionModelProfile(
                                endpoint, model["model"], "TYPESAFE_API_KEY", images=True), credential=credential if mode == "live" else "fixture")
                            if row["kind"] == "task":
                                plugin = create_subagent({"macos": {"profiles": {"com.apple.TextEdit":
                                    s4_ax.macos_policy()["profiles"]["com.apple.TextEdit"]}}})
                                channel = plugin.controller.source
                                assert isinstance(channel, NativeAXChannel)
                                selector = PairedSelector(channel, row["arm"])
                                selector.register(context)
                                plugin.controller.selector = selector
                                outputs = [o async for o in plugin.run(SubAgentRequest(instruction(row), "", row["id"], goal(row, expected)), context)]
                                row["result"] = outputs[-1].metadata["task_result"]
                                row["independent_values"] = owner.read_values()
                                answer = row.get("model_answer", {})
                                selected = row.get("criteria", {}).get(answer.get("choice"), {})
                                row["model_correct"] = isinstance(selected, dict) and selected.get("value") == expected
                                row["model_abstained"] = answer.get("choice") in {"none", "ambiguous", "need_more_context", "escalate"}
                                proposals = {(e["candidate_set_id"], e["action_id"]) for e in observer.events
                                    if e["kind"] == "computer_use_proposal" and e.get("source") == "ablation_" + row["arm"]}
                                receipts = {(r["candidate_set_id"], r["action_id"]) for r in row["result"]["details"]["receipts"] if r["status"] == "sent"}
                                row["selection_executed"] = len(proposals & receipts)
                                row["passed"] = (row["result"]["status"] == "completed"
                                    and row["independent_values"] == {"document": expected}
                                    and row["native_actions"] == [{"pid": owner.pid, "value": expected, "status": "returned"}]
                                    and row["selection_executed"] == 1)
                                reason = row["result"]["reason"]
                                known = {"goal_verified", "none", "ambiguous", "need_more_context", "escalate", "invalid_decision",
                                         "no_progress", "action_limit", "comparison_decision_limit", "stale_reference", "unstable_visual_frame"}
                                if reason == "not_sent" and not row["native_actions"]:
                                    known.add("not_sent")
                                if row["result"]["status"] == "unknown" or context.budget.unknown_calls or reason not in known:
                                    ledger.stop("ablation_unsettled")
                                if selector.image is not None:
                                    (output / "images" / (row["id"] + "-observed.png")).write_bytes(selector.image.source.png)
                                    (output / "images" / (row["id"] + "-prepared.png")).write_bytes(selector.image.asset.data)
                                row["capture_frames"] = [asdict(frame.frame) for frame in selector.captures]
                                for index, frame in enumerate(selector.captures):
                                    (output / "images" / f"{row['id']}-capture-{index}.png").write_bytes(frame.png)
                            else:
                                channel = NativeAXChannel(config=config)
                                observe: TaskOperation[str, Snapshot] = TaskOperation(
                                    "ablation.observe", frozenset({"desktop"}), "read",
                                    lambda scope, source=channel, ctx=context: source.observe(scope, ctx))
                                context.runtime.register(observe)
                                probe = JevImageProbe(channel, context)
                                annotate: TaskOperation[str, list[tuple[int, int, int, int]]] = TaskOperation(
                                    "ablation.annotation", frozenset({"desktop"}), "read",
                                    lambda box_id: run_native(annotation, owner, box_id))
                                context.runtime.register(annotate)
                                snapshot = await context.runtime.execute(observe, row["id"])
                                for box in row["boxes"]:
                                    box_label = box["id"]
                                    try:
                                        prepared, answer = await probe.assess(snapshot,
                                            state={"task": "Read-only localization; no action authorized."}, instructions=box["target"])
                                        assert isinstance(answer, BoxResult)
                                        rectangles = await context.runtime.execute(annotate, box["id"])
                                        point = prepared.map_box(answer.box) if box["cardinality"] == answer.cardinality.choice == "one" else None
                                        interior = None
                                        hit = False
                                        if point is not None:
                                            x, y, width, height = rectangles[0]
                                            inset = min(width, height) * frozen["box_interior_inset"]
                                            interior = [x + inset, y + inset, x + width - inset, y + height - inset]
                                            hit = interior[0] <= point[0] <= interior[2] and interior[1] <= point[1] <= interior[3]
                                        box.update(status="returned", answer=asdict(answer), screen_point=point,
                                            independent_rectangles=rectangles, independent_interior=interior,
                                            correct=answer.cardinality.choice == box["cardinality"] and (box["cardinality"] != "one" or hit),
                                            native_actions_added=len(row["native_actions"]))
                                        (output / "images" / (row["id"] + "-" + box["id"] + ".png")).write_bytes(prepared.source.png)
                                    except SubAgentStopped as exc:
                                        box.update(status="rejected", reason=exc.reason)
                                        if exc.reason != "stale_visual_frame" or context.budget.unknown_calls:
                                            raise
                                row["independent_values"] = owner.read_values()
                                row["passed"] = (row["independent_values"] == {"document": BODY} and not row["native_actions"])
                            row["status"] = "finished"
                        except asyncio.CancelledError:
                            row["status"] = "cancelled"
                            ledger.stop("cancelled")
                            raise
                        except Exception as exc:
                            row.update(status="error", error_type=type(exc).__name__)
                            ledger.stop("ablation_error")
                        finally:
                            errors = []
                            interrupted = None
                            channel_resource = channel if isinstance(channel, NativeAXChannel) and plugin is None else None
                            for resource in (context.runtime if context is not None else None, plugin, channel_resource):
                                if resource is not None:
                                    try:
                                        await resource.aclose()
                                    except BaseException as exc:
                                        errors.append(type(exc).__name__)
                                        if not isinstance(exc, Exception):
                                            interrupted = exc
                            try:
                                row["application_cleanup"] = owner.close()
                            except Exception as exc:
                                row["application_cleanup"] = {"confirmed": False, "error_type": type(exc).__name__}
                            row["cleanup_confirmed"] = not errors and row["application_cleanup"]["confirmed"]
                            row["passed"] = row["passed"] and row["cleanup_confirmed"]
                            if "result" in row:
                                row["result"] = TaskResult.model_validate(row["result"]).with_cleanup(
                                    "confirmed" if row["cleanup_confirmed"] else "unknown").model_dump(mode="json")
                            if not row["cleanup_confirmed"]:
                                ledger.stop("cleanup_failed")
                                DESKTOP_RESOURCE.quarantine("ablation cleanup unconfirmed")
                            row.update(events=observer.events, cleanup_errors=errors,
                                elapsed_ms=(time.monotonic() - started) * 1000,
                                known_tokens=context.budget.total_tokens if context is not None else 0)
                            ledger.finish_trial()
                            persist()
                            if interrupted is not None:
                                raise interrupted
                if ledger.snapshot()["stop_reason"]:
                    break
            report["completed"] = ledger.snapshot()["stop_reason"] is None and all(
                r["status"] == "finished" and r["cleanup_confirmed"] for r in rows)
    finally:
        ledger.close()
        persist()
    return report


def main() -> None:
    import argparse
    import os
    from dotenv import dotenv_values
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run", choices=("fake", "live"))
    parser.add_argument("--approved-sha256")
    parser.add_argument("--record-only", action="store_true")
    parser.add_argument("--text-controls", action="store_true")
    args = parser.parse_args()
    if args.run is None:
        if args.approved_sha256:
            parser.error("a digest requires --run")
        frozen = prepare(args.output, record_only=args.record_only, text_controls=args.text_controls)
        print(json.dumps({k: frozen[k] for k in ("sha256", "request_limit", "nano_usd_limit")}))
        return
    if args.record_only or args.text_controls:
        parser.error("record-only/text-controls are preparation options; execution uses the frozen settings")
    if not args.approved_sha256:
        parser.error("execution requires the reviewed frozen digest")
    load_freeze(args.output, args.approved_sha256)
    key = (os.environ.get("TYPESAFE_API_KEY") or dotenv_values(ROOT / "core/.env").get("TYPESAFE_API_KEY") or "") if args.run == "live" else ""
    report = asyncio.run(run_batch(args.output, args.approved_sha256, mode=args.run, credential=key))
    print(json.dumps({"completed": report["completed"], "spend": report["spend"]["batch"], "stop_reason": report["spend"]["stop_reason"]}))
    raise SystemExit(0 if report["completed"] else 1)


if __name__ == "__main__":
    main()
