"""Local OCR: fake native Vision only, real PNG identity and M2 transforms."""

import io
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from tank_backend.tools.computer_observation import Observation

from .test_native import world as shared_world  # noqa: F401


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
