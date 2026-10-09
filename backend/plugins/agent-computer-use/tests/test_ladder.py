"""Offline semantic fixtures: no desktop access or model requests."""

import asyncio
import json
from dataclasses import replace

import pytest
from pydantic import JsonValue
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
        {'schema_version': 2, 'objective': 'Export this document as PDF without overwriting', 'scope': 'document', 'inputs': [{'key': 'filename', 'value': '报告.pdf', 'purpose': 'filename', 'field_label': 'File name'}], 'completion': [{'key': 'status:new_pdf', 'value': 'verified'}], 'goal_id': 'goal', 'intent': 'Export this document as PDF without overwriting', 'authorization_ref': 'current_task', 'allowed_operations': ['click', 'fill']}
    )


def unbound_goal() -> GoalContract:
    goal = export_goal().model_dump(mode="json")
    goal["inputs"][0]["field_label"] = None
    return GoalContract.from_input(goal)


def profile_goal() -> dict[str, JsonValue]:
    return {
        "schema_version": 2, "goal_id": "profile-name",
        "intent": "把显示名称改为 Ada 并保存，其他资料不变",
        "objective": "Save the display name Ada", "scope": "profile",
        "authorization_ref": "task",
        "allowed_operations": ["click", "fill"],
        "constraints": ["Leave other profile fields unchanged"],
        "inputs": [{"key": "name", "purpose": "profile display name", "value": "Ada",
                    "field_scope": "Profile"}],
        "completion": [{"key": "status:Saved name", "value": "Ada"}],
    }


def test_only_goal_contract_accepts_outcomes_and_rejects_step_scripts() -> None:
    goal = GoalContract.from_input(profile_goal())
    assert goal.schema_version == 2
    assert goal.inputs[0].purpose == "profile display name"
    with pytest.raises(ValueError):
        GoalContract.from_input({**profile_goal(), "schema_version": 1})
    with pytest.raises(ValueError):
        GoalContract.from_input({**profile_goal(), "milestones": []})


def test_goal_v2_preserves_intent_without_an_operation_script() -> None:
    from agent_computer_use.contracts import GoalContract

    goal = GoalContract.from_input(profile_goal())
    assert isinstance(goal, GoalContract)
    assert goal.inputs[0].purpose == "profile display name"
    assert goal.inputs[0].value == "Ada"
    assert "milestones" not in goal.model_dump()
    assert isinstance(GoalContract.from_input(export_goal().model_dump(mode="json")), GoalContract)
    with pytest.raises(ValueError):
        GoalContract.from_input({**profile_goal(), "schema_version": 1})
    with pytest.raises(ValueError):
        GoalContract.from_input({**profile_goal(), "schema_version": True})


def test_goal_v2_does_not_require_a_page_specific_field_label_or_form_name() -> None:
    from agent_computer_use.contracts import GoalContract

    task = profile_goal()
    task["inputs"] = [{"key": "name", "purpose": "display name", "value": "Ada"}]
    goal = GoalContract.from_input(task)
    assert isinstance(goal, GoalContract)
    snapshot = Snapshot("obs", "profile", 1, (
        Element("field", "textbox", "Public alias", ("fill",), value="Bob"),))
    actions = ActionBuilder().build("goal", 1, goal, snapshot)
    assert [(a.target_ref, a.value) for a in actions.actions] == [("field", "Ada")]


async def test_goal_v2_checks_evidence_and_authorization_before_completion() -> None:
    class World(ExportWorld):
        async def observe(self, scope, ctx):
            self.observations += 1
            return Snapshot("initial", scope, 1,
                            facts=(Fact(key="status:Saved name", value="Ada"),))

    for authorization, status, reason in (
        ("task", "completed", "goal_verified"),
        ("current_task", "completed", "goal_verified"),
        ("other-task", "stopped", "authorization_mismatch"),
    ):
        world = World()
        result = await ComputerUseController(world, world).run(
            SubAgentRequest("Save name", "", "task",
                            {**profile_goal(), "authorization_ref": authorization}), context(),
        )
        assert (result.status, result.reason) == (status, reason)
        assert not world.dispatched
        assert world.observations == (0 if authorization == "other-task" else 1)


async def test_goal_v2_outcomes_cannot_be_ignored_by_completion() -> None:
    class World(ExportWorld):
        async def observe(self, scope, ctx):
            return Snapshot("initial", scope, 1,
                            facts=(Fact(key="status:Saved name", value="Ada"),))

    world = World()
    task = profile_goal()
    task["outcomes"] = [{"id": "preserve_email", "conditions": [
        {"key": "status:Email", "value": "unchanged@example.test"}]}]
    result = await ComputerUseController(world, world).run(
        SubAgentRequest("Save name", "", "task", task), context(),
    )
    assert (result.status, result.reason) == ("stopped", "no_viable_actions")
    assert not world.dispatched


