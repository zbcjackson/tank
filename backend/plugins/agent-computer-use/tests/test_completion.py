"""Generic completion evidence for apps without a profile."""

import pytest
from pydantic import JsonValue
from agent_computer_use.contracts import (
    DispatchReceipt, Element, Fact, GoalContract, Snapshot, TargetBinding,
)
from agent_computer_use.controller import ComputerUseController, achieved
from tank_backend.agents.subagent import SubAgentRequest

from .test_ladder import Binder, context


def generic_goal(*completion: tuple[str, str]) -> dict[str, JsonValue]:
    return {
        "schema_version": 2, "goal_id": "note", "intent": "Write 56 into a new note",
        "objective": "The note shows 56", "scope": "window", "authorization_ref": "task",
        "allowed_operations": ["click", "fill"],
        "completion": [{"key": key, "value": value} for key, value in completion],
    }


def test_goal_accepts_generic_condition_types() -> None:
    goal = GoalContract.from_input(generic_goal(
        ("ax:present:result", "56"), ("ax:absent:dialog", "Save changes?"),
        ("ax:title:document", "Notes"), ("ax:value:Result", "56"), ("status:done", "")))
    assert [fact.key for fact in goal.completion][:3] == [
        "ax:present:result", "ax:absent:dialog", "ax:title:document"]


@pytest.mark.parametrize(("key", "value"), [
    ("ax:present:", "56"),
    ("ax:absent:dialog", ""),
    ("ax:title:document", "   "),
    ("ax:contains:result", "56"),
])
def test_goal_rejects_malformed_generic_conditions(key: str, value: str) -> None:
    with pytest.raises(ValueError):
        GoalContract.from_input(generic_goal((key, value)))
    outcome = {**generic_goal(("status:done", "")),
               "outcomes": [{"id": "o", "conditions": [{"key": key, "value": value}]}]}
    with pytest.raises(ValueError):
        GoalContract.from_input(outcome)


def window(*items: tuple[str, str, str], title: str = "Untitled", complete: bool = True,
           ) -> Snapshot:
    """Elements are (role, label, value) inside one AX window."""
    return Snapshot("obs", "window", 0, tuple(
        Element(f"e{index}", role, label, ("click",) if role == "button" else (),
                kind="control" if role == "button" else "text_region", source="ax",
                value=value, ancestors=(("AXWindow", title),))
        for index, (role, label, value) in enumerate(items)), complete=complete)


BASE = window(("button", "56", ""), ("text", "", "0"))
PRESENT = (Fact(key="ax:present:result", value="56"),)


@pytest.mark.parametrize(("current", "baseline", "expected"), [
    (window(("button", "56", ""), ("text", "", "\u200e56 ")), BASE, True),
    (window(("button", "56", ""), ("text", "", "56")), None, False),
    (window(("button", "56", ""), ("text", "", "56")), window(("text", "", "56")), False),
    (window(("text", "", "56"), ("text", "", "56")), BASE, False),
    (window(("button", "56", ""), ("text", "", "0")), BASE, False),
    (window(("text", "", "56"), complete=False), BASE, False),
])
def test_value_present_must_be_new_unique_and_not_a_label(current, baseline, expected) -> None:
    assert achieved(current, PRESENT, baseline) is expected


@pytest.mark.parametrize(("current", "baseline", "expected"), [
    (window(("text", "", "0")), window(("text", "Save changes?", "")), True),
    (window(("text", "", "Save changes?")), window(("text", "Save changes?", "")), False),
    (window(("text", "", "0")), window(("text", "", "0")), False),
])
def test_element_absent_requires_it_in_the_baseline(current, baseline, expected) -> None:
    condition = (Fact(key="ax:absent:dialog", value="Save changes?"),)
    assert achieved(current, condition, baseline) is expected


@pytest.mark.parametrize(("current", "baseline", "expected"), [
    (window(("text", "", "0"), title="report.txt — Edited"), window(("text", "", "0")), True),
    (window(("text", "", "0"), title="Untitled"), window(("text", "", "0")), False),
    (window(("text", "", "0"), title="report.txt"),
     window(("text", "", "0"), title="report.txt"), False),
])
def test_title_contains_must_newly_hold(current, baseline, expected) -> None:
    condition = (Fact(key="ax:title:document", value="report.txt"),)
    assert achieved(current, condition, baseline) is expected


class NoteWorld:
    """One editable body; `existing` is static text already in the window."""

    def __init__(self, existing: str = "", facts: tuple[Fact, ...] = ()) -> None:
        self.body, self.existing, self.facts, self.dispatched = "", existing, facts, []

    async def observe(self, scope, ctx):
        return Snapshot(f"obs-{len(self.dispatched)}", scope, len(self.dispatched), (
            Element("body", "textbox", "Body", ("fill",), source="ax", value=self.body,
                    ancestors=(("AXWindow", "Notes"),)),
            Element("note", "text", self.existing, (), kind="text_region", source="ax",
                    value=self.existing, ancestors=(("AXWindow", "Notes"),)),
        ), self.facts)

    async def is_current(self, binding, action, ctx):
        return binding.generation == len(self.dispatched)

    async def dispatch(self, binding, action, ctx):
        self.dispatched.append(action)
        self.body = action.value
        return DispatchReceipt(action.id, "sent")


BODY_INPUT: JsonValue = [{"key": "body", "purpose": "note body", "value": "56",
                          "field_label": "Body"}]


def note_request() -> SubAgentRequest:
    goal = generic_goal(("ax:present:body", "56"))
    goal["inputs"] = BODY_INPUT
    return SubAgentRequest("Note", "", "task", {**goal, "target": {"application": "Notes"}})


@pytest.mark.parametrize(("generic", "existing", "status", "reason"), [
    (True, "", "completed", "goal_verified"),
    (True, "56", "partial", "no_viable_actions"),
    (False, "", "needs_input", "unsupported_completion_evidence"),
])
async def test_controller_verifies_generic_conditions_from_its_baseline(
    generic, existing, status, reason,
) -> None:
    world, binder = NoteWorld(existing), Binder()
    binder.binding = TargetBinding("com.apple.Notes", False, frozenset(), generic)
    result = await ComputerUseController(world, world, binder=binder).run(note_request(), context())
    assert (result.status, result.reason) == (status, reason)


async def test_generic_outcomes_never_hold_without_a_generic_target() -> None:
    world = NoteWorld(facts=(Fact(key="status:open", value="yes"),))
    goal = {**generic_goal(("status:open", "yes")), "inputs": BODY_INPUT,
            "outcomes": [{"id": "written", "conditions": [{"key": "ax:present:body",
                                                           "value": "56"}]}]}
    result = await ComputerUseController(world, world).run(
        SubAgentRequest("Note", "", "task", goal), context())
    assert world.dispatched
    assert (result.status, result.reason) == ("partial", "no_viable_actions")
