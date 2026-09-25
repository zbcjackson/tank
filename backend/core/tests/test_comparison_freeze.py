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
                             "B-protocol-only", "B-combined", "B-pixels-only", "C", "D",
                                 "AX-quartz", "AX-press"}
    assert snapshot["original"][0]["body"]["max_tokens"] == 40000
    assert "stream_options" not in snapshot["original"][0]["body"]
    assert "enable_thinking" not in snapshot["original"][0]["body"]
    for name, requests in snapshot.items():
        assert len(requests) == (
            4 if name in {"C", "D", "AX-quartz", "AX-press"} else 2)
        first_request = requests[0]["body"]
        assert requests[0]["public_headers"] == {
            "HTTP-Referer": "http://localhost:3000", "X-Title": "Tank Voice Assistant"}
        tools = {t["function"]["name"] for t in first_request["tools"]}
        assert ("locate" in tools) == (
            name in {"C", "D", "AX-quartz", "AX-press"})
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
    # Same adapted contract: only host_restore differs, so the tool lists match.
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
        "A-control", "B-protocol-only", "A", "B-host-only", "B-combined", "B-pixels-only",
        "A", "B-combined", "C", "D", "B-combined", "C", "D", "A",
        "C", "D", "A", "B-combined",
        "D", "A", "B-combined", "C", "A", "B-combined", "C", "D",
        "B-combined", "C", "D", "A",
    ]
    assert report["totals"] == {
        "trials": 30, "planner_requests": 480, "locator_requests": 180,
        "max_locator_requests": 90, "http_requests": 660,
        "tokens": 9000000, "task_seconds": 3600,
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


PILOT_ENTRIES = [
    ("execute_a_control", "A-control", "legacy", False),
    ("execute_b_protocol_only", "B-protocol-only", "point", False),
    ("execute_a", "A", None, None),
    ("execute_b_host_only", "B-host-only", "legacy", True),
    ("execute_b_combined", "B-combined", "point", True),
    ("execute_b_pixels_only", "B-pixels-only", "pixels", False),
]
CORE_PHASES = ("pair-1", "pair-2", "pair-3", "pair-4", "pair-5", "pair-6")


async def test_core_trials_run_the_scheduled_pairs_in_order(runtime_bundle, monkeypatch):
    """The 12 core trials keep the paired order and each row's own limits."""
    from tank_backend.benchmarks import batch

    api = runpy.run_path(str(Path(__file__).resolve().parents[2]
                             / "scripts/prepare_computer_batch.py"))
    proposal_dir = runtime_bundle.parent / "proposal"
    api["prepare"](runtime_bundle, proposal_dir)
    proposal_path = proposal_dir / "proposal.json"
    proposal = json.loads(proposal_path.read_text())
    expected = [row["key"] for row in proposal["trials"] if row["phase"] in CORE_PHASES]
    assert len(expected) == 24 and proposal["core_requires_pilot_acceptance"] is True
    calls: list[tuple[str, dict]] = []

    async def run_batch(entries, **kwargs):
        calls.append((entries[0].key, kwargs))
        return {"completed": [entries[0].key], "spend": {}}

    monkeypatch.setattr(batch, "run_batch", run_batch)
    output = runtime_bundle.parent / "core"
    with pytest.raises(ValueError, match="authorization"):
        await api["execute_core_trials"](runtime_bundle, proposal_path, output)
    assert calls == []
    with pytest.raises(ValueError, match="pilot"):
        await api["execute_core_trials"](runtime_bundle, proposal_path, output,
                                        live_authorized=True)
    assert calls == []
    await api["execute_core_trials"](runtime_bundle, proposal_path, output,
                                    live_authorized=True, pilot_acceptance="recorded")
    assert [key for key, _ in calls] == expected
    by_key = {row["key"]: row for row in proposal["trials"]}
    for key, kwargs in calls:
        row = by_key[key]
        assert kwargs["request_limits"].planner == row["request_limits"]["planner"]
        assert kwargs["request_limits"].locator == row["request_limits"]["locator"]
        assert kwargs["batch_request_limit"] == row["request_limits"]["total"]
        assert kwargs["record_only"] is True and kwargs["input_cleanup"] is True
        assert kwargs["trial_limit"].tokens == row["tokens"]


async def test_framework_pairs_alternate_a_and_a_control(runtime_bundle, monkeypatch):
    """A vs A-control: the framework change must be measured on its own."""
    from tank_backend.benchmarks import batch

    api = runpy.run_path(str(Path(__file__).resolve().parents[2]
                             / "scripts/prepare_computer_batch.py"))
    proposal_dir = runtime_bundle.parent / "proposal"
    api["prepare"](runtime_bundle, proposal_dir)
    proposal_path = proposal_dir / "proposal.json"
    calls: list[tuple[list[str], dict]] = []

    async def run_batch(entries, **kwargs):
        calls.append(([entry.key for entry in entries], kwargs))
        return {"completed": [entry.key for entry in entries], "spend": {}}

    monkeypatch.setattr(batch, "run_batch", run_batch)
    output = runtime_bundle.parent / "framework"
    with pytest.raises(ValueError, match="authorization"):
        await api["execute_framework_pair"](runtime_bundle, proposal_path, output)
    assert calls == []
    with pytest.raises(ValueError, match="pilot"):
        await api["execute_framework_pair"](runtime_bundle, proposal_path, output,
                                           live_authorized=True)
    assert calls == []
    await api["execute_framework_pair"](runtime_bundle, proposal_path, output,
                                       live_authorized=True, pilot_acceptance="recorded",
                                       pairs=4)
    assert len(calls) == 4
    for index, (keys, kwargs) in enumerate(calls, start=1):
        variants = ["A-control" if key.startswith("pilot-a-control") else "A"
                    for key in keys]
        assert variants == (["A", "A-control"] if index % 2 else ["A-control", "A"])
        assert keys[0].endswith(f"fw{index}")
        assert kwargs["batch_request_limit"] == 32
        assert kwargs["record_only"] is True and kwargs["input_cleanup"] is True
        assert kwargs["request_limits"].planner == 16
        assert kwargs["request_limits"].locator == 0
    # run_batch is stubbed here, so assert the recorded plan rather than trial dirs.
    record = json.loads((output / "framework-result.json").read_text())
    assert record["pairs"] == 4 and record["pilot_acceptance"] == "recorded"
    assert record["order"] == [["A", "A-control"], ["A-control", "A"],
                               ["A", "A-control"], ["A-control", "A"]]


async def test_core_trials_stop_on_proposal_drift(runtime_bundle, monkeypatch):
    from unittest.mock import AsyncMock

    from tank_backend.benchmarks import batch

    api = runpy.run_path(str(Path(__file__).resolve().parents[2]
                             / "scripts/prepare_computer_batch.py"))
    directory = runtime_bundle.parent / "proposal"
    api["prepare"](runtime_bundle, directory)
    path = directory / "proposal.json"
    proposal = json.loads(path.read_text())
    proposal["trials"].reverse()
    path.write_text(json.dumps(proposal))
    execute = AsyncMock()
    monkeypatch.setattr(batch, "run_batch", execute)
    with pytest.raises(ValueError):
        await api["execute_core_trials"](runtime_bundle, path, directory / "core",
                                        live_authorized=True, pilot_acceptance="recorded")
    execute.assert_not_called()


async def test_record_only_enforced_agent_budget_stops_planner_loop(
    runtime_bundle, monkeypatch,
):
    """M6 calc trials keep the shared 300000 budget while the ledger only records."""
    from unittest.mock import Mock

    import httpx
    from openai import AsyncOpenAI

    from tank_backend.benchmarks import driver as module
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
    from tank_backend.agents.approval import ToolApprovalPolicy
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
        call = {"id": f"offline-{len(bodies)}", "object": "chat.completion.chunk",
                "created": 1, "model": bodies[-1]["model"],
                "choices": [{"index": 0, "delta": {"tool_calls": [{
                    "index": 0, "id": f"call-{len(bodies)}", "type": "function",
                    "function": {"name": "screenshot", "arguments": "{}"}}]},
                    "finish_reason": None}]}
        finish = {"id": f"offline-{len(bodies)}", "object": "chat.completion.chunk",
                  "created": 1, "model": bodies[-1]["model"],
                  "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                  "usage": {"prompt_tokens": 190000, "completion_tokens": 10000,
                            "total_tokens": 200000}}
        return httpx.Response(200, content="".join(
            f"data: {json.dumps(chunk)}\n\n" for chunk in (call, finish)) + "data: [DONE]\n\n")

    def client_factory(**kwargs):
        client = AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(respond)))
        clients.append(client)
        return client

    monkeypatch.setattr(llm_module, "AsyncOpenAI", client_factory)
    trace = TraceSink(runtime_bundle.parent / "trial-budget-planner")
    ledger = SpendLedger(SpendLimit(0, 0), record_only=True)
    spend = SpendControl(ledger, SpendLimit(0, 0), ())
    try:
        driver = module.SubAgentDriver.create(
            "computer_use", runtime_bundle / "runtime/a/config.yaml",
            request_limits=RequestLimits(), spend=spend, enforce_agent_budget=True,
        )
        assert driver.describe()["token_budget"] == 300000
        assert driver.describe()["agent_budget_enforced"] is True
        result = await driver.run("Keep screenshotting", trace, timeout_s=5, max_steps=6)
        assert len(bodies) == 2, "the shared budget must stop the third request"
        assert "token budget" in result.final_text
        assert result.stop_reason != "request_limit"
        assert ledger.snapshot()["batch"]["known_tokens"] == 400000
        assert ledger.snapshot()["stop_reason"] is None
    finally:
        trace.close()
        for client in clients:
            await client.close()
    # Only the first request's screenshot dispatches; the budget stops the rest.
    assert host.call_count == 1