async def test_goal_v2_preflight_rejection_has_no_pending_action() -> None:
    class World(ExportWorld):
        async def observe(self, scope, ctx):
            return Snapshot("initial", scope, 1, (
                Element("field", "textbox", "Name", ("fill",),
                        ancestors=(("form", "Profile"),)),))

        async def is_current(self, binding, action, ctx):
            return False

    world = World()
    result = await ComputerUseController(world, world, selector=PickFirst()).run(
        SubAgentRequest("Save name", "", "task", profile_goal()), context(),
    )
    assert result.reason == "stale_reference"
    progress = result.details["progress"]
    assert isinstance(progress, dict) and progress["pending_action"] is None
    assert not world.dispatched


def test_goal_candidates_mix_operations_and_bind_only_compatible_inputs() -> None:
    from agent_computer_use.contracts import GoalContract

    goal = GoalContract.from_input(profile_goal())
    assert isinstance(goal, GoalContract)
    snapshot = Snapshot("form", "profile", 1, (
        Element("name", "textbox", "Public name", ("fill",), value="Bob",
                ancestors=(("form", "Profile"),)),
        Element("email", "textbox", "Email", ("fill",), value="private@example.test",
                ancestors=(("form", "Notifications"),)),
        Element("back", "button", "Back", ("click",),
                click_effect=(Fact(key="region:Home", value="visible"),)),
        Element("save", "button", "Save", ("click",), enabled=False),
    ))
    actions = ActionBuilder().build("goal", 1, goal, snapshot)
    assert actions.reason == "jev_eligible"
    from agent_computer_use.model_view import candidate_aliases, decision_question

    question = json.loads(json.dumps(decision_question(goal, snapshot, actions)))
    assert question["state"]["recent_actions"] == []
    fill = next(a for a in actions.actions if a.operation == "fill")
    alias = next(key for key, action in candidate_aliases(actions).items() if action.id == fill.id)
    option = question["questions"]["next_action"]["criteria"][alias]
    assert option["label"] == "Public name"
    assert option["input_key"] == "name"
    assert option["current_value"] == "Bob"
    assert {(a.target_ref, a.operation, a.value) for a in actions.actions} == {
        ("name", "fill", "Ada"), ("back", "click", None),
    }
    snapshot = replace(snapshot, elements=(replace(snapshot.elements[0], value="Ada"),
                                           *snapshot.elements[1:]))
    assert [a.operation for a in ActionBuilder().build("goal", 1, goal, snapshot).actions
            ] == ["click"]


@pytest.mark.parametrize("save_effect", [
    "saved", "field_only", "lost_reply", "delayed_reply", "unknown", "not_sent",
])
async def test_goal_v2_selects_mixed_actions_and_verifies_save_separately(save_effect: str) -> None:
    class World(ExportWorld):
        async def observe(self, scope, ctx):
            self.observations += 1
            filled = any(a.operation == "fill" for a in self.dispatched)
            saved = any(a.target_ref == "save" for a in self.dispatched)
            return Snapshot(str(self.observations), scope, self.observations, (
                Element("name", "textbox", "Public name", ("fill",),
                        value="Ada" if filled else "Bob", ancestors=(("form", "Profile"),)),
                Element("back", "button", "Back", ("click",),
                        click_effect=(Fact(key="region:Home", value="visible"),)),
                Element("save", "button", "Save", ("click",), enabled=filled, submits=True),
            ), facts=(Fact(key="status:Saved name", value="Ada"),)
                if saved and (save_effect in {"saved", "lost_reply"}
                              or save_effect == "delayed_reply" and self.observations >= 5)
                else ())

        async def is_current(self, binding, action, ctx):
            return binding.generation == self.observations

        async def dispatch(self, binding, action, ctx):
            self.dispatched.append(action)
            return DispatchReceipt(action.id, "not_sent" if save_effect == "not_sent" else
                                   "unknown" if save_effect in {
                                       "lost_reply", "delayed_reply", "unknown"} else "sent")

    class Select:
        async def choose(self, goal, snapshot, actions, ctx):
            target = "name" if not world.dispatched else "save"
            if not world.dispatched:
                assert {a.operation for a in actions.actions} == {"click", "fill"}
            else:
                assert actions.progress is not None
                previous = actions.progress.recent_steps[-1]
                assert (previous.label, previous.operation, previous.selected_by) == (
                    "Public name", "fill", "selector")
                expected_dispatch = "unknown" if save_effect in {"lost_reply", "delayed_reply", "unknown"} else "sent"
                assert (previous.dispatch_status, previous.effect_status) == (expected_dispatch, "verified")
                assert [(change.key, change.before, change.after) for change in previous.changes] == [
                    ("target_value", "Bob", "Ada")]
                from agent_computer_use.model_view import decision_question
                view = decision_question(goal, snapshot, actions)["state"]
                assert isinstance(view, dict)
                assert "verified_actions" not in view["progress"]
                assert view["progress"]["verified_action_count"] == 1
                history = view["recent_actions"]
                assert history[-1]["label"] == "Public name"
                assert history[-1]["effect_status"] == "verified"
                assert "action_id" not in history[-1] and "observation_before" not in history[-1]
            return DecisionResult(actions.binding, "candidate",
                                  next(a.id for a in actions.actions if a.target_ref == target))

    world = World()
    result = await ComputerUseController(world, world, selector=Select()).run(
        SubAgentRequest("Save name", "", "task", profile_goal()), context(),
    )
    progress = result.details["progress"]
    assert isinstance(progress, dict)
    verified = progress["verified_actions"]
    assert isinstance(verified, list)
    if save_effect == "not_sent":
        assert (result.status, result.reason) == ("stopped", "not_sent")
        assert len(world.dispatched) == 1
    elif save_effect in {"field_only", "unknown"}:
        assert (result.status, result.reason) == ("unknown", "effect_unknown")
        assert [a.target_ref for a in world.dispatched] == ["name", "save"]
        assert len(verified) == 1
        assert world.observations == 5
        assert progress["pending_action"] is not None
    else:
        assert (result.status, result.reason) == ("completed", "goal_verified")
        assert [a.target_ref for a in world.dispatched] == ["name", "save"]
        assert len(verified) == 2
        assert progress["pending_action"] is None
        assert world.observations == (5 if save_effect == "delayed_reply" else 3)


