"""Offline semantic fixtures: no desktop access or model requests."""

import asyncio
from dataclasses import replace

import pytest
from agent_computer_use.action_builder import ActionBuilder
from agent_computer_use.contracts import (
    AdvisorResult,
    DecisionResult,
    DispatchReceipt,
    Element,
    Fact,
    GoalContract,
    Snapshot,
)
from agent_computer_use.controller import ComputerUseController

from tank_backend.agents.subagent import (
    SubAgentAuthorization,
    SubAgentBudget,
    SubAgentCancelled,
    SubAgentContext,
    SubAgentRequest,
)


def export_goal() -> GoalContract:
    return GoalContract.from_input(
        {
            "schema_version": 1,
            "objective": "Export this document as PDF without overwriting",
            "scope": "document",
            "inputs": [{"key": "filename", "value": "报告.pdf"}],
            "milestones": [
                {
                    "id": "name",
                    "operation": "fill",
                    "role": "textbox",
                    "label": "File name",
                    "input_key": "filename",
                    "postcondition": {"key": "filename", "value": "报告.pdf"},
                }
            ],
            "completion": [{"key": "new_pdf", "value": "verified"}],
        }
    )


def test_known_input_builds_a_complete_bound_action() -> None:
    goal = export_goal()
    snapshot = Snapshot(
        "obs-1",
        "document",
        1,
        (
            Element("field-7", "textbox", "File name", ("fill",)),
            Element("field-8", "textbox", "Directory", ("fill",)),
        ),
    )
    actions = ActionBuilder().build("goal-1", 1, goal, goal.milestones[0], snapshot)
    assert actions.reason == "rules_unique"
    assert len(actions.actions) == 1
    action = actions.actions[0]
    assert (action.target_ref, action.operation, action.value) == ("field-7", "fill", "报告.pdf")
    assert actions.binding.observation_id == "obs-1"
    assert actions.binding.goal_id == "goal-1"
    assert actions.binding.generation == 1


@pytest.mark.parametrize(
    "case,reason",
    [
        ("duplicate", "ambiguous_target"),
        ("truncated", "scope_incomplete"),
        ("missing_input", "missing_parameters"),
        ("scope", "scope_mismatch"),
        ("ocr", "no_viable_actions"),
        ("disabled", "no_viable_actions"),
        ("loading", "observation_unavailable"),
    ],
)
def test_ineligible_evidence_produces_no_executable_candidates(case: str, reason: str) -> None:
    goal = export_goal()
    field = Element("field", "textbox", "File name", ("fill",))
    snapshot = Snapshot("obs", "document", 1, (field,))
    if case == "duplicate":
        snapshot = replace(snapshot, elements=(field, replace(field, ref="other")))
    elif case == "truncated":
        snapshot = replace(snapshot, complete=False)
    elif case == "missing_input":
        goal = goal.model_copy(update={"inputs": ()})
    elif case == "scope":
        snapshot = replace(snapshot, scope="other-window")
    elif case == "ocr":
        snapshot = replace(snapshot, elements=(replace(field, kind="text_region"),))
    elif case == "disabled":
        snapshot = replace(snapshot, elements=(replace(field, enabled=False),))
    else:
        snapshot = replace(snapshot, ready=False)
    actions = ActionBuilder().build("goal", 1, goal, goal.milestones[0], snapshot)
    assert actions.reason == reason
    assert actions.actions == ()


def context() -> SubAgentContext:
    return SubAgentContext(
        SubAgentAuthorization(frozenset({"desktop"})), SubAgentBudget(), asyncio.Event()
    )


class ExportWorld:
    """Each input changes the semantic state; observations themselves do not."""

    def __init__(self) -> None:
        self.dispatched = []
        self.closed = False
        self.observations = 0

    async def observe(self, scope, ctx):
        self.observations += 1
        return Snapshot(
            f"obs-{self.observations}",
            scope,
            len(self.dispatched),
            (Element("field", "textbox", "File name", ("fill",)),),
            facts=(Fact(key="filename", value="报告.pdf"), Fact(key="new_pdf", value="verified"))
            if self.dispatched
            else (),
        )

    async def is_current(self, binding, action, ctx):
        return binding.generation == len(self.dispatched)

    async def dispatch(self, binding, action, ctx):
        ctx.check("desktop")
        self.dispatched.append(action)
        return DispatchReceipt(action.id, "sent")

    async def aclose(self):
        self.closed = True