async def test_record_only_enforced_agent_budget_stops_grounded_context(
    runtime_bundle, monkeypatch,
):
    """Split arms stop through the shared context budget (planner + locator)."""
    from unittest.mock import Mock

    import httpx
    from openai import AsyncOpenAI

    from tank_backend.benchmarks import driver as module
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
    from tank_backend.agents.approval import ToolApprovalPolicy
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
        call = {"id": f"offline-{len(bodies)}", "object": "chat.completion.chunk",
                "created": 1, "model": bodies[-1]["model"],
                "choices": [{"index": 0, "delta": {"tool_calls": [{
                    "index": 0, "id": f"call-{len(bodies)}", "type": "function",
                    "function": {"name": "screenshot", "arguments": "{}"}}]},
                    "finish_reason": None}]}
        finish = {"id": f"offline-{len(bodies)}", "object": "chat.completion.chunk",
                  "created": 1, "model": bodies[-1]["model"],
                  "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                  "usage": {"prompt_tokens": 190000, "completion_tokens": 10000,
                            "total_tokens": 200000}}
        return httpx.Response(200, content="".join(
            f"data: {json.dumps(chunk)}\n\n" for chunk in (call, finish)) + "data: [DONE]\n\n")

    def client_factory(**kwargs):
        client = AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(respond)))
        clients.append(client)
        return client

    monkeypatch.setattr(llm_module, "AsyncOpenAI", client_factory)
    trace = TraceSink(runtime_bundle.parent / "trial-budget-context")
    ledger = SpendLedger(SpendLimit(0, 0), record_only=True)
    spend = SpendControl(ledger, SpendLimit(0, 0), ())
    try:
        driver = module.SubAgentDriver.create(
            "computer_use", runtime_bundle / "runtime/d/config.yaml",
            request_limits=RequestLimits(), spend=spend, enforce_agent_budget=True,
        )
        assert driver.describe()["token_budget"] == 300000
        result = await driver.run("Keep screenshotting", trace, timeout_s=5, max_steps=6)
        assert len(bodies) == 2, "the shared context budget must stop the third request"
        assert result.stop_reason == "budget"
        assert "300000" in (result.error or "")
        assert ledger.snapshot()["batch"]["known_tokens"] == 400000
        assert ledger.snapshot()["stop_reason"] is None
    finally:
        trace.close()
        for client in clients:
            await client.close()
    # Only the first request's screenshot dispatches; the budget stops the rest.
    assert host.call_count == 1