@pytest.mark.parametrize("stale", [False, True])
async def test_goal_v2_stops_repeated_states_and_stale_decisions(stale: bool) -> None:
    class World(ExportWorld):
        async def observe(self, scope, ctx):
            self.observations += 1
            current, target = ("Home", "Profile") if len(self.dispatched) % 2 == 0 else (
                "Profile", "Home")
            return Snapshot(str(self.observations), scope, self.observations, (
                Element(f"new-ref-{self.observations}", "button", target, ("click",),
                        click_effect=(Fact(key="status:Page", value=target),)),
            ), facts=(Fact(key="status:Page", value=current),))

        async def is_current(self, binding, action, ctx):
            return binding.generation == self.observations

    class Select:
        async def choose(self, goal, snapshot, actions, ctx):
            binding = replace(actions.binding, generation=0) if stale else actions.binding
            return DecisionResult(binding, "candidate", actions.actions[0].id)

    world = World()
    result = await ComputerUseController(world, world, selector=Select()).run(
        SubAgentRequest("Save name", "", "task", profile_goal()), context(),
    )
    assert result.reason == ("stale_decision" if stale else "no_progress")
    assert len(world.dispatched) == (0 if stale else 2)
    assert world.observations == (1 if stale else 3)
    progress = result.details["progress"]
    assert isinstance(progress, dict)
    assert progress["no_progress"] == (0 if stale else 1)
    assert progress["pending_action"] is None


@pytest.mark.parametrize("form,label", [("Notifications", "Subscribe"), ("Profile", "Delete profile")])
async def test_satisfied_input_does_not_authorize_a_unique_submit(form: str, label: str) -> None:
    class World(ExportWorld):
        async def observe(self, scope, ctx):
            self.observations += 1
            return Snapshot(str(self.observations), scope, self.observations, (
                Element("name", "textbox", "Name", ("fill",), value="Ada",
                        ancestors=(("form", "Profile"),)),
                Element("submit", "button", label, ("click",), submits=True,
                        ancestors=(("form", form),)),
            ))

        async def is_current(self, binding, action, ctx):
            return True

    world = World()
    result = await ComputerUseController(world, world).run(
        SubAgentRequest("Save name", "", "task", profile_goal()), context(),
    )
    assert not world.dispatched
    assert (result.status, result.reason) == ("stopped", "jev_eligible")


def test_goal_builder_never_offers_premature_submit_or_truncated_candidates() -> None:
    from agent_computer_use.contracts import GoalContract

    goal = GoalContract.from_input(profile_goal())
    assert isinstance(goal, GoalContract)
    form = (Element("field", "textbox", "Name", ("fill",), value="Bob",
                    ancestors=(("form", "Profile"),)),
            Element("save", "button", "Save", ("click",), submits=True,
                    ancestors=(("form", "Profile"),)))
    snapshot = Snapshot("obs", "profile", 1, form)
    actions = ActionBuilder().build("goal", 1, goal, snapshot)
    assert {a.operation for a in actions.actions} == {"fill"}
    crowded = replace(snapshot, elements=tuple(replace(form[0], ref=str(i)) for i in range(33)))
    actions = ActionBuilder().build("goal", 1, goal, crowded)
    assert actions.truncated and actions.actions == ()


