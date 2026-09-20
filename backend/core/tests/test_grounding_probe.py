import pytest


def test_holdout_export_is_reproducible_and_separates_truth(tmp_path, monkeypatch):
    import hashlib
    import json
    import runpy
    from collections import Counter
    from pathlib import Path

    from PIL import Image

    script = Path(__file__).resolve().parents[2] / "scripts/prepare_grounding_holdout.py"
    main = runpy.run_path(str(script))["main"]
    outputs = [tmp_path / "first", tmp_path / "second"]
    for output in outputs:
        monkeypatch.setattr("sys.argv", [str(script), "--output", str(output)])
        main()
    first = outputs[0]
    for path in first.rglob("*"):
        if path.is_file():
            assert path.read_bytes() == (outputs[1] / path.relative_to(first)).read_bytes()
    inputs = json.loads((first / "inputs.json").read_text())
    truth = json.loads((first / "truth/labels.json").read_text())
    assert len(inputs) == len(truth) == 64
    assert len({row["image_sha256"] for row in inputs}) == 64
    assert Counter(row["expected"] for row in truth) == {
        "found": 48, "not_found": 8, "ambiguous": 8,
    }
    for request, answer in zip(inputs, truth, strict=True):
        assert set(request) == {"id", "image", "image_sha256", "size", "target"}
        assert hashlib.sha256((first / request["image"]).read_bytes()).hexdigest() == (
            request["image_sha256"])
        mask = Image.open(first / answer["mask"])
        assert list(mask.size) == request["size"]
        if answer["expected"] == "found":
            assert mask.getpixel(tuple(answer["center"])) == 255
            assert mask.getbbox() is not None
        else:
            assert answer["center"] is None and mask.getbbox() is None
    monkeypatch.setattr("sys.argv", [str(script), "--output", str(first)])
    with pytest.raises(FileExistsError):
        main()


@pytest.mark.parametrize("thinking,budget,variant", [
    ("on", 4000, "strict-bbox"), ("off", 4000, "strict-bbox"),
    ("on", 16000, "low-detail"), ("off", 16000, "low-detail"),
    (None, 4000, "no-thinking"), (None, 4000, "point"),
])
async def test_matrix_cli_sends_independent_thinking_and_budget(
    tmp_path, monkeypatch, thinking, budget, variant,
):
    import base64
    import json
    import runpy
    from pathlib import Path
    from types import SimpleNamespace

    import httpx
    from openai import AsyncOpenAI

    scripts = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    monkeypatch.syspath_prepend(str(scripts))
    probe = runpy.run_path(str(scripts / "probe_grounding_matrix.py"))
    main = probe["main"]
    expected_thinking = thinking == "on" if thinking else variant != "no-thinking"
    seen = []

    def respond(request):
        body = json.loads(request.content)
        seen.append(body)
        assert body["max_tokens"] == budget
        assert body["thinking"] == {"type": "enabled" if expected_thinking else "disabled"}
        assert body["model"] == "deepseek-flash"
        assert request.url.path == ("/beta/chat/completions" if variant.startswith("strict-")
                                    else "/chat/completions")
        image = body["messages"][-1]["content"][1]["image_url"]
        assert base64.b64decode(image["url"].split(",", 1)[1]) == (
            probe["make_case"](102, variant)["png"])
        assert image["detail"] == ("low" if variant == "low-detail" else "auto")
        fn = body["tools"][0]["function"]
        assert fn.get("strict", False) == variant.startswith("strict-")
        assert set(fn["parameters"]["properties"]) == (
            {"found", "left", "top", "right", "bottom"} if variant == "strict-bbox"
            else {"found", "x", "y"}
        )
        # Replay budget exhaustion: retain usage/finish reason instead of inventing a click.
        return httpx.Response(200, json={"id": "test", "object": "chat.completion",
            "created": 1, "model": "deepseek-flash", "choices": [{"index": 0,
                "finish_reason": "length", "message": {"role": "assistant", "content": None}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": budget, "total_tokens": 100+budget,
                      "completion_tokens_details": {"reasoning_tokens": budget}}})

    def create(**kwargs):
        return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(respond)))

    monkeypatch.setitem(main.__globals__, "AsyncOpenAI", create)
    monkeypatch.setitem(main.__globals__, "load_dotenv", lambda path: None)
    monkeypatch.setitem(main.__globals__, "AppConfig", SimpleNamespace(load=lambda path:
        SimpleNamespace(get_llm_profile=lambda name:
            SimpleNamespace(base_url="unused", api_key="test"))))
    output = tmp_path / "probe"
    argv = ["probe", "--models", "deepseek", "--variants", variant, "--cases", "1",
            "--seed", "102", "--output", str(output)]
    if thinking:
        argv += ["--thinking", thinking, "--max-tokens", str(budget)]
    monkeypatch.setattr("sys.argv", argv)
    await main()
    row = json.loads((output / "results.json").read_text())["results"][0]
    assert len(seen) == 1 and row["http_verified"]
    assert row["thinking"] is expected_thinking and row["max_tokens"] == budget
    assert row["finish_reason"] == "length" and not row["schema_valid"] and not row["hit"]
    assert row["usage"]["completion_tokens_details"]["reasoning_tokens"] == budget