async def test_m6_calc_schedule_fixes_pairs_and_enforces_agent_budget(
    runtime_bundle, monkeypatch,
):
    """The M6 calc proposal: 3 pairs x 4 arms, record-only ledger, enforced budget."""
    from tank_backend.benchmarks import batch

    api = runpy.run_path(str(Path(__file__).resolve().parents[2]
                             / "scripts/prepare_computer_batch.py"))
    proposal_dir = runtime_bundle.parent / "m6-proposal"
    api["prepare_m6_calc"](runtime_bundle, proposal_dir)
    proposal_path = proposal_dir / "proposal.json"
    proposal = json.loads(proposal_path.read_text())
    m6_phases = ("m6-pair-1", "m6-pair-2", "m6-pair-3")
    rows = [row for row in proposal["trials"] if row["phase"] in m6_phases]
    assert len(rows) == 12
    assert proposal["record_only"] is True
    assert proposal["enforce_agent_budget"] is True
    assert proposal["core_requires_pilot_acceptance"] is True
    variants = [row["variant"] for row in rows]
    assert set(variants) == {"A", "B-combined", "C", "D"}
    assert all(row["task_id"] == "calc-open" for row in rows)
    assert all(row["timeout_s"] == 120 and row["max_steps"] == 15 for row in rows)
    assert all(row["tokens"] == 300000 for row in rows)
    for row in rows:
        locator = 15 if row["variant"] in {"C", "D"} else 0
        assert row["request_limits"] == {"planner": 16, "locator": locator,
                                         "total": 16 + locator}
    preflight = api["preflight_m6_calc"](runtime_bundle, proposal_path)
    assert preflight["offline_checks_passed"] is True
    assert preflight["effective_agent_token_budget"] == 300000
    assert preflight["token_cost_gate"] == "record-only"
    calls: list[tuple[str, dict]] = []

    async def run_batch(entries, **kwargs):
        calls.append((entries[0].key, kwargs))
        return {"completed": [entries[0].key], "spend": {}}

    monkeypatch.setattr(batch, "run_batch", run_batch)
    output = runtime_bundle.parent / "m6-out"
    with pytest.raises(ValueError, match="authorization"):
        await api["execute_m6_calc_trials"](runtime_bundle, proposal_path, output)
    assert calls == []
    with pytest.raises(ValueError, match="pilot"):
        await api["execute_m6_calc_trials"](runtime_bundle, proposal_path, output,
                                           live_authorized=True)
    assert calls == []
    await api["execute_m6_calc_trials"](runtime_bundle, proposal_path, output,
                                       live_authorized=True, pilot_acceptance="recorded")
    assert [key for key, _ in calls] == [row["key"] for row in rows]
    for (_, kwargs) in calls:
        assert kwargs["record_only"] is True
        assert kwargs["enforce_agent_budget"] is True
        assert kwargs["input_cleanup"] is True
    record = json.loads((output / "m6-result.json").read_text())
    assert record["pilot_acceptance"] == "recorded"
    assert record["enforce_agent_budget"] is True
    assert len(record["completed"]) == 12
    # Drift in the fixed schedule is refused before any execution.
    drifted = json.loads(proposal_path.read_text())
    drifted["trials"][0]["tokens"] = 999999
    drift_path = runtime_bundle.parent / "m6-drift"
    drift_path.mkdir()
    (drift_path / "proposal.json").write_text(json.dumps(drifted))
    calls.clear()
    with pytest.raises(ValueError):
        await api["execute_m6_calc_trials"](runtime_bundle, drift_path / "proposal.json",
                                           runtime_bundle.parent / "m6-drift-out",
                                           live_authorized=True, pilot_acceptance="recorded")
    assert calls == []


