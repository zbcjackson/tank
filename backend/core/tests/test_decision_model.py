"""Provider calls are usable independently of task/runtime/HTTP governance."""

import httpx2
import pytest


@pytest.mark.parametrize("image_format", ["PNG", "JPEG"])
async def test_official_sdk_image_box_multipart_and_default_compression(monkeypatch, image_format):
    import io
    import json
    from email.parser import BytesParser
    from email.policy import default

    from PIL import Image as PILImage
    from typesafe_sdk import AsyncTypeSafeClient, Box, Choice, Image, RetryPolicy

    png = io.BytesIO()
    PILImage.new("RGB", (280, 280), "white").save(png, image_format)
    captured = []

    async def respond(request):
        body = request.content
        if request.headers.get("content-encoding") == "zstd":
            import importlib
            import sys

            codec = importlib.import_module(
                "compression.zstd" if sys.version_info >= (3, 14) else "backports.zstd"
            )
            body = codec.decompress(body)
        envelope = BytesParser(policy=default).parsebytes(
            ("Content-Type: " + request.headers["content-type"] + "\r\n\r\n").encode() + body
        )
        parts = list(envelope.iter_parts())
        payload = parts[0].get_payload(decode=True)
        assert isinstance(payload, bytes)
        data = json.loads(payload)
        assert parts[0].get_param("name", header="content-disposition") == "request"
        assert data["assets"]["photo"] == {"type": "image", "part": "asset-0"}
        assert parts[1].get_payload(decode=True) == png.getvalue()
        assert parts[1].get_content_type() == (
            "image/png" if image_format == "PNG" else "image/jpeg")
        assert request.headers["TypeSafe-Danger-Zone-Images"] == "true"
        captured.append(data)
        result = response("a")
        result["model"] = "jev-1.14.0"
        result["answers"]["target"] = {
            "type": "box",
            "box": {"top": 0.1, "left": 0.2, "bottom": 0.4, "right": 0.5},
            "confidence": 0.8,
        }
        return httpx2.Response(200, json=result)

    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kw: httpx2.MockTransport(respond))
    async with AsyncTypeSafeClient(
        api_key="test",
        model="jev-1.14.0",
        base_url="https://offline.invalid",
        retry=RetryPolicy(max_retries=0),
    ) as client:
        result = await client.system_one(
            state={"image": "photo"},
            assets={"photo": Image(png.getvalue())},
            questions={
                "next_action": Choice(instructions="Choose", criteria={"a": "A", "b": "B"}),
                "target": Box(instructions="Find A in `image`"),
            },
            extra_headers={"TypeSafe-Danger-Zone-Images": "true"},
        )
        assert result.boxes["target"].box.left == 0.2
        assert len(captured) == 1