@pytest.mark.parametrize("budget", [0, -1])
async def test_matrix_rejects_invalid_budget_before_side_effects(tmp_path, monkeypatch, budget):
    import runpy
    from pathlib import Path

    scripts = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")
    monkeypatch.syspath_prepend(str(scripts))
    main = runpy.run_path(str(scripts / "probe_grounding_matrix.py"))["main"]
    output = tmp_path / "probe"
    monkeypatch.setattr("sys.argv", ["probe", "--output", str(output), "--max-tokens", str(budget)])
    with pytest.raises(SystemExit) as exc:
        await main()
    assert exc.value.code == 2 and not output.exists()


def test_native_qwen_payload_preserves_images_schema_and_parameters():
    from tank_backend.benchmarks.grounding_probe import location_request, qwen_native_request

    request = location_request("qwen", "test", b"png", (800, 600), "7", "point")
    native = qwen_native_request(request)
    assert native["model"] == request["model"]
    assert native["parameters"]["tools"] == request["tools"]
    assert native["parameters"]["enable_thinking"] is True
    assert native["parameters"]["max_tokens"] == 4000
    original = request["messages"][-1]["content"]
    assert native["input"]["messages"][-1]["content"] == [
        {"text": original[0]["text"]}, {"image": original[1]["image_url"]["url"]},
    ]
    assert request["messages"][-1]["content"][1]["type"] == "image_url"


def test_nullable_anyof_keeps_same_local_coordinate_contract():
    from tank_backend.benchmarks.grounding_probe import location_request

    request = location_request("qwen", "test", b"png", (800, 600), "7", "point",
                               nullable_style="anyof")
    x = request["tools"][0]["function"]["parameters"]["properties"]["x"]
    assert x == {"anyOf": [{"type": "integer", "minimum": 0, "maximum": 1000},
                           {"type": "null"}]}


def test_integer_schema_requires_explicit_zero_abstention_without_coercion():
    from tank_backend.benchmarks.grounding_probe import decode_location, location_request

    request = location_request("qwen", "test", b"png", (800, 600), "7", "point",
                               nullable_style="integer")
    x = request["tools"][0]["function"]["parameters"]["properties"]["x"]
    assert x == {"type": "integer", "minimum": 0, "maximum": 1000}
    assert decode_location('{"found":false,"x":0,"y":0}', "point", (800, 600),
                           abstention_zero=True) is None
    for raw in ('{"found":false,"x":2,"y":0}', '{"found":false,"x":false,"y":0}',
                '{"found":false,"x":null,"y":null}', '{"found":true,"x":"2","y":0}'):
        with pytest.raises(ValueError):
            decode_location(raw, "point", (800, 600), abstention_zero=True)