@pytest.mark.parametrize("entry,variant,protocol,host_restore", PILOT_ENTRIES)
async def test_single_pilot_entry_preserves_scope_and_cleanup(
    runtime_bundle, monkeypatch, entry, variant, protocol, host_restore,
):
    from unittest.mock import AsyncMock

    from tank_backend.agents.definition import load_agent_definitions
    from tank_backend.benchmarks import batch
    from tank_backend.config import AppConfig

    api = runpy.run_path(str(Path(__file__).resolve().parents[2]
                             / "scripts/prepare_computer_batch.py"))
    proposal_dir = runtime_bundle.parent / "proposal"
    api["prepare"](runtime_bundle, proposal_dir)
    key = f"pilot-{variant.lower()}"
    execute = AsyncMock(return_value={"completed": [key]})
    monkeypatch.setattr(batch, "run_batch", execute)
    proposal_path = proposal_dir / "proposal.json"
    output = runtime_bundle.parent / "live"
    with pytest.raises(ValueError, match="authorization"):
        await api[entry](runtime_bundle, proposal_path, output)
    execute.assert_not_called()
    await api[entry](runtime_bundle, proposal_path, output, live_authorized=True)
    entries = execute.call_args.args[0]
    assert len(entries) == 1 and entries[0].key == key
    assert entries[0].comparison.variant == variant
    assert entries[0].config_path.resolve() == (
        runtime_bundle / "runtime" / variant.lower() / "config.yaml"
    )
    runtime = entries[0].config_path.parent
    config = AppConfig.load(entries[0].config_path)
    definition = load_agent_definitions([runtime / "agents"])["computer_use"]
    assert definition.model is not None
    assert config.llm_profiles[definition.model].model == "qwen3.7-flash-2026-07-15"
    if protocol is None:
        # A keeps the production defaults: no grounding override at all.
        assert definition.grounding is None
    else:
        assert definition.grounding is not None
        assert definition.grounding.mode == "integrated"
        assert definition.grounding.host_restore is host_restore
        assert definition.grounding.protocol == protocol
    kwargs = execute.call_args.kwargs
    assert kwargs["input_cleanup"] is True and kwargs["record_only"] is True
    assert kwargs["batch_request_limit"] == 16
    assert kwargs["request_limits"].planner == 16
    assert kwargs["request_limits"].locator == 0
    kwargs["frozen_inputs"].verify([proposal_path])
    execute.assert_awaited_once()


