"""Natural-language intake: the model only structures the request; the host builds the contract."""

import asyncio
import json

import httpx
import pytest
from agent_computer_use.contracts import Fact, GoalInput
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