def test_goal_candidates_reject_incompatible_fields_and_indistinguishable_targets() -> None:
    from agent_computer_use.contracts import GoalContract

    goal = GoalContract.from_input(profile_goal())
    assert isinstance(goal, GoalContract)
    field = Element("field", "textbox", "Name", ("fill",),
                    ancestors=(("form", "Profile"),))
    snapshot = Snapshot("obs", "profile", 1, (replace(field, input_type="password"),))
    assert ActionBuilder().build("goal", 1, goal, snapshot).actions == ()
    duplicate = replace(snapshot, elements=(field, replace(field, ref="other")))
    actions = ActionBuilder().build("goal", 1, goal, duplicate)
    assert actions.reason == "ambiguous_target" and actions.actions == ()


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
    actions = ActionBuilder().build("goal-1", 1, goal, snapshot)
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
        goal = goal.model_copy(update={"inputs": (goal.inputs[0].model_copy(update={"value": None}),)})
    elif case == "scope":
        snapshot = replace(snapshot, scope="other-window")
    elif case == "ocr":
        snapshot = replace(snapshot, elements=(replace(field, kind="text_region"),))
    elif case == "disabled":
        snapshot = replace(snapshot, elements=(replace(field, enabled=False),))
    else:
        snapshot = replace(snapshot, ready=False)
    actions = ActionBuilder().build("goal", 1, goal, snapshot)
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
            (Element("field", "textbox", "File name", ("fill",),
                     value="报告.pdf" if self.dispatched else ""),),
            facts=(Fact(key="filename", value="报告.pdf"), Fact(key="status:new_pdf", value="verified"))
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
    evidence = result.details["evidence"]
    assert isinstance(evidence, list) and evidence
    assert len(world.dispatched) == 1
    assert world.dispatched[0].value == "报告.pdf"
    assert world.observations == 2
    assert [record.operation for record in ctx.runtime.records] == [
        "computer_use.observe", "computer_use.dispatch", "computer_use.observe",
    ]
    step = controller.progress.recent_steps[0]
    assert (step.selected_by, step.label, step.value, step.effect_status) == (
        "rules", "File name", "报告.pdf", "verified")
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
    goal["inputs"][0]["value"] = None
    goal["inputs"][0]["source"] = "generated"
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


@pytest.mark.parametrize("count", [3, 5])
async def test_multistep_semantic_selection_needs_no_advisor(count) -> None:
    class World(ExportWorld):
        async def observe(self, scope, ctx):
            self.observations += 1
            values = {a.target_ref: a.value for a in self.dispatched}
            return Snapshot(str(self.observations), scope, len(self.dispatched), tuple(
                Element(f"field-{i}", "textbox", "Value", ("fill",),
                        value=values.get(f"field-{i}", ""), ancestors=(("section", str(i)),))
                for i in range(count)),
                facts=(Fact(key="status:done", value="yes"),) if len(values) == count else ())

    world, selector = World(), PickFirst()
    goal = export_goal().model_dump(mode="json")
    goal["inputs"] = [{"key": str(i), "purpose": f"value {i}", "field_scope": str(i),
                       "value": f"value-{i}"} for i in range(count)]
    goal["completion"] = [{"key": "status:done", "value": "yes"}]
    result = await ComputerUseController(world, world, selector=selector).run(
        SubAgentRequest("Fill values", "", "task", goal), context())
    assert result.status == "completed"
    assert selector.calls == len(world.dispatched) == count
    assert {a.target_ref: a.value for a in world.dispatched} == {
        f"field-{i}": f"value-{i}" for i in range(count)}


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
                (Element("field", "textbox", "File name", ("fill",),
                     value=""),),
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
    step = controller.progress.recent_steps[-1]
    expected = "not_sent" if failure == "not_sent" else "unknown"
    assert step.dispatch_status == step.effect_status == expected
    assert step.changes == ()
    assert step.observation_before == "1"


@pytest.mark.parametrize("failure", ["error", "cancel", "incomplete", "stale"])
async def test_history_preserves_sent_action_when_followup_observation_fails(failure):
    class World(ExportWorld):
        async def observe(self, scope, ctx):
            if self.dispatched:
                if failure == "error":
                    raise OSError("Read failed after input")
                if failure == "cancel":
                    raise asyncio.CancelledError()
                if failure == "stale":
                    return replace(await super().observe(scope, ctx), observation_id="obs-1")
                return replace(await super().observe(scope, ctx), complete=False)
            return await super().observe(scope, ctx)
    world = World()
    controller = ComputerUseController(world, world)
    request = SubAgentRequest("Export", "", "task", export_goal().model_dump(mode="json"))
    if failure == "cancel":
        with pytest.raises(SubAgentCancelled) as stopped:
            await controller.run(request, context())
        result = stopped.value.task_result
    else:
        result = await controller.run(request, context())
    assert result is not None and result.status == "unknown"
    assert len(world.dispatched) == 1
    step = controller.progress.recent_steps[-1]
    assert step.dispatch_status == "sent" and step.effect_status == "unknown"
    assert step.changes == ()


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
        SubAgentRequest("Export", "", "task", unbound_goal().model_dump(mode="json")),
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
                    Fact(key="status:new_pdf", value="verified"),
                ),
            )

    world = World()
    result = await ComputerUseController(world, world).run(
        SubAgentRequest("Export", "", "task", export_goal().model_dump(mode="json")),
        context(),
    )
    assert result.status == "stopped"
    assert result.reason == "scope_mismatch"


@pytest.mark.parametrize("unavailable", ["ready", "complete"])
async def test_advisor_can_reobserve_when_evidence_becomes_available(unavailable: str) -> None:
    class World(ExportWorld):
        async def observe(self, scope, ctx):
            snapshot = await super().observe(scope, ctx)
            return replace(snapshot, **{unavailable: False}) if self.observations == 1 else snapshot

    class Advisor:
        async def assist(self, request, goal, snapshot, actions, ctx):
            return AdvisorResult(actions.binding, "need_observation")

    world = World()
    result = await ComputerUseController(world, world, advisor=Advisor()).run(
        SubAgentRequest("Export", "", "task", export_goal().model_dump(mode="json")), context(),
    )
    assert result.status == "completed"
    assert len(world.dispatched) == 1
    assert world.observations == 3