@pytest.mark.parametrize("change", ["cleanup", "runtime", "proposal_order"])
@pytest.mark.parametrize("entry,variant,protocol,host_restore", PILOT_ENTRIES)
async def test_single_pilot_drift_stops_before_batch(
    runtime_bundle, monkeypatch, change, entry, variant, protocol, host_restore,
):
    from unittest.mock import AsyncMock

    from tank_backend.benchmarks import batch

    api = runpy.run_path(str(Path(__file__).resolve().parents[2]
                             / "scripts/prepare_computer_batch.py"))
    directory = runtime_bundle.parent / "proposal"
    api["prepare"](runtime_bundle, directory)
    path = directory / "proposal.json"
    proposal = json.loads(path.read_text())
    if change == "cleanup":
        proposal["input_cleanup"] = False
    elif change == "proposal_order":
        proposal["trials"].reverse()
    else:
        config = runtime_bundle / "runtime" / variant.lower() / "config.yaml"
        config.write_text(config.read_text() + "\n")
    path.write_text(json.dumps(proposal))
    execute = AsyncMock()
    monkeypatch.setattr(batch, "run_batch", execute)
    with pytest.raises(ValueError):
        await api[entry](
            runtime_bundle, path, directory / "live", live_authorized=True,
        )
    execute.assert_not_called()