async def test_governed_image_choice_capture_matches_multipart(monkeypatch):
    import asyncio
    import io
    import json
    from email.parser import BytesParser
    from email.policy import default

    from PIL import Image

    from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.llm.model_data import ModelDataScope, ModelImageAsset

    png = io.BytesIO()
    Image.new("RGB", (280, 280), "white").save(png, "PNG")
    image = ModelImageAsset("tank-image-" + "a" * 32, "asset-0", "image/png", png.getvalue())
    captures, sent = [], []

    class Capture:
        async def request(self, call_id, request):
            captures.append((call_id, request))
            request.parameters["state"]["task"] = "redacted by recorder"

        async def response(self, call_id, response):
            pass

    async def respond(request):
        sent.append(request)
        assert request.headers["TypeSafe-Danger-Zone-Images"] == "true"
        assert "content-encoding" not in request.headers
        message = BytesParser(policy=default).parsebytes(
            ("Content-Type: " + request.headers["content-type"] + "\r\n\r\n").encode()
            + request.content
        )
        parts = list(message.iter_parts())
        payload = parts[0].get_payload(decode=True)
        assert isinstance(payload, bytes)
        data = json.loads(payload)
        assert data["state"]["task"] == "choose"
        assert data["state"]["image"] == image.reference
        assert parts[1].get_payload(decode=True) == captures[0][1].images[0].data
        result = response()
        result["model"] = "jev-1.14.0"
        return httpx2.Response(200, json=result)

    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kw: httpx2.MockTransport(respond))
    ctx = SubAgentContext(
        SubAgentAuthorization(frozenset({"network"})),
        SubAgentBudget(),
        asyncio.Event(),
        model_capture=Capture(),
        model_data_scope=ModelDataScope(frozenset({"text", "image"})),
    )
    ctx.runtime.configure_decision_model(
        "image-task",
        DecisionModelProfile(
            "https://offline.invalid/v1/systemone", "jev-1.14.0", "KEY", images=True
        ),
        credential="test",
    )
    try:
        model = ctx.runtime.decision_model
        assert model is not None
        result = await model.choose_image(
            state={"task": "choose"},
            image=image,
            instructions="Choose",
            options={"a": "A", "b": "B"},
        )
        assert result.choice == "a" and result.confidence == 1.0
        assert len(sent) == len(captures) == ctx.budget.call_count == 1
        assert ctx.budget.total_tokens == 9
    finally:
        await ctx.runtime.aclose()


@pytest.mark.parametrize("count", ["none", "one", "several"])
async def test_box_requires_same_request_cardinality_and_returns_evidence_only(monkeypatch, count):
    import io

    from PIL import Image

    from tank_backend.llm.decision_model import DecisionModel
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.llm.model_data import ModelImageAsset

    png = io.BytesIO()
    Image.new("RGB", (280, 280), "white").save(png, "PNG")
    image = ModelImageAsset("tank-image-" + "a" * 32, "asset-0", "image/png", png.getvalue())
    requests = []

    async def respond(request):
        requests.append(request)
        assert b'"cardinality"' in request.content and b'"box"' in request.content
        assert b'"none"' in request.content and b'"several"' in request.content
        return httpx2.Response(
            200,
            json={
                "model": "jev-1.14.0",
                "answers": {
                    "cardinality": {
                        "type": "choice",
                        "choice": count,
                        "confidence": 0.9,
                        "probabilities": {
                            key: float(key == count) for key in ("none", "one", "several")
                        },
                    },
                    "target": {
                        "type": "box",
                        "box": {"left": 0.2, "top": 0.1, "right": 0.5, "bottom": 0.4},
                        "confidence": 0.8,
                    },
                },
                "usage": {"input_tokens": 13, "output_tokens": 4},
            },
        )

    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kw: httpx2.MockTransport(respond))
    model = DecisionModel(
        DecisionModelProfile(
            "https://offline.invalid/v1/systemone", "jev-1.14.0", "KEY", images=True
        ),
        credential="test",
    )
    try:
        result = await model.locate_image(state={}, image=image, target="the Save button")
        assert result.cardinality.choice == count and result.confidence == 0.8
        assert result.box == (0.2, 0.1, 0.5, 0.4)
        assert result.input_tokens == 13 and result.output_tokens == 4
        assert result.cardinality.input_tokens is None
        assert len(requests) == 1
    finally:
        await model.aclose()