async def test_advisor_reobservation_is_bounded() -> None:
    class Advisor(SupplyFilename):
        async def assist(self, request, goal, snapshot, actions, ctx):
            self.calls += 1
            return AdvisorResult(actions.binding, "need_observation")

    advisor, world = Advisor(), ExportWorld()
    goal = export_goal().model_dump(mode="json")
    goal["inputs"][0]["value"] = None
    goal["inputs"][0]["source"] = "generated"
    result = await ComputerUseController(world, world, advisor=advisor).run(
        SubAgentRequest("Export", "", "task", goal),
        context(),
    )
    assert result.reason == "no_progress"
    assert advisor.calls == 1
    assert not world.dispatched


async def test_reobservation_does_not_repeat_same_abstained_selection() -> None:
    class Selector(PickFirst):
        async def choose(self, goal, snapshot, actions, ctx):
            self.calls += 1
            return DecisionResult(actions.binding, "need_more_context")

    class Advisor(SupplyFilename):
        async def assist(self, request, goal, snapshot, actions, ctx):
            return AdvisorResult(actions.binding, "need_observation")

    class World(ExportWorld):
        async def observe(self, scope, ctx):
            snapshot = await super().observe(scope, ctx)
            return replace(snapshot, elements=(replace(snapshot.elements[0], label="PDF name"),))

    selector, world = Selector(), World()
    result = await ComputerUseController(world, world, selector=selector, advisor=Advisor()).run(
        SubAgentRequest("Export", "", "task", unbound_goal().model_dump(mode="json")),
        context(),
    )
    assert result.reason == "no_progress"
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
        {"schema_version": 1},
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


async def test_later_failure_retains_verified_action() -> None:
    goal = export_goal().model_dump(mode="json")
    goal["completion"] = [{"key": "status:saved", "value": "yes"}]
    world = ExportWorld()
    result = await ComputerUseController(world, world).run(
        SubAgentRequest("Export", "", "task", goal),
        context(),
    )
    assert result.status == "partial"
    evidence = result.details["evidence"]
    assert isinstance(evidence, list) and evidence
    assert len(world.dispatched) == 1


async def test_delayed_effect_is_reconciled_with_reads_only() -> None:
    class World(ExportWorld):
        async def observe(self, scope, ctx):
            snapshot = await super().observe(scope, ctx)
            return replace(snapshot, facts=(), elements=(replace(snapshot.elements[0], value=""),)) if self.observations == 2 else snapshot

    world = World()
    result = await ComputerUseController(world, world).run(
        SubAgentRequest("Export", "", "task", export_goal().model_dump(mode="json")),
        context(),
    )
    assert result.status == "completed"
    assert len(world.dispatched) == 1 and world.observations == 3


def test_semantic_shortlist_cannot_hide_duplicate_labels() -> None:
    goal = unbound_goal()
    snapshot = Snapshot(
        "obs",
        "document",
        1,
        (
            Element("one", "textbox", "PDF name", ("fill",)),
            Element("two", "textbox", "PDF name", ("fill",)),
        ),
    )
    actions = ActionBuilder().build("goal", 1, goal, snapshot)
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
    assert evidence[0]["action_id"] == receipts[0]["action_id"]


def test_shortlist_checks_whole_scope_before_limiting() -> None:
    goal = unbound_goal()
    elements = tuple(Element(f"field-{i}", "textbox", f"Name {i:02}", ("fill",))
                     for i in range(40))
    snapshot = Snapshot("obs", "document", 1, elements)
    actions = ActionBuilder().build("goal", 1, goal, snapshot)
    assert actions.reason == "candidate_limit"
    assert actions.actions == ()
    assert actions.total_candidates == 40 and actions.truncated
    duplicate = replace(elements[-1], ref="duplicate", label=elements[0].label)
    rejected = ActionBuilder().build("goal", 1, goal,
                                    replace(snapshot, elements=(*elements, duplicate)))
    assert rejected.reason == "candidate_limit" and not rejected.actions
    exact = replace(elements[-1], label="File name")
    goal = goal.model_copy(update={"inputs": (goal.inputs[0].model_copy(update={"field_label": "File name"}),)})
    matched = ActionBuilder().build("goal", 1, goal,
                                   replace(snapshot, elements=(*elements[:-1], exact)))
    assert matched.reason == "rules_unique"
    assert matched.actions[0].target_ref == exact.ref
    assert not matched.truncated