@pytest.mark.parametrize("entry,variant,protocol,host_restore", PILOT_ENTRIES)
async def test_single_pilot_rejects_proposal_changed_during_preflight(
    runtime_bundle, monkeypatch, entry, variant, protocol, host_restore,
):
    from unittest.mock import AsyncMock

    from tank_backend.benchmarks import batch

    api = runpy.run_path(str(Path(__file__).resolve().parents[2]
                             / "scripts/prepare_computer_batch.py"))
    directory = runtime_bundle.parent / "proposal"
    api["prepare"](runtime_bundle, directory)
    path = directory / "proposal.json"
    original = api["preflight"]

    def change_after_check(freeze, proposal):
        result = original(freeze, proposal)
        proposal.write_text(proposal.read_text() + "\n")
        return result

    monkeypatch.setitem(api[entry].__globals__, "preflight", change_after_check)
    execute = AsyncMock()
    monkeypatch.setattr(batch, "run_batch", execute)
    with pytest.raises(ValueError, match="changed during preflight"):
        await api[entry](
            runtime_bundle, path, directory / "live", live_authorized=True,
        )
    execute.assert_not_called()


async def test_m6_tasks_schedule_and_per_task_executor(runtime_bundle, monkeypatch):
    """Item 3: A + C across the macOS tasks, three alternating rounds each."""
    from tank_backend.benchmarks import batch

    api = runpy.run_path(str(Path(__file__).resolve().parents[2]
                             / "scripts/prepare_computer_batch.py"))
    proposal_dir = runtime_bundle.parent / "m6-tasks-proposal"
    api["prepare_m6_tasks"](runtime_bundle, proposal_dir)
    proposal_path = proposal_dir / "proposal.json"
    proposal = json.loads(proposal_path.read_text())
    rows = proposal["trials"]
    assert len(rows) == 78  # 13 tasks x 2 arms x 3 rounds; calc-open reuses item 2
    assert "calc-open" not in {row["task_id"] for row in rows}
    assert proposal["record_only"] is True
    assert proposal["enforce_agent_budget"] is True
    by_task: dict[str, list[dict]] = {}
    for row in rows:
        by_task.setdefault(row["task_id"], []).append(row)
    assert len(by_task) == 13
    for task_rows in by_task.values():
        arms = [row["variant"] for row in task_rows]
        assert arms.count("A") == 3 and arms.count("C") == 3
        # Each round carries both arms; the first hand alternates per round.
        for start in (0, 2, 4):
            assert arms[start] != arms[start + 1]
        assert [arms[0], arms[2], arms[4]] in (["A", "C", "A"], ["C", "A", "C"])
        for row in task_rows:
            locator = 15 if row["variant"] == "C" else 0
            assert row["request_limits"] == {"planner": 16, "locator": locator,
                                             "total": 16 + locator}
            assert row["tokens"] == 300000 and row["max_steps"] == 15
    preflight = api["preflight_m6_tasks"](runtime_bundle, proposal_path)
    assert preflight["offline_checks_passed"] is True
    assert preflight["effective_agent_token_budget"] == 300000
    calls: list[tuple[str, dict]] = []

    async def run_batch(entries, **kwargs):
        calls.append((entries[0].key, kwargs))
        return {"completed": [entries[0].key], "spend": {}}

    monkeypatch.setattr(batch, "run_batch", run_batch)
    output = runtime_bundle.parent / "m6-tasks-out"
    with pytest.raises(ValueError, match="authorization"):
        await api["execute_m6_task_trials"](runtime_bundle, proposal_path, output,
                                            task_id="browser-navigate")
    assert calls == []
    await api["execute_m6_task_trials"](runtime_bundle, proposal_path, output,
                                        task_id="browser-navigate",
                                        live_authorized=True, pilot_acceptance="recorded")
    assert [key for key, _ in calls] == ["browser-navigate-r1-a", "browser-navigate-r1-c",
                                           "browser-navigate-r2-c", "browser-navigate-r2-a",
                                           "browser-navigate-r3-a", "browser-navigate-r3-c"]
    for _, kwargs in calls:
        assert kwargs["record_only"] is True and kwargs["enforce_agent_budget"] is True
    record = json.loads((output / "m6-tasks-result.json").read_text())
    assert record["task_id"] == "browser-navigate" and len(record["completed"]) == 6
    with pytest.raises(ValueError, match="Unknown task"):
        await api["execute_m6_task_trials"](runtime_bundle, proposal_path,
                                            runtime_bundle.parent / "m6-bad",
                                            task_id="nope", live_authorized=True,
                                            pilot_acceptance="recorded")