@pytest.mark.parametrize(
    "fault",
    ["mime", "dimensions", "reference", "receiver", "model", "format", "orientation", "part"],
)
async def test_image_rejection_precedes_sdk_allocation(monkeypatch, fault):
    import asyncio
    import io

    from PIL import Image

    from tank_backend.agents.subagent import (
        SubAgentAuthorization,
        SubAgentBudget,
        SubAgentContext,
        SubAgentStopped,
    )
    from tank_backend.llm import decision_model
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.llm.model_data import ModelDataScope, ModelImageAsset

    buffer = io.BytesIO()
    image = Image.new("RGB", (100, 100) if fault == "dimensions" else (280, 280), "white")
    exif = Image.Exif()
    if fault == "orientation":
        exif[274] = 6
    image.save(buffer, "GIF" if fault == "format" else "PNG", exif=exif)
    asset = ModelImageAsset(
        "bad" if fault == "reference" else "tank-image-" + "a" * 32,
        "asset-1" if fault == "part" else "asset-0",
        "image/jpeg" if fault == "mime" else "image/png",
        buffer.getvalue(),
    )

    def forbidden(**kwargs):
        raise AssertionError("invalid image allocated SDK client")

    monkeypatch.setattr(decision_model, "AsyncTypeSafeClient", forbidden)
    ctx = SubAgentContext(
        SubAgentAuthorization(frozenset({"network"})),
        SubAgentBudget(),
        asyncio.Event(),
        model_data_scope=ModelDataScope(frozenset({"text", "image"})),
    )
    ctx.runtime.configure_decision_model(
        "task",
        DecisionModelProfile(
            "https://offline.invalid/v1/systemone",
            "jev-9.0.0" if fault == "model" else "jev-1.14.0",
            "KEY",
            images=fault != "receiver",
        ),
        credential="test",
    )
    try:
        model = ctx.runtime.decision_model
        assert model is not None
        with pytest.raises(SubAgentStopped, match="invalid_decision_image"):
            await model.choose_image(
                state={}, image=asset, instructions="Choose", options={"a": "A"}
            )
        assert ctx.budget.call_count == 0
    finally:
        await ctx.runtime.aclose()


@pytest.mark.parametrize("task_bound", [False, True])
async def test_image_choice_cannot_auto_attach_undeclared_sdk_images(monkeypatch, task_bound):
    import asyncio
    import io

    from PIL import Image
    from typesafe_sdk import Image as SDKImage

    from tank_backend.agents.subagent import (
        SubAgentAuthorization,
        SubAgentBudget,
        SubAgentContext,
        SubAgentStopped,
    )
    from tank_backend.llm import decision_model
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.llm.model_data import ModelDataScope, ModelImageAsset
    from tank_backend.llm.task_decision_model import TaskDecisionModel

    buffer = io.BytesIO()
    Image.new("RGB", (280, 280)).save(buffer, "PNG")
    asset = ModelImageAsset("tank-image-" + "a" * 32, "asset-0", "image/png", buffer.getvalue())

    def forbidden(**kwargs):
        raise AssertionError("undeclared image reached SDK")

    monkeypatch.setattr(decision_model, "AsyncTypeSafeClient", forbidden)
    model = decision_model.DecisionModel(
        DecisionModelProfile(
            "https://offline.invalid/v1/systemone", "jev-1.14.0", "KEY", images=True
        ),
        credential="test",
    )
    ctx = SubAgentContext(
        SubAgentAuthorization(frozenset({"network"})),
        SubAgentBudget(),
        asyncio.Event(),
        model_data_scope=ModelDataScope(frozenset({"text", "image"})),
    )
    task = TaskDecisionModel("task", ctx, model)
    try:
        options: dict[str, object] = {"a": {"example": SDKImage(b"not an approved image file")}}
        if task_bound:
            with pytest.raises(SubAgentStopped, match="invalid_decision_image"):
                await task.choose_image(
                    state={}, image=asset, instructions="Choose", options=options
                )
        else:
            with pytest.raises(ValueError, match="invalid_decision_image"):
                await model.choose_image(
                    state={}, image=asset, instructions="Choose", options=options
                )
        assert ctx.budget.call_count == 0
    finally:
        await task.aclose()
        await model.aclose()