async def test_host_verifies_known_goal_with_no_models() -> None:
    world = ExportWorld()
    controller = ComputerUseController(world, world)
    ctx = context()
    result = await controller.run(
        SubAgentRequest(
            "Export PDF", "Do not overwrite", "task", export_goal().model_dump(mode="json")
        ),
        ctx,
    )
    assert result.status == "completed"
    assert result.details["milestones"] == ["name"]
    assert len(world.dispatched) == 1
    assert world.dispatched[0].value == "报告.pdf"
    assert world.observations == 2
    assert [record.operation for record in ctx.runtime.records] == [
        "computer_use.observe", "computer_use.dispatch", "computer_use.observe",
    ]
    assert all(record.task_id == "task" for record in ctx.runtime.records)


class PickFirst:
    def __init__(self):
        self.calls = 0

    async def choose(self, goal, snapshot, actions, ctx):
        self.calls += 1
        return DecisionResult(actions.binding, "candidate", actions.actions[0].id)


class SupplyFilename:
    def __init__(self):
        self.calls = 0
        self.request: SubAgentRequest | None = None

    async def assist(self, request, goal, snapshot, actions, ctx):
        self.calls += 1
        self.request = request
        return AdvisorResult(
            actions.binding, "inputs", inputs=(Fact(key="filename", value="报告.pdf"),)
        )


async def test_advisor_fills_one_gap_then_returns_to_rules() -> None:
    world, advisor = ExportWorld(), SupplyFilename()
    goal = export_goal().model_dump(mode="json")
    goal["inputs"] = []
    result = await ComputerUseController(world, world, advisor=advisor).run(
        SubAgentRequest("Export PDF", "Never overwrite", "task", goal),
        context(),
    )
    assert result.status == "completed"
    assert advisor.calls == 1
    assert advisor.request is not None
    assert advisor.request.context == "Never overwrite"
    assert result.details["goal_version"] == 2
    assert len(world.dispatched) == 1


async def test_multistep_semantic_selection_needs_no_advisor() -> None:
    class World(ExportWorld):
        async def observe(self, scope, ctx):
            self.observations += 1
            count = len(self.dispatched)
            return Snapshot(
                f"obs-{self.observations}",
                scope,
                count,
                (
                    Element(f"field-{count}", "textbox", "Output filename", ("fill",)),
                    Element(f"folder-{count}", "textbox", "Output folder", ("fill",)),
                ),
                facts=tuple(Fact(key=f"step-{i}", value="done") for i in range(count)),
            )

    world, selector = World(), PickFirst()
    goal = export_goal().model_dump(mode="json")
    goal["milestones"] = [
        dict(
            goal["milestones"][0],
            id=f"step-{i}",
            postcondition={"key": f"step-{i}", "value": "done"},
        )
        for i in range(3)
    ]
    goal["completion"] = [{"key": "step-2", "value": "done"}]
    result = await ComputerUseController(world, world, selector=selector).run(
        SubAgentRequest("Export PDF", "", "task", goal),
        context(),
    )
    assert result.status == "completed"
    assert selector.calls == len(world.dispatched) == 3


@pytest.mark.parametrize("failure", ["cancel", "revoke", "budget", "timeout", "stale"])
async def test_final_gate_prevents_dispatch_after_async_preflight(failure: str) -> None:
    ctx = context()

    class World(ExportWorld):
        async def is_current(self, binding, action, ctx):
            if failure == "cancel":
                ctx.cancel.set()
            elif failure == "revoke":
                ctx.authorization.revoke()
            elif failure == "budget":
                ctx.budget.limit = 1
                ctx.budget.record("shared", 1, 0)
            elif failure == "timeout":
                await asyncio.sleep(0.01)
            return failure != "stale"

    if failure == "timeout":
        import time

        ctx = replace(ctx, deadline=time.monotonic() + 0.005)
    world = World()
    controller = ComputerUseController(world, world)
    request = SubAgentRequest("Export", "", "task", export_goal().model_dump(mode="json"))
    if failure == "cancel":
        with pytest.raises(SubAgentCancelled) as stopped:
            await controller.run(request, ctx)
        assert stopped.value.task_result is not None
        assert stopped.value.task_result.status == "stopped"
    else:
        result = await controller.run(request, ctx)
        assert result.status == "stopped"
    assert world.dispatched == []


