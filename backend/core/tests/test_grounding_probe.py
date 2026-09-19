import pytest


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