class WanderingWorld:
    """Every click changes a readout, but only Finish establishes the requested result."""
    def __init__(self):
        self.dispatched = []
        self.observations = 0
        self.value = "0"

    async def observe(self, scope, ctx):
        from agent_computer_use.contracts import ValueChange
        self.observations += 1
        changes = (ValueChange("status:result", "readout", self.value),)
        return Snapshot(str(self.observations), scope, len(self.dispatched), (
            Element("wander", "button", "Change", ("click",), click_changes=changes),
            Element("repair", "button", "Prepare", ("click",), click_changes=changes),
            Element("finish", "button", "Finish", ("click",), click_changes=changes),
            Element("readout", "text", "Result", (), value=self.value),
        ), facts=(Fact(key="status:result", value=self.value),))

    async def is_current(self, binding, action, ctx):
        return binding.generation == len(self.dispatched)

    async def dispatch(self, binding, action, ctx):
        self.dispatched.append(action.target_ref)
        self.value = ("done" if action.target_ref == "finish" else
                      "ready" if action.target_ref == "repair" else str(len(self.dispatched)))
        return DispatchReceipt(action.id, "sent")


def wandering_request():
    return SubAgentRequest("Finish", "", "task", {
        "schema_version": 2, "goal_id": "finish", "intent": "Establish the finished result",
        "objective": "Establish the finished result", "scope": "document",
        "authorization_ref": "current_task", "allowed_operations": ["click"],
        "completion": [{"key": "status:result", "value": "done"}],
    })


async def test_changing_readout_without_goal_evidence_stops_before_fourth_choice():
    world, selector = WanderingWorld(), PickFirst()
    result = await ComputerUseController(world, world, selector=selector).run(
        wandering_request(), context())
    assert result.reason == "goal_progress_unverified"
    assert result.status == "partial"
    assert world.dispatched == ["wander"] * 3
    assert selector.calls == 3
    progress = result.details["progress"]
    assert isinstance(progress, dict) and progress["unverified_goal_steps"] == 3


async def test_planning_review_returns_to_selector_after_one_advisor_action():
    class Selector(PickFirst):
        async def choose(self, goal, snapshot, actions, ctx):
            self.calls += 1
            target = "finish" if snapshot.facts[0].value == "ready" else "wander"
            return DecisionResult(actions.binding, "candidate", next(
                a.id for a in actions.actions if a.target_ref == target))
    class Advisor:
        calls = 0
        async def assist(self, request, goal, snapshot, actions, ctx):
            self.calls += 1
            assert actions.reason == "goal_progress_unverified"
            assert actions.progress.unverified_goal_steps == 3
            return AdvisorResult(actions.binding, "candidate", candidate_id=next(
                a.id for a in actions.actions if a.target_ref == "repair"))
    world, selector, advisor = WanderingWorld(), Selector(), Advisor()
    result = await ComputerUseController(world, world, selector=selector, advisor=advisor).run(
        wandering_request(), context())
    assert result.status == "completed"
    assert world.dispatched == ["wander", "wander", "wander", "repair", "finish"]
    assert selector.calls == 4 and advisor.calls == 1


async def test_focus_guides_selector_then_clears_without_completing_the_goal():
    from agent_computer_use.contracts import FocusProposal
    from agent_computer_use.model_view import decision_question

    seen = []
    class Selector(PickFirst):
        async def choose(self, goal, snapshot, actions, ctx):
            view = json.loads(json.dumps(decision_question(goal, snapshot, actions)))
            focus = view["state"]["progress"]["current_focus"]
            seen.append((snapshot.facts[0].value, focus, actions.progress.unverified_goal_steps))
            assert goal.completion == (Fact(key="status:result", value="done"),)
            target = "repair" if focus else "finish" if snapshot.facts[0].value == "ready" else "wander"
            return DecisionResult(actions.binding, "candidate", next(
                action.id for action in actions.actions if action.target_ref == target))
    class Advisor:
        async def assist(self, request, goal, snapshot, actions, ctx):
            return AdvisorResult(actions.binding, "focus", focus=FocusProposal(
                objective="Prepare the result before finishing",
                completion=(Fact(key="status:result", value="ready"),)))
    world = WanderingWorld()
    controller = ComputerUseController(world, world, selector=Selector(), advisor=Advisor())
    result = await controller.run(wandering_request(), context())
    assert result.status == "completed"
    assert world.dispatched == ["wander"] * 3 + ["repair", "finish"]
    assert seen[-2][1]["proposal"]["objective"] == "Prepare the result before finishing"
    assert seen[-1] == ("ready", None, 4)
    assert controller.advisor_calls == 1
    assert controller.progress.current_focus is None
    assert controller.progress.focus_history[-1].status == "completed"


@pytest.mark.parametrize("target_value", ["5", "unreachable"])
async def test_focus_persists_until_verified_or_three_actions_expire(target_value):
    from agent_computer_use.contracts import FocusProposal
    active = []
    class Selector(PickFirst):
        async def choose(self, goal, snapshot, actions, ctx):
            focus = actions.progress.current_focus
            if focus:
                active.append((focus.revision, snapshot.facts[0].value))
            target = "finish" if not focus and snapshot.facts[0].value == "5" else "wander"
            return DecisionResult(actions.binding, "candidate", next(
                action.id for action in actions.actions if action.target_ref == target))
    class Advisor:
        calls = 0
        async def assist(self, request, goal, snapshot, actions, ctx):
            self.calls += 1
            if self.calls == 1:
                return AdvisorResult(actions.binding, "focus", focus=FocusProposal(
                    objective="Advance the readout", completion=(Fact(key="status:result", value=target_value),)))
            assert actions.reason == "focus_expired"
            assert actions.progress.current_focus is None
            assert actions.progress.unverified_goal_steps == 6
            return AdvisorResult(actions.binding, "candidate", candidate_id=next(
                action.id for action in actions.actions if action.target_ref == "finish"))
    world, advisor = WanderingWorld(), Advisor()
    controller = ComputerUseController(world, world, selector=Selector(), advisor=advisor)
    result = await controller.run(wandering_request(), context())
    assert result.status == "completed"
    assert [value for _, value in active] == (["3", "4"] if target_value == "5" else ["3", "4", "5"])
    assert {revision for revision, _ in active} == {1}
    record = controller.progress.focus_history[-1]
    assert record.reason == ("focus_verified" if target_value == "5" else "action_limit")