async def test_m6_longhistory_manifest(runtime_bundle, monkeypatch):
    """Item 4: one round per arm at 600s / 60 tools / 60 locates / 300k tokens."""
    from tank_backend.benchmarks import batch

    api = runpy.run_path(str(Path(__file__).resolve().parents[2]
                             / "scripts/prepare_computer_batch.py"))
    proposal_dir = runtime_bundle.parent / "m6-lh-proposal"
    api["prepare_m6_longhistory"](runtime_bundle, proposal_dir)
    proposal_path = proposal_dir / "proposal.json"
    proposal = json.loads(proposal_path.read_text())
    rows = proposal["trials"]
    assert len(rows) == 2
    assert all(row["task_id"] == "long-history" for row in rows)
    assert [row["variant"] for row in rows] == ["A", "C"]
    for row in rows:
        locator = 60 if row["variant"] == "C" else 0
        assert row["request_limits"]["locator"] == locator
        assert row["timeout_s"] == 600 and row["max_steps"] == 60
        assert row["tokens"] == 300000
    assert proposal["enforce_agent_budget"] is True
    preflight = api["preflight_m6_longhistory"](runtime_bundle, proposal_path)
    assert preflight["offline_checks_passed"] is True
    calls: list[tuple[str, dict]] = []

    async def run_batch(entries, **kwargs):
        calls.append((entries[0].key, kwargs))
        return {"completed": [entries[0].key], "spend": {}}

    monkeypatch.setattr(batch, "run_batch", run_batch)
    with pytest.raises(ValueError, match="authorization"):
        await api["execute_m6_longhistory"](runtime_bundle, proposal_path,
                                            runtime_bundle.parent / "lh-out")
    assert calls == []
    await api["execute_m6_longhistory"](runtime_bundle, proposal_path,
                                        runtime_bundle.parent / "lh-out",
                                        live_authorized=True, pilot_acceptance="recorded")
    assert [key for key, _ in calls] == ["long-history-r1-a", "long-history-r1-c"]
    for _, kwargs in calls:
        assert kwargs["enforce_agent_budget"] is True
        assert kwargs["record_only"] is True


@pytest.mark.parametrize("variant", ["AX-quartz", "AX-press"])
async def test_runtime_contract_accepts_ax_variants(runtime_bundle, variant):
    from tank_backend.agents.definition import load_agent_definitions
    from tank_backend.benchmarks.comparison_contract import ComparisonContract
    from tank_backend.config import AppConfig

    runtime = runtime_bundle / "runtime" / variant.lower()
    config = AppConfig.load(runtime / "config.yaml")
    definition = load_agent_definitions([runtime / "agents"])["computer_use"]
    assert definition.grounding is not None
    assert definition.grounding.mode == "ax"
    assert definition.grounding.ax_action == ("quartz" if variant == "AX-quartz"
                                              else "ax_press")
    ComparisonContract(runtime_bundle, variant).verify(config, definition)