@pytest.mark.parametrize("variant", [
    "point", "bbox", "pixels", "crop", "resized", "history", "full-tools",
])
async def test_matrix_binds_actual_request_and_scores_known_location(
    tmp_path, monkeypatch, variant,
):
    import json
    import runpy
    from pathlib import Path

    import httpx
    from openai import AsyncOpenAI

    scripts = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")
    monkeypatch.syspath_prepend(str(scripts))
    probe = runpy.run_path(str(scripts / "probe_grounding_matrix.py"))
    case = probe["make_case"](102, variant)
    x, y = case["center"]
    ox, oy, cw, ch = case["crop"] or (0, 0, *case["size"])
    x, y = (x-ox) / cw, (y-oy) / ch
    args = {"found": True, "x": round(x*1000), "y": round(y*1000)}
    if variant == "pixels":
        args = {"found": True, "x": round(x*case["size"][0]), "y": round(y*case["size"][1])}
    elif variant == "bbox":
        args = {"found": True, "left": round(x*1000)-10, "right": round(x*1000)+10,
                "top": round(y*1000)-10, "bottom": round(y*1000)+10}

    def respond(request):
        body = json.loads(request.content)
        assert body["model"] == "candidate"
        if variant == "full-tools":
            assert {tool["function"]["name"] for tool in body["tools"]} >= {
                "click", "screenshot", "computer_batch", "launch_app", "type_text",
            }
            assert body["messages"][0]["content"] == "agent"
        return httpx.Response(200, json={"id": "test", "object": "chat.completion",
            "created": 1, "model": "candidate", "choices": [{"index": 0,
                "finish_reason": "tool_calls", "message": {"role": "assistant",
                    "content": None, "tool_calls": [{"id": "one", "type": "function",
                        "function": {"name": "click", "arguments": json.dumps(args)}}]}}]})

    async with AsyncOpenAI(api_key="test", base_url="https://probe.invalid/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))) as client:
        row = await probe["run_trial"](client, "qwen", "candidate", 102, variant,
                                       tmp_path, "test", "agent")
    assert row["http_verified"] and row["schema_valid"] and row["hit"]
    assert row["distance"] < 2
    assert len(row["images"]) == (2 if variant == "history" else 1)
    assert "data:image" not in (tmp_path / "test.request.json").read_text()
    assert (tmp_path / "test.response.json.gz").exists()


def test_button_hit_uses_rounded_shape_and_pixel_protocol_keeps_axis_scales():
    from tank_backend.benchmarks.grounding_probe import decode_location, score_location

    assert decode_location('{"found":true,"x":100,"y":50}', "pixels", (400, 200),
                           (10, 20, 800, 600)) == (210, 170)
    assert score_location((100, 100), (80, 80, 120, 120), 20)["hit"] is True
    assert score_location((81, 81), (80, 80, 120, 120), 20)["hit"] is False
    assert score_location((120, 100), (80, 80, 120, 120), 20)["hit"] is True
    assert score_location((121, 100), (80, 80, 120, 120), 20)["hit"] is False
    assert score_location((80, 95), (80, 80, 120, 120), 20)["dx"] == -20


def test_strict_protocol_maps_bbox_through_crop_and_rejects_guessed_coordinates():
    from tank_backend.benchmarks.grounding_probe import decode_location

    # A 400x200 image represents an 800x600 desktop crop starting at (50, 70).
    point = decode_location(
        '{"found":true,"left":200,"top":100,"right":400,"bottom":500}',
        "bbox", (400, 200), (50, 70, 800, 600),
    )
    assert point == (290, 250)
    assert decode_location(
        '{"found":false,"x":null,"y":null}', "point", (400, 200),
    ) is None
    for raw in (
        '{"found":true,"x":"200","y":300}',
        '{"found":true,"x":true,"y":300}',
        '{"found":true,"x":1001,"y":300}',
        '{"found":true,"x":200,"y":300,"bbox":[1,2,3,4]}',
        '{"found":false,"x":200,"y":300}',
        '{"found":true,"x":200,"x":300,"y":300}',
    ):
        with pytest.raises(ValueError):
            decode_location(raw, "point", (400, 200))
    with pytest.raises(ValueError):
        decode_location(
            '{"found":true,"left":400,"top":100,"right":200,"bottom":500}',
            "bbox", (400, 200),
        )


@pytest.mark.parametrize("provider", ["qwen", "deepseek", "openai", "openrouter"])
async def test_protocol_request_over_sdk_keeps_provider_params_and_frame_order(provider):
    import base64
    import hashlib
    import json

    import httpx
    from openai import AsyncOpenAI

    from tank_backend.benchmarks.grounding_probe import location_request

    seen = []

    def respond(request):
        body = json.loads(request.content)
        seen.append(body)
        assert ("enable_thinking" in body) == (provider == "qwen")
        assert ("thinking" in body) == (provider == "deepseek")
        assert ("max_completion_tokens" in body) == (provider == "openai")
        assert ("temperature" in body) == (provider in {"qwen", "deepseek"})
        assert ("max_tokens" in body) == (provider != "openai")
        if provider == "openrouter":
            assert body["reasoning"] == {"effort": "low"}
            assert body["provider"]["allow_fallbacks"] is False
        fn = body["tools"][0]["function"]
        assert fn["strict"] is True
        assert fn["parameters"]["additionalProperties"] is False
        assert set(fn["parameters"]["required"]) == {"found", "x", "y"}
        images = [part["image_url"]["url"] for message in body["messages"]
                  if isinstance(message["content"], list) for part in message["content"]
                  if part["type"] == "image_url"]
        assert [hashlib.sha256(base64.b64decode(url.split(",")[1])).hexdigest()
                for url in images] == [hashlib.sha256(png).hexdigest()
                                      for png in [b"old-png", b"latest-png"]]
        assert body["messages"][-1]["content"][0]["text"].startswith("CURRENT")
        return httpx.Response(200, json={"id": "test", "object": "chat.completion",
            "created": 1, "model": "candidate", "choices": [{"index": 0,
                "finish_reason": "tool_calls", "message": {"role": "assistant",
                    "content": None, "tool_calls": [{"id": "one", "type": "function",
                        "function": {"name": "click", "arguments":
                            '{"found":true,"x":250,"y":750}'}}]}}]})

    kwargs = location_request(provider, "candidate", b"latest-png", (400, 200), "7",
                              "point", strict=True, previous=b"old-png")
    async with AsyncOpenAI(api_key="test", base_url="https://probe.invalid/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))) as client:
        result = await client.chat.completions.create(**kwargs)
    assert result.model == "candidate"
    assert len(seen) == 1


async def test_probe_model_override_preserves_original_profile(tmp_path, monkeypatch):
    import runpy
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from tank_backend.llm.profile import LLMProfile

    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")
    script = Path(__file__).resolve().parents[2] / "scripts/probe_grounding_contract.py"
    probe = runpy.run_path(str(script))
    main = probe["main"]
    original = LLMProfile(name="computer_use", model="configured-model", api_key="test",
                          base_url="https://probe.invalid/v1", temperature=0.1)
    selected = []

    def create(profile):
        selected.append(profile)
        return SimpleNamespace(client=SimpleNamespace(close=AsyncMock()), extra_body={})

    monkeypatch.setitem(main.__globals__, "load_dotenv", lambda path: None)
    monkeypatch.setitem(main.__globals__, "AppConfig", SimpleNamespace(load=lambda path:
        SimpleNamespace(get_llm_profile=lambda name: original)))
    monkeypatch.setitem(main.__globals__, "create_llm_from_profile", create)
    monkeypatch.setitem(main.__globals__, "scene", lambda size, position: (b"generated", {}))
    monkeypatch.setattr("sys.argv", [str(script), "--model", "comparison-model", "--output",
                                   str(tmp_path / "probe"), "--repeats", "0"])
    await main()
    assert selected[0].model == "comparison-model"
    assert original.model == "configured-model"
    assert selected[0].base_url == original.base_url
    assert selected[0].api_key == original.api_key
    assert selected[0].temperature == original.temperature


@pytest.mark.parametrize("style", ["agent", "minimal", "formula"])
def test_probe_prompt_uses_image_dimensions_without_leaking_target(style, monkeypatch):
    import runpy
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "scripts/probe_grounding_contract.py"
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")
    probe = runpy.run_path(str(script))
    messages = probe["probe_messages"]("agent instructions", "7", (1080, 1920), [], style, False)
    assert messages[0]["content"] == (
        "agent instructions" if style == "agent" else
        "Locate the requested UI element in the image."
    )
    question = messages[1]["content"]
    assert "7" in question
    assert "normalized" in question
    if style == "formula":
        assert "1080" in question and "1920" in question
        assert "x = 1000 * pixel_x / 1080" in question
        assert "y = 1000 * pixel_y / 1920" in question


@pytest.mark.parametrize("plain_json", [False, True])
@pytest.mark.parametrize("extra", [
    {}, {"enable_thinking": False, "vl_high_resolution_images": True},
])
async def test_probe_over_real_sdk_preserves_pixels_parameters_and_response(
    monkeypatch, plain_json, extra,
):
    import base64
    import io
    import json
    import runpy
    from pathlib import Path

    import httpx
    from openai import AsyncOpenAI
    from PIL import Image

    from tank_backend.core.content import ImageBlock
    from tank_backend.llm import llm as llm_module

    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")
    script = Path(__file__).resolve().parents[2] / "scripts/probe_grounding_contract.py"
    probe = runpy.run_path(str(script))
    buffer = io.BytesIO()
    Image.new("RGB", (1080, 1920), "red").save(buffer, format="PNG")
    png = buffer.getvalue()
    messages = probe["probe_messages"]("agent", "7", (1080, 1920), [ImageBlock(
        source="data:image/png;base64," + base64.b64encode(png).decode(), mime_type="image/png",
    )], "formula", plain_json)
    seen = []

    def respond(request):
        body = json.loads(request.content)
        seen.append(body)
        assert ("tools" in body) is not plain_json
        for key in ("enable_thinking", "vl_high_resolution_images"):
            assert (key in body) == (key in extra)
            assert body.get(key) == extra.get(key)
        assert "extra_body" not in body  # SDK expands provider parameters at top level.
        url = next(part["image_url"]["url"] for message in body["messages"]
                   if isinstance(message["content"], list) for part in message["content"]
                   if part["type"] == "image_url")
        assert base64.b64decode(url.split(",", 1)[1]) == png
        assert "x = 1000 * pixel_x / 1080" in body["messages"][1]["content"]
        raw = '{"x":750,"y":250}'
        delta = {"content": raw} if plain_json else {"tool_calls": [{
            "index": 0, "id": "probe", "type": "function",
            "function": {"name": "click", "arguments": raw},
        }]}
        chunk = {"id": "probe", "object": "chat.completion.chunk", "created": 1,
                 "model": "test", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              content=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n")

    client = AsyncOpenAI(api_key="test", base_url="https://probe.invalid/v1",
                         http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(llm_module, "AsyncOpenAI", lambda **kwargs: client)
    monkeypatch.setattr(llm_module, "initialize_langfuse", lambda: None)
    llm = llm_module.LLM(api_key="test", model="test", base_url="https://probe.invalid/v1",
                         extra_body=extra)
    try:
        tools = [{"type": "function", "function": {
            "name": "click", "parameters": {"type": "object"},
        }}]
        events = [event async for event in llm.chat_stream(
            messages, tools=None if plain_json else tools,
        )]
    finally:
        await client.close()
    assert len(seen) == 1  # Probe has no executor: returned actions never run.
    if plain_json:
        raw = "".join(text for kind, text, meta in events if kind.name == "TEXT")
    else:
        message = next(meta["message"] for kind, text, meta in events if kind.name == "MESSAGE")
        raw = message["tool_calls"][0]["function"]["arguments"]
    assert json.loads(raw) == {"x": 750, "y": 250}


@pytest.mark.parametrize("point, hypothesis", [
    ((750, 250), "normalized"),
    ((1440, 270), "pixels"),
    ((960, 180), "long_edge_1280"),
])
def test_scores_known_coordinate_spaces(point, hypothesis):
    from tank_backend.benchmarks.grounding_probe import score_point

    scores = score_point(point, (1920, 1080), (1440, 270))
    assert scores[hypothesis] == 0
    assert sum(error == 0 for error in scores.values()) == 1


@pytest.mark.parametrize("arguments, expected", [
    ({"x": "1440", "y": 270}, (1440, 270)),
    ({"bbox": [100, 200, 300, 400]}, (200, 300)),
    ({"bbox": "[100,200,300,400]]"}, None),
    ({"x": float("nan"), "y": 1}, None),
    ({"x": True, "y": 1}, None),
])
def test_probe_preserves_pixel_coordinates_but_rejects_malformed(arguments, expected):
    from tank_backend.benchmarks.grounding_probe import response_point

    assert response_point(arguments) == expected


@pytest.mark.parametrize("text, expected", [
    ('{"x":154,"y":286}', (154, 286)),
    ('```json\n{"x":154,"y":286}\n```', (154, 286)),
    ('```json\n[{"x":778,"y":690], "label":"7"}]\n```', None),
    ('Here is the answer: {"x":154,"y":286}', None),
])
def test_text_probe_scores_whole_json_but_never_repairs_corrupt_arguments(text, expected):
    from tank_backend.benchmarks.grounding_probe import text_response_point

    assert text_response_point(text) == expected


@pytest.mark.parametrize("box, expected", [
    ([726, 608, 771, 658], (748.5, 633)),
    ([726, 608], None),
    ("[726,608,771,658]", None),
])
def test_native_bbox_is_scored_only_with_explicit_format(box, expected):
    import json

    from tank_backend.benchmarks.grounding_probe import text_response_point

    answer = json.dumps([{"bbox_2d": box, "label": "7"}])
    assert text_response_point(answer) is None
    assert text_response_point(answer, native_bbox=True) == expected


async def test_real_provider_sse_preserves_bad_arguments_and_refuses_execution(monkeypatch):
    """2026-09-19 synthetic-only capture: upstream emitted Python-like, invalid JSON."""
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import httpx
    from openai import AsyncOpenAI

    from tank_backend.llm import llm as llm_module
    from tank_backend.tools.manager import ToolManager

    sse = (Path(__file__).parent / "fixtures/grounding-malformed.sse").read_bytes()
    client = AsyncOpenAI(api_key="test", base_url="https://probe.invalid/v1",
                         http_client=httpx.AsyncClient(transport=httpx.MockTransport(
                             lambda request: httpx.Response(200, content=sse,
                                 headers={"content-type": "text/event-stream"}),
                         )))
    monkeypatch.setattr(llm_module, "AsyncOpenAI", lambda **kwargs: client)
    monkeypatch.setattr(llm_module, "initialize_langfuse", lambda: None)
    llm = llm_module.LLM(api_key="test", model="test", base_url="https://probe.invalid/v1")
    try:
        events = [event async for event in llm.chat_stream([
            {"role": "user", "content": "synthetic replay"},
        ])]
    finally:
        await client.close()
    message = next(meta["message"] for kind, text, meta in events if kind.name == "MESSAGE")
    fn = message["tool_calls"][0]["function"]
    assert fn == {"name": "click", "arguments": '{"x": 778, y=693]}'}
    manager = ToolManager.__new__(ToolManager)
    manager.execute_tool = AsyncMock()
    result = await manager.execute_openai_tool_call(SimpleNamespace(function=SimpleNamespace(**fn)))
    assert not isinstance(result, str) and result.error
    manager.execute_tool.assert_not_called()


@pytest.mark.parametrize("provider", ["qwen", "deepseek", "openrouter"])
async def test_grounding_adapter_uses_profile_and_bound_image_over_real_sdk(monkeypatch, provider):
    import base64
    import io
    import json

    import httpx
    from openai import AsyncOpenAI
    from PIL import Image

    from tank_backend.benchmarks.grounding_probe import location_request
    from tank_backend.llm.profile import LLMProfile, create_llm_from_profile
    from tank_backend.tools.computer_grounding import GroundingAdapter
    from tank_backend.tools.computer_observation import Observation

    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")
    png = io.BytesIO()
    Image.new("RGB", (800, 600), "white").save(png, format="PNG")
    observation, image = Observation.capture(
        png.getvalue(), session_id="test", display_id=1, region=(250, 250, 750, 750),
    )
    adapter = GroundingAdapter(protocol="point", nullable_style="integer")
    profile = LLMProfile(
        name="grounder", api_key="test", model="candidate", base_url="https://probe.invalid/v1",
        temperature=None if provider == "openrouter" else 0.1, max_tokens=8000,
        extra_body={
            "qwen": {"enable_thinking": False},
            "deepseek": {"thinking": {"type": "disabled"}},
            "openrouter": {"reasoning": {"effort": "none"}, "provider": {
                "only": ["openai"], "allow_fallbacks": False, "require_parameters": True}},
        }[provider],
    )
    seen = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        expected = location_request(
            provider, "candidate", image, observation.image_size, "AC", "point",
            nullable_style="integer", thinking=False, max_tokens=8000,
        )
        extra = expected.pop("extra_body")
        assert body == expected | extra
        assert base64.b64decode(body["messages"][-1]["content"][1]["image_url"]["url"]
                                .split(",", 1)[1]) == image
        return httpx.Response(200, json={"id": "test", "object": "chat.completion",
            "created": 1, "model": "candidate", "choices": [{"index": 0,
                "finish_reason": "tool_calls", "message": {"role": "assistant",
                    "content": None, "tool_calls": [{"id": "one", "type": "function",
                        "function": {"name": "click", "arguments":
                            '{"found":true,"x":250,"y":750}'}}]}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}})

    llm = create_llm_from_profile(profile)
    await llm.client.close()
    async with AsyncOpenAI(api_key="test", base_url=profile.base_url,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))) as client:
        llm.client = client
        response = await adapter.request(llm, observation, image, "AC")
    location = adapter.parse_response(response, observation.image_size)
    assert location.status == "found"
    assert location.point == (observation.image_size[0] * .25, observation.image_size[1] * .75)
    assert location.point is not None
    assert observation.map_point(*location.point) == (300, 375)
    assert response.usage is not None and response.usage.total_tokens == 120
    assert len(seen) == 1


@pytest.mark.parametrize("mismatch", ["bytes", "size", "not-png"])
async def test_grounding_rejects_unbound_image_before_http(monkeypatch, mismatch):
    import hashlib
    import io
    from dataclasses import replace

    import httpx
    from openai import AsyncOpenAI
    from PIL import Image

    from tank_backend.llm.profile import LLMProfile, create_llm_from_profile
    from tank_backend.tools.computer_grounding import GroundingAdapter
    from tank_backend.tools.computer_observation import Observation

    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")
    buffer = io.BytesIO()
    Image.new("RGB", (31, 17)).save(buffer, format="PNG")
    observation, png = Observation.capture(buffer.getvalue(), session_id="a", display_id=1)
    if mismatch == "bytes":
        png += b"different"
    elif mismatch == "size":
        observation = replace(observation, image_size=(30, 17))
    else:
        png = b"not a PNG"
        observation = replace(observation, image_sha256=hashlib.sha256(png).hexdigest())

    def respond(request: httpx.Request) -> httpx.Response:
        pytest.fail("An unbound image must not cause an HTTP request")

    llm = create_llm_from_profile(LLMProfile(
        name="test", api_key="test", model="test", base_url="https://probe.invalid/v1",
    ))
    await llm.client.close()
    async with AsyncOpenAI(api_key="test", base_url=llm.base_url,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))) as client:
        llm.client = client
        with pytest.raises(ValueError, match="image|PNG"):
            await GroundingAdapter().request(llm, observation, png, "AC")


@pytest.mark.parametrize("status", ["found", "not_found", "ambiguous"])
def test_grounding_explicit_outcome_keeps_absence_and_ambiguity_distinct(status):
    import json

    from tank_backend.tools.computer_grounding import GroundingAdapter

    adapter = GroundingAdapter(protocol="bbox", status_field=True, strict=True)
    request = adapter.build_request(b"png", (800, 400), "Save button in toolbar")
    schema = request["tools"][0]["function"]["parameters"]
    assert schema["properties"]["status"]["enum"] == ["found", "not_found", "ambiguous"]
    assert "found" not in schema["properties"]
    assert "Save button in toolbar" in request["messages"][-1]["content"][0]["text"]
    box = [100, 200, 500, 600] if status == "found" else [0, 0, 0, 0]
    fields = dict(zip(["left", "top", "right", "bottom"], box, strict=True))
    raw = json.dumps(fields | {"status": status})
    result = adapter.parse(raw, (800, 400))
    assert result.status == status
    if status == "found":
        assert result.box == (80, 80, 400, 240)
        assert result.point == (240, 160)
    else:
        assert result.point is None and result.box is None
        with pytest.raises(ValueError):
            adapter.parse(json.dumps({"status": status, "left": 10, "top": 0,
                                      "right": 0, "bottom": 0}), (800, 400))
    with pytest.raises(ValueError):
        adapter.parse('{"found":true,"left":100,"top":200,"right":500,"bottom":600}',
                      (800, 400))


async def test_matrix_rejects_complete_looking_truncated_location(tmp_path, monkeypatch):
    import json
    import runpy
    from pathlib import Path

    import httpx
    from openai import AsyncOpenAI

    scripts = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")
    monkeypatch.syspath_prepend(str(scripts))
    run_trial = runpy.run_path(str(scripts / "probe_grounding_matrix.py"))["run_trial"]

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "test", "object": "chat.completion",
            "created": 1, "model": "candidate", "choices": [{"index": 0,
                "finish_reason": "length", "message": {"role": "assistant",
                    "content": None, "tool_calls": [{"id": "one", "type": "function",
                        "function": {"name": "click", "arguments":
                            '{"found":true,"x":250,"y":750}'}}]}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 8000, "total_tokens": 8100}})

    async with AsyncOpenAI(api_key="test", base_url="https://probe.invalid/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))) as client:
        row = await run_trial(client, "qwen", "candidate", 101, "point", tmp_path, "test", "")
    assert row["schema_valid"] is False and row["hit"] is False
    assert row["finish_reason"] == "length" and row["usage"]["total_tokens"] == 8100
    assert "Incomplete location response" in row["error"]
    assert json.loads(row["arguments"]) == {"found": True, "x": 250, "y": 750}
    assert (tmp_path / "test.response.json.gz").exists()


@pytest.mark.parametrize("options", [
    {"protocol": "guess"}, {"nullable_style": "coerce"}, {"detail": "invented"},
    {"strict": "true"}, {"status_field": "false"},
])
def test_grounding_invalid_configuration_is_rejected(options):
    from tank_backend.tools.computer_grounding import GroundingAdapter

    with pytest.raises(ValueError):
        GroundingAdapter(**options)


@pytest.mark.parametrize("size", [(0, 20), (20, -1), (True, 20), (20.5, 10)])
def test_grounding_rejects_invalid_dimensions_even_for_abstention(size):
    from tank_backend.tools.computer_grounding import GroundingAdapter

    adapter = GroundingAdapter()
    with pytest.raises(ValueError, match="image size"):
        adapter.build_request(b"png", size, "AC")
    with pytest.raises(ValueError, match="image size"):
        adapter.parse('{"found":false,"x":0,"y":0}', size)


@pytest.mark.parametrize("finish,refusal", [
    ("length", None), ("content_filter", None), ("tool_calls", "Refused"),
])
def test_grounding_incomplete_or_refused_response_never_yields_a_point(finish, refusal):
    from openai.types.chat import ChatCompletion

    from tank_backend.tools.computer_grounding import GroundingAdapter

    response = ChatCompletion.model_validate({"id": "test", "object": "chat.completion",
        "created": 1, "model": "test", "choices": [{"index": 0, "finish_reason": finish,
            "message": {"role": "assistant", "refusal": refusal, "tool_calls": [
                {"id": "one", "type": "function", "function": {"name": "click",
                    "arguments": '{"found":true,"x":250,"y":750}'}}]}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 8000, "total_tokens": 8100}})
    with pytest.raises(ValueError):
        GroundingAdapter().parse_response(response, (800, 600))
    assert response.usage is not None and response.usage.total_tokens == 8100


@pytest.mark.parametrize("failure", ["rate_limit", "cancel"])
async def test_grounding_single_call_does_not_retry_or_swallow_cancellation(monkeypatch, failure):
    import asyncio
    import io

    import httpx
    from openai import AsyncOpenAI, RateLimitError
    from PIL import Image

    from tank_backend.llm.profile import LLMProfile, create_llm_from_profile
    from tank_backend.tools.computer_grounding import GroundingAdapter
    from tank_backend.tools.computer_observation import Observation

    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")
    buffer = io.BytesIO()
    Image.new("RGB", (31, 17)).save(buffer, format="PNG")
    observation, png = Observation.capture(buffer.getvalue(), session_id="a", display_id=1)
    started = asyncio.Event()
    requests = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        started.set()
        if failure == "cancel":
            await asyncio.Event().wait()
        return httpx.Response(429, json={"error": {"message": "Rate limited"}})

    llm = create_llm_from_profile(LLMProfile(
        name="test", api_key="test", model="test", base_url="https://probe.invalid/v1",
    ))
    await llm.client.close()
    async with AsyncOpenAI(api_key="test", base_url=llm.base_url,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))) as client:
        llm.client = client
        task = asyncio.create_task(GroundingAdapter().request(llm, observation, png, "AC"))
        await asyncio.wait_for(started.wait(), 1)
        if failure == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(RateLimitError):
                await task
    assert len(requests) == 1