@pytest.mark.parametrize("options", [{}, {"": "A"}, {"a": 7}])
async def test_task_image_choice_rejects_invalid_options_before_capture_or_usage(
    monkeypatch, options,
):
    import asyncio
    import io

    from PIL import Image

    from tank_backend.agents.subagent import (
        SubAgentAuthorization,
        SubAgentBudget,
        SubAgentContext,
        SubAgentStopped,
    )
    from tank_backend.llm import decision_model
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.llm.model_data import ModelDataScope, ModelImageAsset
    from tank_backend.llm.task_decision_model import TaskDecisionModel

    buffer = io.BytesIO()
    Image.new("RGB", (280, 280)).save(buffer, "PNG")
    asset = ModelImageAsset("tank-image-" + "a" * 32, "asset-0", "image/png", buffer.getvalue())
    activity = []

    class Capture:
        async def request(self, call_id, request):
            activity.append("capture")

        async def response(self, call_id, response):
            activity.append("response")

    def forbidden(**kwargs):
        activity.append("sdk")
        raise AssertionError("invalid options reached SDK")

    monkeypatch.setattr(decision_model, "AsyncTypeSafeClient", forbidden)
    model = decision_model.DecisionModel(DecisionModelProfile(
        "https://offline.invalid/v1/systemone", "jev-1.14.0", "KEY", images=True,
    ), credential="test")
    ctx = SubAgentContext(
        SubAgentAuthorization(frozenset({"network"})), SubAgentBudget(), asyncio.Event(),
        model_capture=Capture(), model_data_scope=ModelDataScope(frozenset({"text", "image"})),
    )
    task = TaskDecisionModel("task", ctx, model)
    try:
        with pytest.raises(SubAgentStopped, match="invalid_decision_image"):
            await task.choose_image(state={}, image=asset, instructions="Choose", options=options)
        assert activity == []
        assert ctx.budget.call_count == 0 and not ctx.budget.unknown_calls
    finally:
        await task.aclose()
        await model.aclose()


def response(choice="a"):
    return {
        "model": "jev-1.13.0",
        "answers": {
            "next_action": {
                "type": "choice",
                "choice": choice,
                "confidence": 1.0,
                "probabilities": {"a": 1.0, "b": 0.0},
            }
        },
        "usage": {"input_tokens": 7, "output_tokens": 2},
    }


async def test_standalone_decision_model_has_no_task_or_custom_transport(monkeypatch):
    from tank_backend.llm.decision_model import DecisionModel
    from tank_backend.llm.decision_profile import DecisionModelProfile

    calls = []

    async def respond(request):
        calls.append(request)
        return httpx2.Response(200, json=response())

    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kw: httpx2.MockTransport(respond))
    model = DecisionModel(
        DecisionModelProfile(
            "https://offline.invalid/v1/systemone",
            "jev-1.13.0",
            "TEST_KEY",
        ),
        credential="secret",
    )
    try:
        result = await model.choose(state={}, instructions="Choose", options={"a": "A", "b": "B"})
        assert result.choice == "a"
        assert (result.input_tokens, result.output_tokens) == (7, 2)
        assert len(calls) == 1
        assert calls[0].headers["authorization"] == "Bearer secret"
    finally:
        await model.aclose()


