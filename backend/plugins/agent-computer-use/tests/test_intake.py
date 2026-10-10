"""Natural-language intake: the model only structures the request; the host builds the contract."""

import asyncio
import json

import httpx
import pytest
from agent_computer_use.contracts import Fact, GoalInput, TargetBinding
from agent_computer_use.controller import ComputerUseController
from agent_computer_use.intake import LLMIntake, TaskBrief, goal_from_brief, grounded
from pydantic import ValidationError

from tank_backend.agents.subagent import (
    SubAgentAuthorization,
    SubAgentBudget,
    SubAgentContext,
    SubAgentRequest,
    SubAgentStopped,
)
from tank_backend.llm.profile import LLMProfile

from .test_completion import generic_goal, note
from .test_ladder import Binder, PickFirst, context

BRIEF = {
    "application": "Notes",
    "objective": "Create a note containing the shopping list",
    "constraints": ["Do not delete other notes"],
    "inputs": [{"purpose": "note body", "value": "milk, eggs"}],
    "completion": [{"type": "present", "value": "milk, eggs"}, {"type": "title", "value": "Notes"}],
}


def test_brief_expands_into_a_generic_goal_contract() -> None:
    goal = goal_from_brief(TaskBrief.from_input(BRIEF), "在备忘录里记下 milk, eggs")

    assert goal.intent == "在备忘录里记下 milk, eggs"
    assert goal.objective == BRIEF["objective"]
    assert goal.authorization_ref == "current_task"
    assert goal.allowed_operations == ("click", "fill")
    assert goal.constraints == ("Do not delete other notes",)
    assert goal.inputs == (GoalInput(key="input1", purpose="note body", value="milk, eggs"),)
    assert goal.completion == (Fact(key="ax:present:c1", value="milk, eggs"),
                               Fact(key="ax:title:c2", value="Notes"))
    assert goal.goal_id != goal_from_brief(TaskBrief.from_input(BRIEF), "again").goal_id


@pytest.mark.parametrize("change", [
    {"completion": []},
    {"completion": [{"type": "value", "value": "56"}]},
    {"completion": [{"type": "present", "value": "56", "key": "ax:value:result"}]},
    {"application": ""},
    {"scope": "editor"},
])
def test_invalid_briefs_are_rejected(change) -> None:
    with pytest.raises(ValidationError):
        TaskBrief.from_input({**BRIEF, **change})


def test_blank_expected_values_fail_contract_validation() -> None:
    brief = TaskBrief.from_input({**BRIEF, "completion": [{"type": "absent", "value": " "}]})

    with pytest.raises(ValueError, match="Invalid AX completion condition"):
        goal_from_brief(brief, "remove it")


@pytest.mark.parametrize(("request_text", "inputs", "expected"), [
    ("在备忘录里记下 Milk,\u200b  Eggs", [{"purpose": "note body", "value": "milk, eggs"}], True),
    ("Create a note", [{"purpose": "note body", "value": None}], True),
    ("Create a note", [], True),
    ("Create a note", [{"purpose": "note body", "value": "milk, eggs"}], False),
    ("记下 milk", [{"purpose": "a", "value": "milk"}, {"purpose": "b", "value": "eggs"}], False),
    ("Create a note", [{"purpose": "note body", "value": "   "}], False),
    ("Create a note", [{"purpose": "note body", "value": "\u200b"}], False),
])
def test_input_values_must_come_from_the_request(request_text, inputs, expected) -> None:
    brief = TaskBrief.from_input({**BRIEF, "inputs": inputs,
                                  "completion": [{"type": "present", "value": "derived 56"}]})

    assert grounded(brief, request_text) is expected


def completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"id": "intake", "object": "chat.completion", "created": 1,
        "model": "planner", "choices": [{"index": 0, "finish_reason": "stop", "message": {
            "role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})


@pytest.fixture
def intake(monkeypatch):
    sent: list[httpx.Request] = []
    replies: list[str] = []

    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            sent.append(request)
            return completion(replies.pop(0))

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)

    async def read(reply, task="在备忘录里记下 milk, eggs", application=None, *, model=True):
        replies.append(reply if isinstance(reply, str) else json.dumps(reply))
        ctx = SubAgentContext(SubAgentAuthorization(frozenset({"network", "desktop"})),
                              SubAgentBudget(), asyncio.Event())
        if model:
            ctx.runtime.configure_model("task", LLMProfile(
                "text", "key", "planner", "https://offline.invalid/v1", max_tokens=128))
        try:
            return await LLMIntake().read(
                SubAgentRequest(task, "Keep other notes", "task"), application, ctx), ctx
        finally:
            await ctx.runtime.aclose()

    return read, sent


async def test_intake_reads_one_brief_through_the_task_model(intake) -> None:
    read, sent = intake

    brief, ctx = await read({"kind": "brief", "brief": BRIEF}, application="Notes")

    assert brief == TaskBrief.from_input(BRIEF)
    assert len(sent) == 1 and ctx.budget.total_tokens == 15
    payload = json.loads(json.loads(sent[0].content)["messages"][1]["content"])
    assert payload["request"] == "在备忘录里记下 milk, eggs"
    assert payload["context"] == "Keep other notes"
    assert payload["application"] == "Notes"
    assert "brief" in payload["response_schema"]["properties"]


@pytest.mark.parametrize("reply, reason", [
    ({"kind": "unable", "reason": "application_unknown"}, "application_unknown"),
    ({"kind": "unable", "reason": "no_observable_completion"}, "no_observable_completion"),
    ({"kind": "brief", "brief": {**BRIEF, "inputs": [{"purpose": "body", "value": "bread"}]}},
     "ungrounded_input"),
])
async def test_intake_reports_field_level_needs_input_reasons(intake, reply, reason) -> None:
    read, _ = intake

    assert (await read(reply))[0] == reason


@pytest.mark.parametrize("reply", [
    "not json",
    {"kind": "brief"},
    {"kind": "unable", "reason": "application_unknown", "brief": BRIEF},
    {"kind": "unable", "reason": "too_hard"},
    {"kind": "unable"},
    json.dumps({"kind": "brief", "brief": BRIEF}) + " " * 16384,
])
async def test_invalid_intake_replies_stop_the_task(intake, reply) -> None:
    read, _ = intake

    with pytest.raises(SubAgentStopped, match="invalid_intake"):
        await read(reply)


async def test_intake_without_a_task_model_sends_nothing(intake) -> None:
    read, sent = intake

    with pytest.raises(SubAgentStopped, match="intake_model_unavailable"):
        await read({"kind": "brief", "brief": BRIEF}, model=False)
    assert sent == []


NOTE_BRIEF = {"application": "Notes", "objective": "The note shows 56",
              "inputs": [{"purpose": "note body", "value": "56"}],
              "completion": [{"type": "present", "value": "56"}]}


class FakeIntake:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    async def read(self, request, application, ctx):
        self.calls.append((request.task, application))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


async def run_intake(reply, task_input=None):
    world, binder, intake = note(), Binder(), FakeIntake(reply)
    binder.binding = TargetBinding("com.apple.Notes", False, frozenset(), True)
    result = await ComputerUseController(world, world, selector=PickFirst(), binder=binder,
                                         intake=intake).run(
        SubAgentRequest("在备忘录写 56", "", "task", task_input), context())
    return result, world, binder, intake


async def test_request_without_a_contract_is_read_then_bound_and_verified() -> None:
    brief = TaskBrief.from_input(NOTE_BRIEF)

    result, world, binder, intake = await run_intake(brief)

    assert (result.status, result.reason) == ("completed", "goal_verified")
    assert intake.calls == [("在备忘录写 56", None)]
    assert binder.calls == [("Notes", "app")]
    assert [(a.operation, a.value) for a in world.dispatched] == [("fill", "56")]
    assert result.details["intake"] == brief.model_dump(mode="json")


async def test_parent_target_overrides_the_brief_application() -> None:
    result, _, binder, intake = await run_intake(
        TaskBrief.from_input(NOTE_BRIEF), {"target": {"application": "com.apple.Notes"}})

    assert result.status == "completed"
    assert intake.calls == [("在备忘录写 56", "com.apple.Notes")]
    assert binder.calls == [("com.apple.Notes", "app")]


@pytest.mark.parametrize(("reply", "status", "reason"), [
    ("ungrounded_input", "needs_input", "ungrounded_input"),
    ("application_unknown", "needs_input", "application_unknown"),
    (SubAgentStopped("invalid_intake"), "stopped", "invalid_intake"),
    (TaskBrief.from_input({**NOTE_BRIEF, "completion": [{"type": "present", "value": " "}]}),
     "stopped", "invalid_intake"),
])
async def test_failed_intake_never_binds_or_dispatches(reply, status, reason) -> None:
    result, world, binder, _ = await run_intake(reply)

    assert (result.status, result.reason) == (status, reason)
    assert binder.calls == [] and world.dispatched == []
    assert "intake" not in result.details


async def test_full_contracts_bypass_intake() -> None:
    goal = {**generic_goal(("ax:present:body", "56")), "scope": "app",
            "inputs": [{"key": "body", "purpose": "note body", "value": "56"}],
            "target": {"application": "Notes"}}

    result, _, binder, intake = await run_intake(TaskBrief.from_input(NOTE_BRIEF), goal)

    assert result.status == "completed"
    assert intake.calls == [] and binder.calls == [("Notes", "app")]


def test_present_completion_aligns_to_profile_result_readout() -> None:
    from agent_computer_use.intake import TaskBrief, align_completion, goal_from_brief

    goal = goal_from_brief(TaskBrief.from_input(NOTE_BRIEF), "在备忘录写 56")
    aligned = align_completion(goal, frozenset({"ax:value:expression", "ax:value:result"}))

    assert [fact.key for fact in aligned.completion] == ["ax:value:result"]
    assert aligned.completion[0].value == "56"


def test_present_completion_stays_generic_without_profile_readouts() -> None:
    from agent_computer_use.intake import TaskBrief, align_completion, goal_from_brief

    goal = goal_from_brief(TaskBrief.from_input(NOTE_BRIEF), "在备忘录写 56")

    assert align_completion(goal, frozenset()) == goal


async def test_aligns_intake_present_to_profile_result_during_bind() -> None:
    world = note()
    world.facts = (Fact(key="ax:value:result", value="56"),)
    binder, intake = Binder(), FakeIntake(TaskBrief.from_input(NOTE_BRIEF))
    binder.binding = TargetBinding(
        "com.apple.calculator", False, frozenset({"ax:value:result"}), True)
    result = await ComputerUseController(world, world, selector=PickFirst(), binder=binder,
                                         intake=intake).run(
        SubAgentRequest("在备忘录写 56", "", "task", {"target": {"application": "Calculator"}}),
        context())
    assert (result.status, result.reason) == ("completed", "goal_verified")
    assert result.details["intake"]["completion"][0] == {"type": "present", "value": "56"}


def test_recover_inputs_copies_long_present_values_from_the_request() -> None:
    from agent_computer_use.intake import TaskBrief, recover_inputs

    request = "把正文换成：\nTank NL / 中文验收\n不要保存"
    brief = TaskBrief.from_input({
        "application": "TextEdit", "objective": "Replace the body",
        "inputs": [],
        "completion": [{"type": "present", "value": "Tank NL / 中文验收"}],
    })

    recovered = recover_inputs(brief, request)

    assert len(recovered.inputs) == 1
    assert recovered.inputs[0].value == "Tank NL / 中文验收\n"
    assert recovered.completion[0].value == "Tank NL / 中文验收\n"


def test_recover_inputs_leaves_short_derived_results_alone() -> None:
    from agent_computer_use.intake import TaskBrief, recover_inputs

    request = "用计算器算出 7×8，让结果显示为 56。"
    brief = TaskBrief.from_input({
        "application": "Calculator", "objective": "Show 56",
        "inputs": [],
        "completion": [{"type": "present", "value": "56"}],
    })

    assert recover_inputs(brief, request) == brief


def test_recover_inputs_ignores_join_newline_on_short_results() -> None:
    from agent_computer_use.intake import TaskBrief, recover_inputs

    # LLMIntake joins as f"{task}\n{context}"; a short present at the end of
    # task must not become a fill just because that join adds a newline.
    request = "算出结果 56\n"
    brief = TaskBrief.from_input({
        "application": "Calculator", "objective": "Show 56",
        "inputs": [],
        "completion": [{"type": "present", "value": "56"}],
    })

    assert recover_inputs(brief, request) == brief