@pytest.mark.parametrize(
    "failure", ["lost_reply", "wrong_receipt", "unknown", "cancel", "not_sent"]
)
async def test_dispatch_uncertainty_is_preserved_without_replay(failure: str) -> None:
    class World(ExportWorld):
        async def dispatch(self, binding, action, ctx):
            if failure == "not_sent":
                return DispatchReceipt(action.id, "not_sent")
            self.dispatched.append(action)
            if failure == "lost_reply":
                raise OSError("lost native reply")
            if failure == "cancel":
                raise asyncio.CancelledError()
            return DispatchReceipt("wrong" if failure == "wrong_receipt" else action.id, "unknown")

        async def observe(self, scope, ctx):
            self.observations += 1
            return Snapshot(
                str(self.observations),
                scope,
                len(self.dispatched),
                (Element("field", "textbox", "File name", ("fill",)),),
            )

    world = World()
    controller = ComputerUseController(world, world)
    request = SubAgentRequest("Export", "", "task", export_goal().model_dump(mode="json"))
    if failure == "cancel":
        with pytest.raises(SubAgentCancelled) as stopped:
            await controller.run(request, context())
        result = stopped.value.task_result
    else:
        result = await controller.run(request, context())
    assert result is not None
    assert result.status == ("stopped" if failure == "not_sent" else "unknown")
    assert len(world.dispatched) == (0 if failure == "not_sent" else 1)
    assert isinstance(result.details["receipts"], list)
    assert len(result.details["receipts"]) == 1


@pytest.mark.parametrize("change", ["scope", "generation", "observation", "goal", "candidate_set"])
async def test_stale_selector_reply_never_dispatches(change: str) -> None:
    class Selector(PickFirst):
        async def choose(self, goal, snapshot, actions, ctx):
            field = {
                "scope": "scope",
                "generation": "generation",
                "observation": "observation_id",
                "goal": "goal_version",
                "candidate_set": "candidate_set_id",
            }[change]
            value = 99 if field in {"generation", "goal_version"} else "stale"
            return DecisionResult(
                replace(actions.binding, **{field: value}), "candidate", actions.actions[0].id
            )

    class World(ExportWorld):
        async def observe(self, scope, ctx):
            snap = await super().observe(scope, ctx)
            return replace(snap, elements=(replace(snap.elements[0], label="PDF name"),))

    world = World()
    result = await ComputerUseController(world, world, selector=Selector()).run(
        SubAgentRequest("Export", "", "task", export_goal().model_dump(mode="json")),
        context(),
    )
    assert result.reason == "stale_decision"
    assert not world.dispatched


async def test_wrong_scope_cannot_supply_completion_evidence() -> None:
    class World(ExportWorld):
        async def observe(self, scope, ctx):
            return Snapshot(
                "other",
                "another-document",
                1,
                facts=(
                    Fact(key="filename", value="报告.pdf"),
                    Fact(key="new_pdf", value="verified"),
                ),
            )

    world = World()
    result = await ComputerUseController(world, world).run(
        SubAgentRequest("Export", "", "task", export_goal().model_dump(mode="json")),
        context(),
    )
    assert result.status == "stopped"
    assert result.reason == "scope_mismatch"


async def test_advisor_reobservation_is_bounded() -> None:
    class Advisor(SupplyFilename):
        async def assist(self, request, goal, snapshot, actions, ctx):
            self.calls += 1
            return AdvisorResult(actions.binding, "need_observation")

    advisor, world = Advisor(), ExportWorld()
    goal = export_goal().model_dump(mode="json")
    goal["inputs"] = []
    result = await ComputerUseController(world, world, advisor=advisor).run(
        SubAgentRequest("Export", "", "task", goal),
        context(),
    )
    assert result.reason == "advisor_limit"
    assert advisor.calls == 4
    assert not world.dispatched


async def test_reobservation_does_not_repeat_same_abstained_selection() -> None:
    class Selector(PickFirst):
        async def choose(self, goal, snapshot, actions, ctx):
            self.calls += 1
            return DecisionResult(actions.binding, "none")

    class Advisor(SupplyFilename):
        async def assist(self, request, goal, snapshot, actions, ctx):
            return AdvisorResult(actions.binding, "need_observation")

    class World(ExportWorld):
        async def observe(self, scope, ctx):
            snapshot = await super().observe(scope, ctx)
            return replace(snapshot, elements=(replace(snapshot.elements[0], label="PDF name"),))

    selector, world = Selector(), World()
    result = await ComputerUseController(world, world, selector=selector, advisor=Advisor()).run(
        SubAgentRequest("Export", "", "task", export_goal().model_dump(mode="json")),
        context(),
    )
    assert result.reason == "advisor_limit"
    assert selector.calls == 1
    assert not world.dispatched


@pytest.mark.parametrize("patch", ["replace_input", "new_input", "stale", "weaken_goal"])
async def test_advice_cannot_replace_authorized_inputs_or_completion(patch: str) -> None:
    class Advisor(SupplyFilename):
        async def assist(self, request, goal, snapshot, actions, ctx):
            binding = actions.binding
            if patch == "stale":
                binding = replace(binding, goal_version=0)
            return AdvisorResult(
                binding,
                "inputs",
                inputs=(
                    Fact(
                        key="filename" if patch in {"replace_input", "stale"} else patch,
                        value="changed",
                    ),
                ),
            )

    class World(ExportWorld):
        async def observe(self, scope, ctx):
            return replace(await super().observe(scope, ctx), elements=())

    world = World()
    result = await ComputerUseController(world, world, advisor=Advisor()).run(
        SubAgentRequest("Export", "", "task", export_goal().model_dump(mode="json")),
        context(),
    )
    assert result.reason == ("stale_advice" if patch == "stale" else "invalid_goal_patch")
    assert not world.dispatched