@pytest.mark.parametrize("kind", ["text", "image", "box"])
async def test_successful_choice_trace_retains_decision_evidence(monkeypatch, kind):
    import io
    from contextlib import contextmanager

    from PIL import Image

    from tank_backend.llm import decision_model
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.llm.model_data import ModelImageAsset

    updates = []

    @contextmanager
    def observation(name, model):
        yield lambda **fields: updates.append(fields)

    data = response()
    if kind != "text":
        data["model"] = "jev-1.14.0"
    if kind == "box":
        data["answers"] = {
            "cardinality": {"type": "choice", "choice": "one", "confidence": 0.9,
                            "probabilities": {"none": 0.0, "one": 1.0, "several": 0.0}},
            "target": {"type": "box", "box": {"left": 0.1, "top": 0.2, "right": 0.3,
                                                "bottom": 0.4}, "confidence": 0.8},
        }
    monkeypatch.setattr(decision_model, "model_observation", observation)
    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kw: httpx2.MockTransport(
        lambda request: httpx2.Response(200, json=data)))
    model = decision_model.DecisionModel(DecisionModelProfile(
        "https://offline.invalid/v1/systemone", data["model"], "KEY", images=kind != "text",
    ), credential="test")
    try:
        expected: dict[str, object] = {
            "choice": "a", "confidence": 1.0, "probabilities": {"a": 1.0, "b": 0.0},
            "candidates": 2, "input_tokens": 7, "output_tokens": 2,
        }
        if kind == "text":
            await model.choose(state={}, instructions="Choose", options={"a": "A", "b": "B"})
        else:
            buffer = io.BytesIO()
            Image.new("RGB", (280, 280)).save(buffer, "PNG")
            asset = ModelImageAsset("tank-image-" + "a" * 32, "asset-0", "image/png",
                                    buffer.getvalue())
            if kind == "image":
                await model.choose_image(state={}, image=asset, instructions="Choose",
                                         options={"a": "A", "b": "B"})
            else:
                await model.locate_image(state={}, image=asset, target="A")
                expected = {
                    "cardinality": "one", "cardinality_confidence": 0.9,
                    "cardinality_probabilities": {"none": 0.0, "one": 1.0, "several": 0.0},
                    "box": (0.1, 0.2, 0.3, 0.4), "box_confidence": 0.8,
                    "input_tokens": 7, "output_tokens": 2,
                }
        assert updates == [expected]
    finally:
        await model.aclose()


@pytest.mark.parametrize("allow_text,max_bytes,reason", [
    (True, 1024, None), (True, 32, "model_request_too_large"),
    (False, 1024, "model_data_denied"),
])
async def test_task_decision_respects_host_data_scope_before_sdk_creation(
    monkeypatch, allow_text, max_bytes, reason,
):
    import asyncio

    from typesafe_sdk import AsyncTypeSafeClient

    from tank_backend.agents.subagent import (
        SubAgentAuthorization,
        SubAgentBudget,
        SubAgentContext,
        SubAgentStopped,
    )
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.llm.model_data import ModelDataScope

    created, requests = [], []
    original = AsyncTypeSafeClient.__init__

    def initialize(self, *args, **kwargs):
        created.append(True)
        original(self, *args, **kwargs)

    def respond(request):
        requests.append(request)
        return httpx2.Response(200, json=response())

    monkeypatch.setattr(AsyncTypeSafeClient, "__init__", initialize)
    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kw: httpx2.MockTransport(respond))
    ctx = SubAgentContext(
        SubAgentAuthorization(frozenset({"network"})), SubAgentBudget(), asyncio.Event(),
        model_data_scope=ModelDataScope(frozenset({"text"} if allow_text else set()), max_bytes),
    )
    ctx.runtime.configure_decision_model("data-task", DecisionModelProfile(
        "https://offline.invalid/v1/systemone", "jev-1.13.0", "TEST_KEY"), credential="fake")
    model = ctx.runtime.decision_model
    assert model is not None
    try:
        if reason:
            with pytest.raises(SubAgentStopped, match=reason):
                await model.choose(state={"name": "中"}, instructions="Choose",
                                   options={"a": "A", "b": "B"})
            assert created == requests == [] and ctx.budget.call_count == 0
        else:
            assert (await model.choose(state={"name": "中"}, instructions="Choose",
                                       options={"a": "A", "b": "B"})).choice == "a"
            assert len(created) == len(requests) == 1 and ctx.budget.total_tokens == 9
    finally:
        await ctx.runtime.aclose()