@pytest.mark.parametrize("kind", ["unknown_key", "already_satisfied"])
async def test_invalid_focus_stops_without_additional_actions(kind):
    from agent_computer_use.contracts import FocusProposal
    class Advisor:
        async def assist(self, request, goal, snapshot, actions, ctx):
            return AdvisorResult(actions.binding, "focus", focus=FocusProposal(
                objective="Prepare", completion=(Fact(
                    key="unknown:result" if kind == "unknown_key" else "status:result", value="3"),)))
    world = WanderingWorld()
    controller = ComputerUseController(world, world, selector=PickFirst(), advisor=Advisor())
    result = await controller.run(wandering_request(), context())
    assert result.reason == ("unsupported_focus_evidence" if kind == "unknown_key" else "focus_already_satisfied")
    assert world.dispatched == ["wander"] * 3
    assert controller.progress.current_focus is None


async def test_focus_only_planning_cannot_reset_advisor_budget():
    from agent_computer_use.contracts import FocusProposal
    class Selector:
        async def choose(self, goal, snapshot, actions, ctx):
            return DecisionResult(actions.binding, "escalate")
    class Advisor:
        async def assist(self, request, goal, snapshot, actions, ctx):
            return AdvisorResult(actions.binding, "focus", focus=FocusProposal(
                objective="Prepare", completion=(Fact(key="status:result", value="ready"),)))
    world = WanderingWorld()
    controller = ComputerUseController(world, world, selector=Selector(), advisor=Advisor())
    result = await controller.run(wandering_request(), context())
    assert result.reason == "advisor_limit" and controller.advisor_calls == 4
    assert world.dispatched == []
    assert len(controller.progress.focus_history) == 4
    assert all(focus.status == "invalidated" for focus in controller.progress.focus_history)


@pytest.mark.parametrize("change", ["repeated", "incomplete"])
async def test_focus_is_invalidated_when_observation_cannot_support_progress(change):
    from agent_computer_use.contracts import FocusProposal
    class World(WanderingWorld):
        async def observe(self, scope, ctx):
            observed = await super().observe(scope, ctx)
            return replace(observed, complete=False) if change == "incomplete" and self.observations == 5 else observed
        async def dispatch(self, binding, action, ctx):
            receipt = await super().dispatch(binding, action, ctx)
            if change == "repeated" and len(self.dispatched) == 5:
                self.value = "3"
            return receipt
    class Advisor:
        calls = 0
        async def assist(self, request, goal, snapshot, actions, ctx):
            self.calls += 1
            if self.calls == 1:
                return AdvisorResult(actions.binding, "focus", focus=FocusProposal(
                    objective="Prepare", completion=(Fact(key="status:result", value="ready"),)))
            assert actions.progress.current_focus is None
            assert actions.progress.focus_history[-1].reason == "repeated_state"
            return AdvisorResult(actions.binding, "candidate", candidate_id=next(
                action.id for action in actions.actions if action.target_ref == "finish"))
    world = World()
    controller = ComputerUseController(world, world, selector=PickFirst(), advisor=Advisor())
    result = await controller.run(wandering_request(), context())
    assert result.status == ("completed" if change == "repeated" else "partial")
    assert len(world.dispatched) == (6 if change == "repeated" else 3)
    assert controller.progress.focus_history[0].reason == (
        "repeated_state" if change == "repeated" else "observation_unavailable")