@pytest.mark.parametrize("variant", ["AX-quartz", "AX-press"])
async def test_ax_variant_snapshot_uses_text_selection_without_images(
    runtime_bundle, variant,
):
    """The frozen AX locate request carries the numbered candidate list as text,
    never an image; the planner screenshot binds the offline window."""
    snapshots = json.loads((runtime_bundle / "requests.json").read_text())
    requests = snapshots[variant]
    assert len(requests) == 4
    selection = requests[2]["body"]
    assert not selection.get("stream")
    assert selection["tools"][0]["function"]["name"] == "select"
    assert "image_url" not in json.dumps(selection["messages"])
    content = selection["messages"][1]["content"]
    assert "Candidates:" in content and "Target: unique blue button" in content
    parameters = selection["tools"][0]["function"]["parameters"]["properties"]
    assert parameters["index"]["maximum"] >= 1
    assert parameters["status"]["enum"] == ["found", "not_found", "ambiguous"]


async def test_m7_ax_schedule_fixes_pairs_and_executor(runtime_bundle, monkeypatch):
    """The M7 AX proposal: 3 rounds x 3 arms (A / AX-quartz / AX-press), rotated."""
    from tank_backend.benchmarks import batch

    api = runpy.run_path(str(Path(__file__).resolve().parents[2]
                             / "scripts/prepare_computer_batch.py"))
    proposal_dir = runtime_bundle.parent / "m7-proposal"
    api["prepare_m7_ax"](runtime_bundle, proposal_dir)
    proposal_path = proposal_dir / "proposal.json"
    proposal = json.loads(proposal_path.read_text())
    rows = proposal["trials"]
    assert len(rows) == 9
    assert proposal["record_only"] is True
    assert proposal["enforce_agent_budget"] is True
    assert proposal["core_requires_pilot_acceptance"] is True
    variants = [row["variant"] for row in rows]
    assert set(variants) == {"A", "AX-quartz", "AX-press"}
    assert all(row["task_id"] == "calc-open" for row in rows)
    assert all(row["timeout_s"] == 120 and row["max_steps"] == 15 for row in rows)
    for row in rows:
        locator = 15 if row["variant"] != "A" else 0
        assert row["request_limits"] == {"planner": 16, "locator": locator,
                                         "total": 16 + locator}
    preflight = api["preflight_m7_ax"](runtime_bundle, proposal_path)
    assert preflight["offline_checks_passed"] is True
    assert preflight["effective_agent_token_budget"] == 300000
    calls: list[tuple[str, dict]] = []

    async def run_batch(entries, **kwargs):
        calls.append((entries[0].key, kwargs))
        return {"completed": [entries[0].key], "spend": {}}

    monkeypatch.setattr(batch, "run_batch", run_batch)
    output = runtime_bundle.parent / "m7-out"
    with pytest.raises(ValueError, match="authorization"):
        await api["execute_m7_ax_trials"](runtime_bundle, proposal_path, output)
    assert calls == []
    with pytest.raises(ValueError, match="pilot"):
        await api["execute_m7_ax_trials"](runtime_bundle, proposal_path, output,
                                          live_authorized=True)
    assert calls == []
    await api["execute_m7_ax_trials"](runtime_bundle, proposal_path, output,
                                      live_authorized=True,
                                      pilot_acceptance="recorded")
    assert [key for key, _ in calls] == [row["key"] for row in rows]
    for (_, kwargs) in calls:
        assert kwargs["record_only"] is True
        assert kwargs["enforce_agent_budget"] is True
        assert kwargs["input_cleanup"] is True
    record = json.loads((output / "m7-result.json").read_text())
    assert record["pilot_acceptance"] == "recorded"
    assert len(record["completed"]) == 9
    drifted = json.loads(proposal_path.read_text())
    drifted["trials"][0]["tokens"] = 999999
    drift_path = runtime_bundle.parent / "m7-drift"
    drift_path.mkdir()
    (drift_path / "proposal.json").write_text(json.dumps(drifted))
    calls.clear()
    with pytest.raises(ValueError):
        await api["execute_m7_ax_trials"](runtime_bundle, drift_path / "proposal.json",
                                          runtime_bundle.parent / "m7-drift-out",
                                          live_authorized=True,
                                          pilot_acceptance="recorded")
    assert calls == []
