"""Offline comparison exports exercise the production Runner and SDK."""

import hashlib
import json
import runpy
from pathlib import Path

import pytest


@pytest.fixture
async def runtime_bundle(tmp_path, monkeypatch):
    import yaml

    script = Path(__file__).resolve().parents[2] / "scripts/prepare_computer_comparison.py"
    config = tmp_path / "source.yaml"
    config.write_text(yaml.safe_dump({
        "llm": {"computer_use": {"api_key": "NEVER_EXPORT_THIS_SECRET",
            "model": "qwen3.7-flash-2026-07-15",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"}},
        "toolsets": {"profiles": {"computer_use": {"tools": ["screenshot", "click"]}}},
    }))
    output = tmp_path / "freeze"
    await runpy.run_path(str(script))["prepare"](config, output)
    monkeypatch.setenv("M5_DASHSCOPE_API_KEY", "OFFLINE_RUNTIME_SECRET")
    return output


@pytest.mark.parametrize("variant", ["A", "A-control", "B-host-only", "B-protocol-only",
                                     "B-combined", "C", "D"])
async def test_runtime_contract_accepts_resolved_generated_variants(runtime_bundle, variant):
    from tank_backend.agents.definition import load_agent_definitions
    from tank_backend.benchmarks.comparison_contract import ComparisonContract
    from tank_backend.config import AppConfig

    runtime = runtime_bundle / "runtime" / variant.lower()
    config = AppConfig.load(runtime / "config.yaml")
    definition = load_agent_definitions([runtime / "agents"])["computer_use"]
    ComparisonContract(runtime_bundle, variant).verify(config, definition)


@pytest.mark.parametrize("change", [
    "model", "endpoint", "temperature", "output", "usage", "thinking", "locator",
    "headers", "prompt", "grounding", "toolset", "missing_toolset", "dirs", "missing_profile",
    "environment", "credentials_only",
])
async def test_runtime_contract_detects_resolved_drift_without_exposing_secrets(
    runtime_bundle, monkeypatch, change,
):
    from dataclasses import replace

    import yaml

    from tank_backend.agents.definition import load_agent_definitions
    from tank_backend.benchmarks.comparison_contract import ComparisonContract
    from tank_backend.config import AppConfig

    runtime = runtime_bundle / "runtime/d"
    path = runtime / "config.yaml"
    raw = yaml.safe_load(path.read_text())
    edits = {
        "model": ("model", "different"), "endpoint": ("base_url", "https://other.invalid/v1"),
        "temperature": ("temperature", 0.123), "output": ("max_tokens", 9000),
        "usage": ("stream_options", False), "thinking": ("extra_body", {"enable_thinking": True}),
        "headers": ("extra_headers", {"Authorization": "NEVER_PRINT_THIS_SECRET"}),
    }
    if change in edits:
        field, value = edits[change]
        raw["llm"]["planner"][field] = value
    elif change == "locator":
        raw["llm"]["locator"]["model"] = "different"
    elif change == "toolset":
        raw["toolsets"]["profiles"]["computer_use"]["tools"] = []
    elif change == "missing_toolset":
        raw["toolsets"]["profiles"] = {}
    elif change == "dirs":
        raw["agents"]["dirs"] = ["agents", "other"]
    elif change == "missing_profile":
        del raw["llm"]["planner"]
    elif change == "environment":
        raw["llm"]["planner"]["model"] = "${M5_TEST_MODEL}"
        monkeypatch.setenv("M5_TEST_MODEL", "different")
    elif change == "credentials_only":
        monkeypatch.setenv("M5_DASHSCOPE_API_KEY", "NEW_SECRET_NOT_FROZEN")
    path.write_text(yaml.safe_dump(raw))
    config = AppConfig.load(path)
    definition = load_agent_definitions([runtime / "agents"])["computer_use"]
    if change == "prompt":
        definition = replace(definition, system_prompt="changed")
    elif change == "grounding":
        definition = replace(definition, grounding=None)
    contract = ComparisonContract(runtime_bundle, "D")
    if change == "credentials_only":
        contract.verify(config, definition)
    else:
        with pytest.raises(ValueError, match="Comparison contract") as error:
            contract.verify(config, definition)
        assert "NEVER_PRINT_THIS_SECRET" not in str(error.value)
        assert "OFFLINE_RUNTIME_SECRET" not in str(error.value)


async def test_driver_checks_runtime_contract_before_constructing_clients(
    runtime_bundle, monkeypatch,
):
    from unittest.mock import Mock

    from tank_backend.benchmarks import driver as module
    from tank_backend.benchmarks.comparison_contract import ComparisonContract
    from tank_backend.llm import profile

    client, manager = Mock(), Mock()
    monkeypatch.setattr(profile, "create_llm_from_profile", client)
    monkeypatch.setattr(module, "ToolManager", manager)
    monkeypatch.setattr(module, "disable_langfuse_tracing", lambda: None)
    with pytest.raises(ValueError, match="Comparison contract agent definition"):
        module.SubAgentDriver.create(
            "computer_use", runtime_bundle / "runtime/a/config.yaml",
            comparison=ComparisonContract(runtime_bundle, "D"),
        )
    client.assert_not_called()
    manager.assert_not_called()


@pytest.mark.parametrize("variant,record_only,status", [
    (variant, mode, 200) for mode in (False, True)
    for variant in ("A", "A-control", "B-host-only", "B-protocol-only", "B-combined", "C", "D")
] + [("A", True, 402), ("D", True, 402)])
async def test_generated_config_reaches_real_driver_and_sdk(
    runtime_bundle, monkeypatch, variant, record_only, status,
):
    from unittest.mock import Mock

    import httpx
    from openai import AsyncOpenAI

    from tank_backend.agents.approval import ToolApprovalPolicy
    from tank_backend.benchmarks import driver as module
    from tank_backend.benchmarks.comparison_contract import ComparisonContract
    from tank_backend.benchmarks.request_budget import RequestLimits
    from tank_backend.benchmarks.spend_http import SpendControl
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit
    from tank_backend.benchmarks.trace import TraceSink
    from tank_backend.llm import llm as llm_module
    from tank_backend.tools import computer_use_macos as macos
    from tank_backend.tools.groups import ComputerUseToolGroup
    from tank_backend.tools.manager import ToolManager

    manager = ToolManager.__new__(ToolManager)
    manager.tools = {t.get_info().name: t for t in ComputerUseToolGroup()._create_macos_tools()}
    manager.tool_metadata = {name: tool.get_metadata() for name, tool in manager.tools.items()}
    manager._media_store = manager._bus = None
    manager._approval_policy = ToolApprovalPolicy(computer_mode="allow")
    manager.set_session_id("offline")
    host = Mock(side_effect=AssertionError("Host access is forbidden"))
    for name in ("_load_quartz", "_capture_screenshot_macos", "_click_macos"):
        monkeypatch.setattr(macos, name, host)
    monkeypatch.setattr(module, "ToolManager", lambda *args, **kwargs: manager)
    monkeypatch.setattr(module, "disable_langfuse_tracing", lambda: None)
    monkeypatch.setattr(llm_module, "initialize_langfuse", lambda: None)
    monkeypatch.setattr(llm_module, "is_tracing_registered", lambda: False)
    bodies, clients = [], []

    def respond(request):
        bodies.append(json.loads(request.content))
        if status == 402:
            return httpx.Response(402, json={"error": {"message": "Insufficient balance"}})
        chunk = {"id": "offline", "object": "chat.completion.chunk", "created": 1,
                 "model": bodies[-1]["model"], "choices": [{"index": 0,
                 "delta": {"content": "done"}, "finish_reason": "stop"}],
                 "usage": {"prompt_tokens": 400000 if record_only else 2, "completion_tokens": 3,
                           "total_tokens": 400003 if record_only else 5}}
        return httpx.Response(200, content=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n")

    def client_factory(**kwargs):
        client = AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(respond)))
        clients.append(client)
        return client

    monkeypatch.setattr(llm_module, "AsyncOpenAI", client_factory)
    trace = TraceSink(runtime_bundle.parent / "trial")
    ledger = SpendLedger(SpendLimit(0, 0), record_only=True)
    spend = SpendControl(ledger, SpendLimit(0, 0), ()) if record_only else None
    try:
        driver = module.SubAgentDriver.create(
            "computer_use", runtime_bundle / "runtime" / variant.lower() / "config.yaml",
            comparison=ComparisonContract(runtime_bundle, variant), request_limits=RequestLimits(),
            spend=spend,
        )
        result = await driver.run("Reply done without tools", trace, timeout_s=5, max_steps=2)
        if status == 402:
            assert result.error is not None
            assert ledger.snapshot()["stop_reason"] == "unknown_usage"
        else:
            assert result.error is None
            assert result.final_text == "done"
        assert driver.describe()["comparison_contract"]["variant"] == variant
        if record_only:
            assert driver.describe()["token_budget"] == 0
            if status == 200:
                assert ledger.snapshot()["batch"]["known_tokens"] == 400003
                assert ledger.snapshot()["stop_reason"] is None
    finally:
        trace.close()
        for client in clients:
            await client.close()
    assert len(bodies) == 1
    frozen = json.loads((runtime_bundle / "requests.json").read_text())[variant][0]["body"]
    for key in ("model", "tools", "max_tokens", "temperature", "enable_thinking", "stream_options"):
        assert bodies[0].get(key) == frozen.get(key)
    host.assert_not_called()


@pytest.mark.parametrize("change", ["none", "modified", "missing", "added", "uncovered"])
def test_frozen_input_preflight_checks_hashes_coverage_and_inventory(tmp_path, change):
    from tank_backend.benchmarks.frozen_inputs import FrozenFile, FrozenInputs

    sources = tmp_path / "sources"
    sources.mkdir()
    source = sources / "agent.md"
    source.write_text("frozen prompt")
    frozen = FrozenInputs(
        (FrozenFile(source, hashlib.sha256(source.read_bytes()).hexdigest()),), (sources,),
    )
    required = [source]
    if change == "modified":
        source.write_text("changed prompt")
    elif change == "missing":
        source.unlink()
    elif change == "added":
        (sources / "new.md").write_text("new agent")
    elif change == "uncovered":
        required.append(tmp_path / "not-in-manifest.yaml")
    if change == "none":
        frozen.verify(required)
    else:
        with pytest.raises(ValueError, match="Frozen inputs"):
            frozen.verify(required)


@pytest.mark.parametrize("invalid", ["empty", "duplicate", "digest"])
def test_frozen_input_manifest_rejects_ambiguous_or_invalid_pins(tmp_path, invalid):
    from tank_backend.benchmarks.frozen_inputs import FrozenFile, FrozenInputs

    path = tmp_path / "input"
    path.write_text("frozen")
    item = FrozenFile(path, hashlib.sha256(path.read_bytes()).hexdigest())
    entries = {"empty": (), "duplicate": (item, item), "digest": (FrozenFile(path, "bad"),)}
    with pytest.raises(ValueError, match="Frozen inputs"):
        FrozenInputs(entries[invalid]).verify()


async def test_comparison_freeze_is_reproducible_and_uses_final_sdk_requests(tmp_path, monkeypatch):
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
    from tank_backend.agents.definition import load_agent_definitions
    from tank_backend.config import AppConfig

    monkeypatch.setenv("M5_DASHSCOPE_API_KEY", "OFFLINE_RUNTIME_SECRET")
    frozen_definitions = json.loads((first / "definitions.json").read_text())
    for variant in ("A", "A-control", "B-host-only", "B-protocol-only", "B-combined", "C", "D"):
        from dataclasses import asdict

        runtime = first / "runtime" / variant.lower()
        loaded = AppConfig.load(runtime / "config.yaml")
        definitions = load_agent_definitions([
            runtime / directory for directory in loaded.agents.dirs
        ])
        definition = definitions["computer_use"]
        actual = asdict(definition)
        actual["disallowed_tools"] = sorted(definition.disallowed_tools)
        assert json.loads(json.dumps(actual)) == frozen_definitions[variant]
        assert loaded.llm_profiles["planner"].api_key == "OFFLINE_RUNTIME_SECRET"
        assert loaded.llm_profiles["planner"].max_tokens == 8000
        assert list(loaded.toolsets.profiles["computer_use"].tools) == json.loads(
            (first / "toolset.json").read_text())
    assert not (first / "runtime/original").exists()
    for path in first.rglob("*"):
        if path.is_file():
            assert path.read_bytes() == (second / path.relative_to(first)).read_bytes()
            assert b"NEVER_EXPORT_THIS_SECRET" not in path.read_bytes()
            assert b"OFFLINE_RUNTIME_SECRET" not in path.read_bytes()
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


async def test_batch_proposal_preflight_is_offline_and_preserves_budget(
    runtime_bundle, monkeypatch,
):
    from unittest.mock import Mock

    from tank_backend.benchmarks.driver import SubAgentDriver

    forbidden = Mock(side_effect=AssertionError("offline preflight must not construct a driver"))
    monkeypatch.setattr(SubAgentDriver, "create", forbidden)
    script = Path(__file__).resolve().parents[2] / "scripts/prepare_computer_batch.py"
    api = runpy.run_path(str(script))
    output = runtime_bundle.parent / "proposal"
    api["prepare"](runtime_bundle, output)
    report = api["preflight"](runtime_bundle, output / "proposal.json")
    proposal = json.loads((output / "proposal.json").read_text())
    assert [row["variant"] for row in proposal["trials"]] == [
        "A-control", "B-protocol-only", "A", "B-host-only", "B-combined",
        "A", "B-combined", "C", "D", "B-combined", "C", "D", "A",
        "C", "D", "A", "B-combined",
    ]
    assert report["totals"] == {
        "trials": 17, "planner_requests": 272, "locator_requests": 90,
        "max_locator_requests": 45, "http_requests": 362,
        "tokens": 5100000, "task_seconds": 2040,
    }
    assert report["live_ready"] is False
    assert report["token_cost_gate"] == "disabled"
    assert report["effective_agent_token_budget"] == 0
    assert proposal["record_only"] is True
    assert proposal["budget_nano_usd"] == 8000000000
    assert "usable_input_bound" not in report["blockers"]
    assert "live_endpoint_and_image_scope_authorization" in report["blockers"]
    forbidden.assert_not_called()
    with pytest.raises(FileExistsError):
        api["prepare"](runtime_bundle, output)


@pytest.mark.parametrize("change", [
    "order", "budget", "requests", "authorization", "missing_pin", "config_bytes",
    "manifest_bytes", "agent_bytes", "adjacent_env", "extra_agent",
])
async def test_batch_proposal_rejects_drift(runtime_bundle, change):
    script = Path(__file__).resolve().parents[2] / "scripts/prepare_computer_batch.py"
    api = runpy.run_path(str(script))
    output = runtime_bundle.parent / "proposal"
    api["prepare"](runtime_bundle, output)
    path = output / "proposal.json"
    proposal = json.loads(path.read_text())
    if change == "order":
        proposal["trials"].reverse()
    elif change == "budget":
        proposal["budget_nano_usd"] += 1
    elif change == "requests":
        proposal["trials"][0]["request_limits"]["locator"] = 15
    elif change == "authorization":
        proposal["live_authorized"] = True
    elif change == "missing_pin":
        proposal["files"].pop(next(key for key in proposal["files"] if key.endswith("suite.yaml")))
    elif change in {"config_bytes", "manifest_bytes", "agent_bytes"}:
        relative = {"config_bytes": "runtime/a/config.yaml", "manifest_bytes": "manifest.json",
                    "agent_bytes": "runtime/a/agents/computer-use.md"}[change]
        target = runtime_bundle / relative
        target.write_text(target.read_text() + "\n")
    elif change == "adjacent_env":
        (runtime_bundle / "runtime/a/.env").write_text("M5_DASHSCOPE_API_KEY=secret")
    elif change == "extra_agent":
        (runtime_bundle / "runtime/a/agents/extra.md").write_text("---\nname: extra\n---\nx")
    path.write_text(json.dumps(proposal))
    with pytest.raises(ValueError):
        api["preflight"](runtime_bundle, path)
