"""Offline comparison exports exercise the production Runner and SDK."""

import hashlib
import json
import runpy
from pathlib import Path

import pytest


async def test_comparison_freeze_is_reproducible_and_uses_final_sdk_requests(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts/prepare_computer_comparison.py"
    prepare = runpy.run_path(str(script))["prepare"]
    config = tmp_path / "config.yaml"
    config.write_text("""llm:
  computer_use:
    api_key: NEVER_EXPORT_THIS_SECRET
    model: qwen3.7-flash-2026-07-15
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    temperature: 0.1
    max_tokens: 40000
    stream_options: false
    capabilities: [text, image]
    extra_headers:
      HTTP-Referer: http://localhost:3000
      X-Title: Tank Voice Assistant
toolsets:
  profiles:
    computer_use:
      tools: [screenshot, click, mouse_down, mouse_up, computer_batch]
""")
    first, second = tmp_path / "first", tmp_path / "second"
    await prepare(config, first)
    await prepare(config, second)
    for path in first.rglob("*"):
        if path.is_file():
            assert path.read_bytes() == (second / path.relative_to(first)).read_bytes()
            assert b"NEVER_EXPORT_THIS_SECRET" not in path.read_bytes()
    manifest = json.loads((first / "manifest.json").read_text())
    assert manifest["live_authorized"] is False
    for name, digest in manifest["artifacts"].items():
        assert hashlib.sha256((first / name).read_bytes()).hexdigest() == digest
    snapshot = json.loads((first / "requests.json").read_text())
    assert set(snapshot) == {"original", "A", "A-control", "B-host-only",
                             "B-protocol-only", "B-combined", "C", "D"}
    assert snapshot["original"][0]["body"]["max_tokens"] == 40000
    assert "stream_options" not in snapshot["original"][0]["body"]
    assert "enable_thinking" not in snapshot["original"][0]["body"]
    for name, requests in snapshot.items():
        assert len(requests) == (4 if name in {"C", "D"} else 2)
        first_request = requests[0]["body"]
        assert requests[0]["public_headers"] == {
            "HTTP-Referer": "http://localhost:3000", "X-Title": "Tank Voice Assistant"}
        tools = {t["function"]["name"] for t in first_request["tools"]}
        assert ("locate" in tools) == (name in {"C", "D"})
        assert ("mouse_down" in tools) == (name in {"original", "A"})
        assert "data:image/png;base64," in json.dumps(requests[1]["body"])
        if name != "original":
            assert first_request["stream_options"] == {"include_usage": True}
            assert first_request["max_tokens"] == 8000
            assert first_request["enable_thinking"] is False
        if name in {"C", "D"}:
            locator = requests[2]["body"]
            assert not locator.get("stream")
            assert len(locator["messages"]) == 2
            assert "PRIVATE PLANNER HISTORY" not in json.dumps(locator)
            fields = locator["tools"][0]["function"]["parameters"]["properties"]
            assert set(fields) == ({"found", "x", "y"} if name == "C" else
                                   {"found", "left", "top", "right", "bottom"})
            assert locator["model"] == ("qwen3.7-flash-2026-07-15" if name == "C"
                                        else "qwen3.8-max-2026-09-02")
    assert snapshot["A-control"][0]["body"]["tools"] == (
        snapshot["B-host-only"][0]["body"]["tools"])
    assert snapshot["B-protocol-only"][0]["body"]["tools"] == (
        snapshot["B-combined"][0]["body"]["tools"])
    with pytest.raises(FileExistsError):
        await prepare(config, first)


@pytest.mark.parametrize("field,value", [
    ("extra_headers", {"Authorization": "secret"}),
    ("extra_body", {"credential": "secret"}),
    ("base_url", "https://other.invalid/v1"),
    ("model", "different-model"),
])
async def test_comparison_rejects_unreviewed_profile_before_export(tmp_path, field, value):
    import yaml

    script = Path(__file__).resolve().parents[2] / "scripts/prepare_computer_comparison.py"
    prepare = runpy.run_path(str(script))["prepare"]
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump({"llm": {"computer_use": {field: value}}}))
    output = tmp_path / "export"
    with pytest.raises(ValueError):
        await prepare(config, output)
    assert not list(output.iterdir())