async def test_bad_choice_retains_known_usage(monkeypatch):
    from tank_backend.llm.decision_model import DecisionModel, DecisionModelError
    from tank_backend.llm.decision_profile import DecisionModelProfile

    monkeypatch.setattr(
        httpx2,
        "AsyncHTTPTransport",
        lambda **kw: httpx2.MockTransport(
            lambda request: httpx2.Response(200, json=response("unoffered"))
        ),
    )
    model = DecisionModel(
        DecisionModelProfile(
            "https://offline.invalid/v1/systemone",
            "jev-1.13.0",
            "TEST_KEY",
        ),
        credential="secret",
    )
    try:
        with pytest.raises(DecisionModelError) as error:
            await model.choose(state={}, instructions="Choose", options={"a": "A", "b": "B"})
        assert (error.value.input_tokens, error.value.output_tokens) == (7, 2)
    finally:
        await model.aclose()


@pytest.mark.parametrize("failure", ["disabled", "enter", "update", "exit"])
async def test_optional_observability_never_changes_decision(monkeypatch, failure):
    from tank_backend.llm.decision_model import DecisionModel
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.observability import model_observation as telemetry

    calls = []

    async def respond(request):
        calls.append(request)
        return httpx2.Response(200, json=response())

    class Span:
        def __enter__(self):
            if failure == "enter":
                raise RuntimeError("tracing unavailable")
            return self

        def update(self, **kwargs):
            if failure == "update":
                raise RuntimeError("tracing unavailable")

        def __exit__(self, *args):
            if failure == "exit":
                raise RuntimeError("tracing unavailable")

    class Client:
        def start_as_current_observation(self, **kwargs):
            return Span()

    monkeypatch.setattr(
        telemetry, "get_langfuse", lambda: None if failure == "disabled" else Client()
    )
    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kw: httpx2.MockTransport(respond))
    model = DecisionModel(
        DecisionModelProfile("https://offline.invalid/v1/systemone", "jev-1.13.0", "TEST_KEY"),
        credential="secret",
    )
    try:
        result = await model.choose(state={}, instructions="Choose", options={"a": "A", "b": "B"})
        assert result.choice == "a" and result.input_tokens == 7 and len(calls) == 1
    finally:
        await model.aclose()


async def test_failed_decision_trace_keeps_usage_and_error_level(monkeypatch):
    from tank_backend.llm.decision_model import DecisionModel, DecisionModelError
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.observability import model_observation as telemetry

    updates = []

    class Span:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def update(self, **kwargs):
            updates.append(kwargs)

    class Client:
        def start_as_current_observation(self, **kwargs):
            return Span()

    monkeypatch.setattr(telemetry, "get_langfuse", lambda: Client())
    monkeypatch.setattr(
        httpx2,
        "AsyncHTTPTransport",
        lambda **kw: httpx2.MockTransport(
            lambda request: httpx2.Response(200, json=response("unoffered"))
        ),
    )
    model = DecisionModel(
        DecisionModelProfile("https://offline.invalid/v1/systemone", "jev-1.13.0", "TEST_KEY"),
        credential="secret",
    )
    try:
        with pytest.raises(DecisionModelError):
            await model.choose(state={}, instructions="Choose", options={"a": "A", "b": "B"})
        assert any(u.get("level") == "ERROR" for u in updates)
        assert any(
            u.get("usage_details") == {"input_tokens": 7, "output_tokens": 2} for u in updates
        )
    finally:
        await model.aclose()


async def test_choice_is_bound_to_options_at_invocation(monkeypatch):
    import json

    from tank_backend.llm.decision_model import DecisionModel, DecisionModelError
    from tank_backend.llm.decision_profile import DecisionModelProfile

    options: dict[str, object] = {"a": "A", "b": "B"}

    async def respond(request):
        assert set(json.loads(request.content)["questions"]["next_action"]["criteria"]) == {
            "a",
            "b",
        }
        options["late"] = "Not offered in this invocation"
        data = response("late")
        data["answers"]["next_action"]["probabilities"] = {"a": 0.0, "b": 0.0, "late": 1.0}
        return httpx2.Response(200, json=data)

    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kw: httpx2.MockTransport(respond))
    model = DecisionModel(
        DecisionModelProfile("https://offline.invalid/v1/systemone", "jev-1.13.0", "TEST_KEY"),
        credential="secret",
    )
    try:
        with pytest.raises(DecisionModelError, match="invalid_decision"):
            await model.choose(state={}, instructions="Choose", options=options)
    finally:
        await model.aclose()


