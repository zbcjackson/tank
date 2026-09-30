"""S1 adapters through the real candidate builder; only native boundaries are fake."""

import asyncio
from dataclasses import replace
from unittest.mock import Mock

import pytest
from agent_computer_use.action_builder import ActionBuilder
from agent_computer_use.contracts import GoalContract
from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext
from tank_backend.tools.computer_ax import AXCandidate, AXElementRef
from tank_backend.tools.computer_observation import Observation


def frame() -> Observation:
    return Observation("frame", "session", 5, (100, 80), (100, 80), (0, 0, 100, 80),
                       "hash", 0, (5, 0, 0, 100, 80, 200, 160), 7, (0, 0, 100, 80))


def goal(label: str = "Save") -> GoalContract:
    return GoalContract.from_input({
        "schema_version": 1, "objective": "Save", "scope": "window-7",
        "milestones": [{"id": "save", "operation": "click", "role": "button",
                        "label": label, "postcondition": {"key": "saved", "value": "yes"}}],
        "completion": [{"key": "saved", "value": "yes"}],
    })


def candidate(native: object, label: str, index: int = 1) -> AXCandidate:
    return AXCandidate(index, "AXButton", label, "", "", "", ("AXPress",), True,
                       (10, 10, 20, 20), AXElementRef(native, False, 80),
                       ancestors=(("AXWindow", "Document"),), pid=42, window_id=7)


def context() -> SubAgentContext:
    ctx = SubAgentContext(SubAgentAuthorization(frozenset({"desktop"})),
                          SubAgentBudget(), asyncio.Event())
    ctx.runtime.bind("task")
    return ctx


async def test_ax_identity_survives_reordering_but_not_disappearance(monkeypatch) -> None:
    from agent_computer_use.observation import AXObservationSource

    a, b = candidate(object(), "Save"), candidate(object(), "Cancel", 2)
    read = Mock(side_effect=[([a, b], False), ([replace(b, index=1), replace(a, index=2,
                         value="new", focused=True)], False), ([b], False), ([a, b], False)])
    monkeypatch.setattr("agent_computer_use.observation.ax_window_candidates", read)
    source = AXObservationSource(frame(), "window-7")
    ctx = context()
    first = await source.observe("window-7", ctx)
    second = await source.observe("window-7", ctx)
    assert first.elements[0].ref == second.elements[1].ref
    assert second.elements[1].value == "new" and second.elements[1].focused
    assert second.elements[1].ancestors == (("AXWindow", "Document"),)
    assert first.observation_id != second.observation_id
    assert second.generation > first.generation
    actions = ActionBuilder().build("goal", 1, goal(), goal().milestones[0], second)
    assert actions.reason == "rules_unique"
    assert actions.actions[0].target_ref == first.elements[0].ref
    await source.observe("window-7", ctx)
    fourth = await source.observe("window-7", ctx)
    assert fourth.elements[0].ref != first.elements[0].ref


async def test_ax_fill_requires_settable_value_and_keeps_parent_text(monkeypatch) -> None:
    from agent_computer_use.observation import AXObservationSource

    field = replace(candidate(object(), "Name"), role="AXTextField", actions=(),
                    value_settable=True)
    text = replace(candidate(object(), "Name", 2), role="AXStaticText", actions=())
    monkeypatch.setattr("agent_computer_use.observation.ax_window_candidates",
                        lambda *args: ([field, text], False))
    snapshot = await AXObservationSource(frame(), "window-7").observe("window-7", context())
    assert snapshot.elements[0].actions == ("fill",)
    assert snapshot.elements[0].kind == "control"
    assert snapshot.elements[1].kind == "text_region"
    assert snapshot.elements[1].actions == ()


@pytest.mark.parametrize("case", ["scope", "revoked", "closed", "foreign_window"])
async def test_ax_rejects_unbound_reads(monkeypatch, case: str) -> None:
    from agent_computer_use.observation import AXObservationSource
    from tank_backend.agents.subagent import SubAgentStopped

    read = Mock(return_value=([replace(candidate(object(), "Save"), window_id=8)], False))
    monkeypatch.setattr("agent_computer_use.observation.ax_window_candidates", read)
    ctx = context()
    source = AXObservationSource(frame(), "window-7")
    if case == "revoked":
        ctx.authorization.revoke()
    elif case == "closed":
        await source.aclose()
    with pytest.raises(SubAgentStopped):
        await source.observe("other" if case == "scope" else "window-7", ctx)
    assert read.call_count == (1 if case == "foreign_window" else 0)


