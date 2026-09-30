"""Local OCR: fake native Vision only, real PNG identity and M2 transforms."""

import io
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from tank_backend.tools.computer_observation import Observation


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