@pytest.mark.parametrize(
    "invalid",
    [
        {"schema_version": True},
        {"schema_version": 2},
        {"scope": ""},
        {"milestones": []},
        {"completion": []},
        {"permissions": ["filesystem"]},
    ],
)
async def test_invalid_domain_contract_has_zero_observations(invalid) -> None:
    goal = {**export_goal().model_dump(mode="json"), **invalid}
    world = ExportWorld()
    result = await ComputerUseController(world, world).run(
        SubAgentRequest("Export", "", "task", goal),
        context(),
    )
    assert result.status == "needs_input"
    assert result.reason == "invalid_goal_contract"
    assert world.observations == 0


async def test_later_failure_retains_verified_milestone() -> None:
    goal = export_goal().model_dump(mode="json")
    goal["milestones"].append(
        {
            "id": "save",
            "operation": "click",
            "role": "button",
            "label": "Save",
            "postcondition": {"key": "saved", "value": "yes"},
        }
    )
    world = ExportWorld()
    result = await ComputerUseController(world, world).run(
        SubAgentRequest("Export", "", "task", goal),
        context(),
    )
    assert result.status == "partial"
    assert result.details["milestones"] == ["name"]
    assert len(world.dispatched) == 1


async def test_delayed_effect_is_reconciled_with_reads_only() -> None:
    class World(ExportWorld):
        async def observe(self, scope, ctx):
            snapshot = await super().observe(scope, ctx)
            return replace(snapshot, facts=()) if self.observations == 2 else snapshot

    world = World()
    result = await ComputerUseController(world, world).run(
        SubAgentRequest("Export", "", "task", export_goal().model_dump(mode="json")),
        context(),
    )
    assert result.status == "completed"
    assert len(world.dispatched) == 1 and world.observations == 3


def test_semantic_shortlist_cannot_hide_duplicate_labels() -> None:
    goal = export_goal()
    snapshot = Snapshot(
        "obs",
        "document",
        1,
        (
            Element("one", "textbox", "PDF name", ("fill",)),
            Element("two", "textbox", "PDF name", ("fill",)),
        ),
    )
    actions = ActionBuilder().build("goal", 1, goal, goal.milestones[0], snapshot)
    assert actions.reason == "ambiguous_target" and not actions.actions


async def test_result_binds_receipts_and_verification_to_observations() -> None:
    world = ExportWorld()
    result = await ComputerUseController(world, world).run(
        SubAgentRequest("Export", "", "worker-id", export_goal().model_dump(mode="json")),
        context(),
    )
    assert result.details["task_id"] == "worker-id"
    receipts = result.details["receipts"]
    assert isinstance(receipts, list) and isinstance(receipts[0], dict)
    assert receipts[0]["observation_id"] == "obs-1"
    assert receipts[0]["goal_version"] == 1
    evidence = result.details["evidence"]
    assert isinstance(evidence, list) and isinstance(evidence[0], dict)
    assert evidence[0]["observation_id"] == "obs-2"
    assert evidence[0]["milestone"] == "name"


def test_shortlist_checks_whole_scope_before_limiting() -> None:
    goal = export_goal()
    elements = tuple(Element(f"field-{i}", "textbox", f"Name {i:02}", ("fill",))
                     for i in range(40))
    snapshot = Snapshot("obs", "document", 1, elements)
    actions = ActionBuilder().build("goal", 1, goal, goal.milestones[0], snapshot)
    assert actions.reason == "jev_eligible"
    assert len(actions.actions) == 32
    assert actions.total_candidates == 40 and actions.truncated
    duplicate = replace(elements[-1], ref="duplicate", label=elements[0].label)
    rejected = ActionBuilder().build("goal", 1, goal, goal.milestones[0],
                                    replace(snapshot, elements=(*elements, duplicate)))
    assert rejected.reason == "ambiguous_target" and not rejected.actions
    exact = replace(elements[-1], label="File name")
    matched = ActionBuilder().build("goal", 1, goal, goal.milestones[0],
                                   replace(snapshot, elements=(*elements[:-1], exact)))
    assert matched.reason == "rules_unique"
    assert matched.actions[0].target_ref == exact.ref
    assert not matched.truncated
