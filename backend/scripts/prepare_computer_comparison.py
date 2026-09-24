"""Export M5 profiles and representative SDK requests, entirely offline.

Run from backend with --config core/config.yaml --output <new-directory>.
Only screenshot -> optional locate -> done is replayed. No input actions,
real screenshots, task validators, credentials or network transport are used.
These are request contract fixtures, not future live requests or effect scores.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import itertools
import json
import os
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, replace
from importlib.metadata import version
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import yaml
from openai import AsyncOpenAI
from PIL import Image

from tank_backend.agents.approval import PendingToolCallStore, ToolApprovalPolicy
from tank_backend.agents.base import AgentOutputType
from tank_backend.agents.definition import AgentDefinition, GroundingConfig, parse_agent_file
from tank_backend.agents.runner import AgentRunner
from tank_backend.benchmarks.comparison_contract import ComparisonContract
from tank_backend.config import AppConfig
from tank_backend.llm.profile import create_llm_from_profile, resolve_profile
from tank_backend.pipeline.bus import Bus
from tank_backend.tools import computer_use_macos as macos
from tank_backend.tools.groups import ComputerUseToolGroup
from tank_backend.tools.manager import ToolManager

BACKEND = Path(__file__).resolve().parents[1]
PUBLIC_FIELDS = ("model", "base_url", "temperature", "max_tokens", "stream_options",
                 "capabilities", "extra_body", "extra_headers")
PUBLIC_HEADERS = {"HTTP-Referer": "http://localhost:3000", "X-Title": "Tank Voice Assistant"}


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


@contextmanager
def quartz_module(quartz: Any) -> Iterator[None]:
    original = sys.modules.get("Quartz")
    sys.modules["Quartz"] = quartz
    try:
        yield
    finally:
        if original is None:
            sys.modules.pop("Quartz", None)
        else:
            sys.modules["Quartz"] = original


def variants(base: AgentDefinition) -> dict[str, AgentDefinition]:
    result = {"original": replace(base, model="original"),
              "A": replace(base, model="planner")}
    for name, protocol, restore in (
        ("A-control", "legacy", False), ("B-host-only", "legacy", True),
        # B-protocol-only keeps the superseded normalized contract as a measured control.
        ("B-protocol-only", "point", False), ("B-combined", "pixels", True),
        # The adapted coordinate contract is pixels; the arm that isolated the unit.
        ("B-pixels-only", "pixels", False),
    ):
        result[name] = replace(base, model="planner", grounding=GroundingConfig(
            mode="integrated", protocol=protocol, host_restore=restore, status_field=False))
    # C and D share one adapted contract so C to D isolates the locator model/profile.
    for name, protocol, profile in (("C", "pixels", None), ("D", "pixels", "locator")):
        result[name] = replace(base, model="planner", grounding=GroundingConfig(
            protocol=protocol, profile=profile, status_field=False))
    return result


def response(name: str | None, arguments: dict[str, Any]) -> httpx.Response:
    delta = {"tool_calls": [{"index": 0, "id": "offline-call", "type": "function",
                            "function": {"name": name, "arguments": json.dumps(arguments)}}]
             } if name else {"content": "Offline contract replay complete."}
    chunk = {"id": "offline", "object": "chat.completion.chunk", "created": 1,
             "model": "offline", "choices": [{"index": 0, "delta": delta,
             "finish_reason": "tool_calls" if name else "stop"}],
             "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}}
    return httpx.Response(200, headers={"content-type": "text/event-stream"},
                         content=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n")


async def capture(definition: AgentDefinition, profiles: dict[str, Any],
                  tool_names: list[str], png: bytes) -> list[dict[str, Any]]:
    """Use the real Runner/LLM/tools; replace only HTTP, host pixels and identities."""
    requests: list[dict[str, Any]] = []
    clients: list[AsyncOpenAI] = []
    turn = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal turn
        body = json.loads(request.content)
        requests.append({"url": str(request.url), "body": body,
                         "public_headers": {k: request.headers[k] for k in PUBLIC_HEADERS
                                            if k in request.headers}})
        if not body.get("stream"):
            # A scripted abstention exercises parsing without any input dispatch.
            protocol = definition.grounding.protocol if definition.grounding else "point"
            coords = {k: None for k in (("left", "top", "right", "bottom")
                                       if protocol == "bbox" else ("x", "y"))}
            return httpx.Response(200, json={
                "id": "offline-locator", "object": "chat.completion", "created": 1,
                "model": body["model"], "choices": [{"index": 0, "finish_reason": "tool_calls",
                    "message": {"role": "assistant", "tool_calls": [{"id": "location",
                        "type": "function", "function": {"name": "click",
                        "arguments": json.dumps({"found": False, **coords})}}]}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}})
        turn += 1
        if turn == 1:
            return response("screenshot", {"region": [100, 100, 800, 800]})
        if turn == 2 and definition.grounding and definition.grounding.mode == "split":
            text = next(p["text"] for m in body["messages"]
                        if isinstance(m.get("content"), list) for p in m["content"]
                        if p["type"] == "text" and "frame_id" in p["text"])
            frame = json.loads(text[text.index("{"):])["frame_id"]
            return response("locate", {"frame_id": frame, "target": "unique blue button"})
        return response(None, {})

    def client_factory(**kwargs: Any) -> AsyncOpenAI:
        kwargs["max_retries"] = 0
        client = AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(respond)))
        clients.append(client)
        return client

    quartz = MagicMock()
    quartz.CGMainDisplayID.return_value = 5
    quartz.CGDisplayBounds.return_value = ((0, 0), (100, 80))
    quartz.CGDisplayModeGetPixelWidth.return_value = 200
    quartz.CGDisplayModeGetPixelHeight.return_value = 160
    identities = itertools.count(1)
    with (
        quartz_module(quartz),
        patch.object(macos, "_load_quartz", return_value=quartz),
        patch.object(macos, "_capture_screenshot_macos", return_value=png),
        patch("tank_backend.llm.llm.AsyncOpenAI", side_effect=client_factory),
        patch("tank_backend.llm.llm.initialize_langfuse", return_value=None),
        patch("tank_backend.llm.llm.is_tracing_registered", return_value=False),
        patch("uuid.uuid4", side_effect=lambda: uuid.UUID(int=next(identities))),
        patch("time.time", return_value=1.0),
    ):
        manager = ToolManager.__new__(ToolManager)
        manager.tools = {t.get_info().name: t for t in
                         ComputerUseToolGroup()._create_macos_tools()}
        if set(tool_names) - manager.tools.keys():
            raise ValueError("Frozen toolset contains unavailable desktop tools")
        manager.tool_metadata = {n: t.get_metadata() for n, t in manager.tools.items()}
        manager._media_store = manager._bus = None
        manager.set_session_id("offline-parent")
        resolved = {name: resolve_profile(name, {**raw, "api_key": "offline-placeholder"})
                    for name, raw in profiles.items()}
        llm = create_llm_from_profile(resolved[definition.model or "planner"])
        runner = AgentRunner(llm, manager, Bus(), ToolApprovalPolicy(computer_mode="allow"),
                             PendingToolCallStore(), {definition.name: definition},
                             toolsets_config=SimpleNamespace(profiles={definition.toolset:
                                 SimpleNamespace(tools=tool_names)}),
                             app_config=SimpleNamespace(llm_profiles=resolved,
                                                        get_llm_profile=resolved.__getitem__))
        try:
            outputs = [o async for o in runner.run_agent(definition, [{"role": "user",
                "content": "PRIVATE PLANNER HISTORY: inspect the synthetic blue button."}],
                token_budget=300000)]
            if not any(o.type == AgentOutputType.DONE for o in outputs):
                raise RuntimeError("Offline Runner did not complete")
            expected = 4 if definition.grounding and definition.grounding.mode == "split" else 2
            if len(requests) != expected:
                raise RuntimeError("Offline request route differs from the frozen scenario")
        finally:
            for client in clients:
                await client.close()
    return requests


async def prepare(config: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    raw = yaml.safe_load(config.read_text())
    source = raw["llm"]["computer_use"]
    # Never serialize API keys, unreviewed headers, expansion, or unrelated config.
    original = {key: source[key] for key in PUBLIC_FIELDS if key in source}
    if source.get("extra_headers") and source["extra_headers"] != PUBLIC_HEADERS:
        raise ValueError("Review custom headers before freezing this profile")
    # Arbitrary extra_body values may contain provider credentials; fail closed.
    if source.get("extra_body"):
        raise ValueError("Review extra_body before freezing this profile")
    if (source.get("model") != "qwen3.7-flash-2026-07-15" or source.get("base_url") !=
            "https://dashscope.aliyuncs.com/compatible-mode/v1"):
        raise ValueError("Comparison candidate selection requires the recorded Beijing profile")
    planner = {**original, "stream_options": True, "max_tokens": 8000,
               "extra_body": {"enable_thinking": False}}
    profiles = {"original": original, "planner": planner,
                "locator": {**planner, "model": "qwen3.8-max-2026-09-02"}}
    tool_names = raw["toolsets"]["profiles"]["computer_use"]["tools"]
    if "screenshot" not in tool_names:
        raise ValueError("Comparison requires screenshot in the production toolset")
    base = parse_agent_file(BACKEND / "agents/computer_use.md")
    definitions = variants(base)
    buffer = io.BytesIO()
    Image.new("RGB", (100, 80), "blue").save(buffer, "PNG")
    png = buffer.getvalue()
    (output / "synthetic.png").write_bytes(png)
    write_json(output / "profiles.json", profiles)
    write_json(output / "definitions.json", {
        name: {**asdict(definition), "disallowed_tools": sorted(definition.disallowed_tools)}
        for name, definition in definitions.items()})
    write_json(output / "toolset.json", tool_names)
    for name, definition in definitions.items():
        if name == "original":
            continue
        runtime = output / "runtime" / name.lower()
        (runtime / "agents").mkdir(parents=True)
        metadata = asdict(definition)
        prompt = metadata.pop("system_prompt")
        metadata["disallowed_tools"] = sorted(definition.disallowed_tools)
        if definition.grounding is None:
            metadata.pop("grounding")
        (runtime / "agents/computer-use.md").write_text(
            "---\n" + yaml.safe_dump(metadata, sort_keys=True) + "---\n\n" + prompt + "\n",
            encoding="utf-8",
        )
        runtime_profiles = {key: {**profiles[source], "api_key": "${M5_DASHSCOPE_API_KEY}"}
                            for key, source in (("default", "planner"), ("planner", "planner"),
                                                ("locator", "locator"))}
        (runtime / "config.yaml").write_text(yaml.safe_dump({
            "llm": runtime_profiles,
            "agents": {"dirs": ["agents"], "llm_profile": "planner"},
            "toolsets": {"profiles": {"computer_use": {"tools": tool_names}}},
        }, sort_keys=True), encoding="utf-8")
        # Round-trip through production parsing; never use an operator credential.
        with patch.dict(os.environ, {"M5_DASHSCOPE_API_KEY": "offline-placeholder"}):
            loaded_config = AppConfig.load(runtime / "config.yaml")
        loaded_definition = parse_agent_file(runtime / "agents/computer-use.md")
        ComparisonContract(output, name).verify(loaded_config, loaded_definition)
        definitions[name] = loaded_definition
    snapshots = {name: await capture(definition, profiles, tool_names, png)
                 for name, definition in definitions.items()}
    write_json(output / "requests.json", snapshots)
    source_paths = [Path(__file__), BACKEND / "agents/computer_use.md", BACKEND / "uv.lock"]
    # Include transitive backend prompt/tool/config code rather than only this exporter.
    source_paths.extend(sorted((BACKEND / "core/src/tank_backend").rglob("*.py")))
    source_hashes = {str(p.relative_to(BACKEND)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in source_paths}
    write_json(output / "manifest.json", {
        "live_authorized": False, "model_requests": 0, "desktop_actions": 0,
        "scope": "Representative offline Runner -> LLM -> SDK bodies; not live trial evidence",
        "fixture": {"display": [100, 80], "backing": [200, 160], "display_id": 5,
                    "region": [100, 100, 800, 800], "time": 1.0,
                    "identity": "incrementing UUID integers, reset for each variant",
                    "transport": "httpx.MockTransport only; only reviewed public headers exported",
                    "assembly": "real Runner and desktop tools; ToolManager constructed offline"},
        "live_environment": "pending: display, OS, application versions and window geometry",
        "versions": {"python": sys.version, **{name: version(name)
                     for name in ("openai", "httpx", "Pillow", "PyYAML")}},
        "sources": source_hashes,
        "artifacts": {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sorted(output.rglob("*")) if p.is_file()},
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(prepare(args.config, args.output))


if __name__ == "__main__":
    main()