async def test_frozen_ax_golden_cases(monkeypatch) -> None:
    import hashlib
    import json
    from pathlib import Path
    from agent_computer_use.observation import AXObservationSource

    root = Path(__file__).resolve().parents[3] / "benchmarks/computer_use/fixtures/s1"
    manifest = json.loads((root / "manifest.json").read_text())
    splits: dict[str, set[str]] = {}
    for case in manifest["cases"]:
        assert hashlib.sha256((root / case["image"]).read_bytes()).hexdigest() == case["sha256"]
        splits.setdefault(case["split"], set()).add(case["family"])
        candidates = [candidate(object(), label, i + 1)
                      for i, label in enumerate(case["ax_labels"])]
        if case["ax_text_child"]:
            candidates.append(replace(candidate(object(), case["target"], 9),
                                      role="AXStaticText", actions=()))
        monkeypatch.setattr("agent_computer_use.observation.ax_window_candidates",
                            lambda *args: (candidates, False))
        snapshot = await AXObservationSource(frame(), "window-7").observe("window-7", context())
        target = goal(case["target"])
        actions = ActionBuilder().build("goal", 1, target, target.milestones[0], snapshot)
        if case["category"] == "duplicate":
            assert actions.reason == "ambiguous_target" and not actions.actions
        elif case["category"] == "absent":
            assert actions.reason == "no_viable_actions" and not actions.actions
        else:
            assert actions.reason == "rules_unique" and len(actions.actions) == 1
            assert actions.actions[0].target_ref == snapshot.elements[0].ref
    assert not splits["calibration"] & splits["holdout"]


async def test_ax_text_view_through_governed_sdk_has_no_images_or_old_snapshot(monkeypatch) -> None:
    import json
    import httpx
    from agent_computer_use.contracts import snapshot_text
    from agent_computer_use.observation import AXObservationSource
    from tank_backend.llm.profile import LLMProfile

    requests = []

    async def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "test", "object": "chat.completion", "created": 1, "model": "test",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ready"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        })

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda: httpx.MockTransport(respond))
    target = candidate(object(), "保存")
    monkeypatch.setattr("agent_computer_use.observation.ax_window_candidates",
                        lambda *args: ([target], False))
    ctx = SubAgentContext(SubAgentAuthorization(frozenset({"desktop", "network"})),
                          SubAgentBudget(), asyncio.Event())
    ctx.runtime.configure_model("task", LLMProfile(
        "test", "secret", "test", "https://offline.invalid/v1", max_tokens=20))
    source = AXObservationSource(frame(), "window-7")
    model = ctx.runtime.model
    assert model is not None
    try:
        snapshots = [await source.observe("window-7", ctx) for _ in range(2)]
        for snapshot in snapshots:
            assert await model.complete([{"role": "user", "content": snapshot_text(snapshot)}]) == "ready"
        assert len(requests) == 2 and ctx.budget.total_tokens == 20
        for body, snapshot in zip(requests, snapshots, strict=True):
            assert body["messages"] == [{"role": "user", "content": snapshot_text(snapshot)}]
            assert "image_url" not in json.dumps(body)
            assert "data:image" not in json.dumps(body)
            assert "native" not in json.dumps(body)
        assert snapshots[0].observation_id not in json.dumps(requests[1])
    finally:
        await ctx.runtime.aclose()


@pytest.mark.parametrize("case", ["quota", "revoked_after_read", "incomplete"])
async def test_ax_controller_uses_governed_read_boundary(monkeypatch, case: str) -> None:
    from agent_computer_use.factory import UnavailableChannel
    from agent_computer_use.controller import ComputerUseController
    from agent_computer_use.observation import AXObservationSource
    from tank_backend.agents.subagent import SubAgentRequest

    ctx = context()
    calls = []

    def native(*args):
        calls.append(True)
        if case == "revoked_after_read":
            ctx.authorization.revoke()
        return [candidate(object(), "Save")], case == "incomplete"

    monkeypatch.setattr("agent_computer_use.observation.ax_window_candidates", native)
    if case == "quota":
        ctx.runtime.restrict_operations(observations=0)
    source = AXObservationSource(frame(), "window-7")
    controller = ComputerUseController(source, UnavailableChannel())
    result = await controller.run(SubAgentRequest("Save", "", "task", goal().model_dump(mode="json")), ctx)
    assert result.status == "stopped"
    assert not result.details["receipts"]
    assert len(calls) == (0 if case == "quota" else 1)
    if case == "incomplete":
        assert result.reason == "scope_incomplete"
    await ctx.runtime.aclose()
    await source.aclose()