async def test_task_choice_capture_and_sdk_share_input_snapshot(monkeypatch):
    import asyncio
    import json

    from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext
    from tank_backend.llm.decision_model import DecisionModel
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.llm.task_decision_model import TaskDecisionModel

    ticket, option = {"text": "original"}, {"label": "original"}
    state: dict[str, object] = {"ticket": ticket}
    options: dict[str, object] = {"a": option, "b": "B"}
    captured = []

    class Capture:
        async def request(self, call_id, request):
            import copy

            captured.append(copy.deepcopy(request.parameters))
            request.parameters["state"] = {"recorder": "redacted"}
            ticket["text"] = "changed"
            option["label"] = "changed"
            options["late"] = "Not in the captured question"
            await asyncio.sleep(0)

        async def response(self, call_id, response):
            pass

    async def respond(request):
        assert json.loads(request.content) == captured[0]
        return httpx2.Response(200, json=response())

    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kw: httpx2.MockTransport(respond))
    model = DecisionModel(
        DecisionModelProfile("https://offline.invalid/v1/systemone", "jev-1.13.0", "TEST_KEY"),
        credential="secret",
    )
    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"network"})),
        SubAgentBudget(),
        asyncio.Event(),
        model_capture=Capture(),
    )
    task_model = TaskDecisionModel("task", context, model)
    try:
        result = await task_model.choose(state=state, instructions="Choose", options=options)
        assert result.choice == "a" and context.budget.total_tokens == 9
    finally:
        await task_model.aclose()
        await model.aclose()


async def test_invalid_sdk_configuration_allocates_no_http_client(monkeypatch):
    from typesafe_sdk import TypeSafeError

    from tank_backend.llm.decision_model import DecisionModel
    from tank_backend.llm.decision_profile import DecisionModelProfile

    clients = []
    original = httpx2.AsyncClient

    def client(**kwargs):
        created = original(**kwargs)
        clients.append(created)
        return created

    monkeypatch.setattr(httpx2, "AsyncClient", client)
    model = DecisionModel(
        DecisionModelProfile("https://offline.invalid/v1/systemone", "jev-1.13.0", "KEY"),
        credential="invalid key",
    )
    try:
        with pytest.raises(TypeSafeError):
            await model.choose(state={}, instructions="Choose", options={"a": "A"})
        assert clients == []
    finally:
        await model.aclose()
        for allocated in clients:
            await allocated.aclose()