@pytest.mark.parametrize("batch", ["", "pixels"])
@pytest.mark.parametrize("alias", ["flash", "qwen38flash", "qwen38max", "deepseek", "gpt55"])
async def test_recorded_m3_responses_replay_through_production_adapter(monkeypatch, batch, alias):
    import base64
    import gzip
    import hashlib
    import json
    from pathlib import Path

    import httpx
    from openai import AsyncOpenAI

    from tank_backend.benchmarks.grounding_probe import score_location
    from tank_backend.llm.profile import LLMProfile, create_llm_from_profile
    from tank_backend.tools.computer_grounding import GroundingAdapter
    from tank_backend.tools.computer_observation import Observation

    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")
    report = (Path(__file__).resolve().parents[2] / "benchmarks/computer_use/reports"
              / "20260920-m3-preflight" / batch)
    row = next(r for r in json.loads((report / "results.json").read_text()) if r["id"] == alias)
    recorded = json.loads((report / f"{alias}.request.json").read_text())
    raw = gzip.decompress((report / f"{alias}.response.json.gz").read_bytes())
    png = (report / f"{row['images'][0]}.png").read_bytes()
    observation, image = Observation.capture(png, session_id="replay", display_id=1)
    adapter = GroundingAdapter(protocol=row["protocol"])
    extra = {k: v for k, v in recorded.items() if k not in {
        "model", "messages", "tools", "temperature", "max_tokens", "stream",
    }}
    llm = create_llm_from_profile(LLMProfile(
        name="replay", api_key="test", model=recorded["model"],
        base_url="https://probe.invalid/v1", temperature=recorded.get("temperature"),
        max_tokens=recorded["max_tokens"], extra_body=extra,
    ))
    await llm.client.close()

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        part = body["messages"][-1]["content"][1]["image_url"]
        digest = hashlib.sha256(base64.b64decode(part["url"].split(",", 1)[1])).hexdigest()
        assert digest == observation.image_sha256
        part["url"] = f"sha256:{digest}"
        assert body == recorded
        return httpx.Response(200, content=raw, headers={"content-type": "application/json"})

    async with AsyncOpenAI(api_key="test", base_url=llm.base_url,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))) as client:
        llm.client = client
        response = await adapter.request(llm, observation, image, row["target"])
    assert response.model == row["returned_model"]
    assert response.usage is not None
    assert response.usage.total_tokens == row["usage"]["total_tokens"]
    if not row["schema_valid"]:
        with pytest.raises(ValueError, match="Coordinates must be integers"):
            adapter.parse_response(response, observation.image_size)
    else:
        point = adapter.parse_response(response, observation.image_size).point
        assert point is not None
        score = score_location(point, row["bounds"], row["radius"])
        assert score["hit"] == row["hit"]
        assert score["distance"] == pytest.approx(row["distance"], rel=0, abs=1e-10)