async def test_generated_input_patch_invalidates_focus_and_preserves_original_goal():
    from agent_computer_use.contracts import FocusProposal
    class World(WanderingWorld):
        field_value = ""
        async def observe(self, scope, ctx):
            observed = await super().observe(scope, ctx)
            if "repair" in self.dispatched:
                return replace(observed, elements=(
                    Element("field", "textbox", "Generated", ("fill",), value=self.field_value),
                    observed.elements[-1]))
            return observed
        async def dispatch(self, binding, action, ctx):
            if action.operation == "fill":
                self.dispatched.append(action.target_ref)
                self.field_value, self.value = action.value, "done"
                return DispatchReceipt(action.id, "sent")
            return await super().dispatch(binding, action, ctx)
    class Selector(PickFirst):
        async def choose(self, goal, snapshot, actions, ctx):
            target = "repair" if actions.progress.current_focus else "wander"
            return DecisionResult(actions.binding, "candidate", next(
                action.id for action in actions.actions if action.target_ref == target))
    class Advisor:
        async def assist(self, request, goal, snapshot, actions, ctx):
            if actions.progress.current_focus:
                return AdvisorResult(actions.binding, "inputs", inputs=(Fact(key="name", value="Ada"),))
            return AdvisorResult(actions.binding, "focus", focus=FocusProposal(
                objective="Prepare and fill the form", completion=goal.completion))
    request = wandering_request()
    assert isinstance(request.task_input, dict)
    request = replace(request, task_input={**request.task_input,
        "allowed_operations": ["click", "fill"],
        "inputs": [{"key": "name", "purpose": "Generate name", "source": "generated", "field_label": "Generated"}]})
    world = World()
    controller = ComputerUseController(world, world, selector=Selector(), advisor=Advisor())
    result = await controller.run(request, context())
    assert result.status == "completed" and controller.version == 2
    assert controller.progress.focus_history[-1].reason == "goal_changed"
    assert world.dispatched == ["wander"] * 3 + ["repair", "field"]


@pytest.mark.parametrize("unavailable", ["incomplete", "not_ready"])
async def test_transient_unavailable_effect_readback_invalidates_focus_without_replay(unavailable):
    from agent_computer_use.contracts import FocusProposal

    class World(WanderingWorld):
        async def observe(self, scope, ctx):
            observed = await super().observe(scope, ctx)
            if self.observations == 6:
                return replace(observed, complete=unavailable != "incomplete",
                               ready=unavailable != "not_ready")
            return observed

    class Selector(PickFirst):
        async def choose(self, goal, snapshot, actions, ctx):
            if snapshot.facts[0].value == "ready":
                assert actions.progress.current_focus is None
                assert actions.progress.focus_history[-1].reason == "observation_unavailable"
                target = "finish"
            else:
                target = "repair" if actions.progress.current_focus else "wander"
            return DecisionResult(actions.binding, "candidate", next(
                action.id for action in actions.actions if action.target_ref == target))

    class Advisor:
        async def assist(self, request, goal, snapshot, actions, ctx):
            return AdvisorResult(actions.binding, "focus", focus=FocusProposal(
                objective="Prepare the result", completion=(Fact(key="status:result", value="ready"),)))

    world = World()
    controller = ComputerUseController(world, world, selector=Selector(), advisor=Advisor())
    result = await controller.run(wandering_request(), context())
    assert result.status == "completed"
    assert world.dispatched == ["wander"] * 3 + ["repair", "finish"]
    assert controller.advisor_calls == 1 and world.observations == 8
    assert controller.progress.recent_steps[-2].effect_status == "verified"
    assert controller.progress.focus_history[0].final_observation_id == "6"


async def test_unhelpful_planning_advisor_cannot_reset_its_call_limit():
    class Advisor:
        calls = 0
        async def assist(self, request, goal, snapshot, actions, ctx):
            self.calls += 1
            return AdvisorResult(actions.binding, "candidate", candidate_id=actions.actions[0].id)
    world, advisor = WanderingWorld(), Advisor()
    controller = ComputerUseController(world, world, selector=PickFirst(), advisor=advisor)
    result = await controller.run(
        wandering_request(), context())
    assert result.reason == "advisor_limit" and advisor.calls == 4
    assert len(world.dispatched) == 15
    progress = result.details["progress"]
    assert isinstance(progress, dict) and progress["unverified_goal_steps"] == 15
    history = controller.progress.recent_steps
    assert [step.step for step in history] == list(range(6, 16))
    assert all(step.effect_status == "verified" for step in history)
    assert {step.selected_by for step in history} == {"selector", "advisor"}


async def test_advisor_can_recover_a_repeated_state_without_repeating_selector():
    class World(WanderingWorld):
        async def dispatch(self, binding, action, ctx):
            receipt = await super().dispatch(binding, action, ctx)
            if action.target_ref == "wander":
                self.value = str(len(self.dispatched) % 2)
            return receipt
    class Advisor:
        calls = 0
        async def assist(self, request, goal, snapshot, actions, ctx):
            self.calls += 1
            assert actions.reason == "repeated_state"
            return AdvisorResult(actions.binding, "candidate", candidate_id=next(
                a.id for a in actions.actions if a.target_ref == "finish"))
    world, selector, advisor = World(), PickFirst(), Advisor()
    result = await ComputerUseController(world, world, selector=selector, advisor=advisor).run(
        wandering_request(), context())
    assert result.status == "completed"
    assert selector.calls == 2 and advisor.calls == 1
    assert world.dispatched == ["wander", "wander", "finish"]


async def test_advisor_cannot_generate_an_undeclared_user_value():
    task = export_goal().model_dump(mode="json")
    task["inputs"][0]["value"] = None
    world, advisor = ExportWorld(), SupplyFilename()
    result = await ComputerUseController(world, world, advisor=advisor).run(
        SubAgentRequest("Export", "", "task", task), context())
    assert result.status == "needs_input"
    assert result.reason == "missing_user_input"
    assert advisor.calls == 0 and world.dispatched == []