async def test_official_sdk_owns_default_http_client(monkeypatch):
    from tank_backend.llm import decision_model as module
    from tank_backend.llm.decision_profile import DecisionModelProfile

    clients, configurations = [], []
    sdk_class, http_factory = module.AsyncTypeSafeClient, httpx2.AsyncClient

    def sdk(**kwargs):
        assert "http_client" not in kwargs and "transport" not in kwargs
        configurations.append(kwargs)
        return sdk_class(**kwargs)

    def http(**kwargs):
        assert "trust_env" not in kwargs and "follow_redirects" not in kwargs
        assert kwargs.get("transport") is None
        client = http_factory(**kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(module, "AsyncTypeSafeClient", sdk)
    monkeypatch.setattr(httpx2, "AsyncClient", http)
    monkeypatch.setattr(
        httpx2,
        "AsyncHTTPTransport",
        lambda **kw: httpx2.MockTransport(lambda request: httpx2.Response(200, json=response())),
    )
    model = module.DecisionModel(
        DecisionModelProfile("https://offline.invalid/v1/systemone", "jev-1.13.0", "KEY"),
        credential="secret",
    )
    try:
        assert clients == []
        result = await model.choose(state={}, instructions="Choose", options={"a": "A", "b": "B"})
        assert result.choice == "a"
        assert len(clients) == len(configurations) == 1
        assert configurations[0]["timeout"] == 30
        assert configurations[0]["retry"].max_retries == 0
        assert clients[0].trust_env and not clients[0].follow_redirects
        assert not clients[0].is_closed
    finally:
        await model.aclose()
    assert clients[0].is_closed


async def test_task_decision_error_survives_unknown_usage_stop(monkeypatch):
    import asyncio
    import json

    from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext
    from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
    from tank_backend.benchmarks.spend_http import ContextWindowContract
    from tank_backend.benchmarks.spend_ledger import (
        SpendLedger,
        SpendLimit,
        SpendLimitExceeded,
        TokenAllowance,
    )
    from tank_backend.llm.decision_model import DecisionModel
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.llm.task_decision_model import TaskDecisionModel

    events, requests = [], []
    class Observer:
        def on_event(self, kind, metadata):
            events.append((kind, metadata))
    async def respond(request):
        requests.append(request)
        return httpx2.Response(401, json={"error": "private-body-secret"},
                               headers={"x-private": "private-header-secret"})
    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kw: httpx2.MockTransport(respond))
    url = "https://offline.invalid/v1/systemone"
    ledger = SpendLedger(SpendLimit(10000, 1000000), request_limit=1)
    ledger.start_trial("trial", SpendLimit(10000, 1000000))
    policy = BenchmarkModelPolicy(ledger, (ContextWindowContract(
        url, "jev-1.13.0", TokenAllowance(100, 100, 42, 0), "test", output_cap_required=False),))
    ctx = SubAgentContext(SubAgentAuthorization(frozenset({"network"})), SubAgentBudget(),
                          asyncio.Event(), observer=Observer(), model_policy=policy)
    model = DecisionModel(
        DecisionModelProfile(url, "jev-1.13.0", "KEY"), credential="private-key-secret",
    )
    task = TaskDecisionModel("task", ctx, model)
    try:
        with pytest.raises(SpendLimitExceeded, match="unknown_usage"):
            await task.choose(state={}, instructions="Choose", options={"a": "A"})
        errors = [data for kind, data in events if kind == "decision_error"]
        assert len(errors) == 1
        assert errors[0]["error_type"] == "TypeSafeAuthenticationError"
        assert errors[0]["http_status"] == 401
        assert errors[0]["task_id"] == "task" and errors[0]["call_id"]
        assert len(requests) == 1
        assert "private-" not in json.dumps(events)
        assert ledger.snapshot()["stop_reason"] == "unknown_usage"
    finally:
        await task.aclose()
        await model.aclose()
        ledger.close()


async def test_connection_failure_diagnostics_exclude_private_message(monkeypatch):
    from tank_backend.llm.decision_model import DecisionModel, DecisionModelError
    from tank_backend.llm.decision_profile import DecisionModelProfile

    requests = []
    async def respond(request):
        requests.append(request)
        raise httpx2.ConnectError("private-proxy-credentials", request=request)
    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kw: httpx2.MockTransport(respond))
    model = DecisionModel(
        DecisionModelProfile("https://offline.invalid/v1/systemone", "jev-1.13.0", "KEY"),
        credential="secret",
    )
    try:
        with pytest.raises(DecisionModelError) as error:
            await model.choose(state={}, instructions="Choose", options={"a": "A"})
        assert error.value.diagnostics == {
            "error_type": "TypeSafeAPIConnectionError", "http_status": None,
            "cause_type": "ConnectError",
        }
        assert "private-" not in str(error.value.diagnostics)
        assert len(requests) == 1
    finally:
        await model.aclose()
