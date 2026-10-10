"""Generic completion evidence for apps without a profile."""

from dataclasses import replace

import pytest
from pydantic import JsonValue
from agent_computer_use.action_builder import ActionBuilder
from agent_computer_use.contracts import (
    DispatchReceipt, Element, Fact, GoalContract, Snapshot, TargetBinding,
)
from agent_computer_use.controller import ComputerUseController, achieved
from agent_computer_use.model_view import compact_model_view
from tank_backend.agents.subagent import SubAgentRequest

from .test_ladder import Binder, PickFirst, context


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


BODY_INPUT: JsonValue = [{"key": "body", "purpose": "note body", "value": "56",
                          "field_label": "Body"}]


def button(ref: str, label: str, title: str = "Notes") -> Element:
    return Element(ref, "button", label, ("click",), source="ax", click_observable=True,
                   ancestors=(("AXWindow", title),))


def field(ref: str, label: str, value: str = "", title: str = "Notes") -> Element:
    return Element(ref, "textbox", label, ("fill",), source="ax", value=value,
                   ancestors=(("AXWindow", title),))


def text(ref: str, value: str, title: str = "Notes") -> Element:
    return Element(ref, "text", "", (), kind="text_region", source="ax", value=value,
                   ancestors=(("AXWindow", title),))


class AppWorld:
    """Scripted AX app: clicking a ref listed in `opens` shows another screen."""

    def __init__(self, screens: dict[str, tuple[str, tuple[Element, ...]]],
                 opens: dict[str, str] | None = None, facts: tuple[Fact, ...] = ()) -> None:
        self.screens = {name: (window, {e.ref: e for e in elements})
                        for name, (window, elements) in screens.items()}
        self.opens, self.facts, self.screen, self.version, self.reads = opens or {}, facts, "A", 0, 0
        self.dispatched = []

    async def observe(self, scope, ctx):
        self.reads += 1
        window, elements = self.screens[self.screen]
        return Snapshot(f"obs-{self.reads}", scope, self.version, tuple(elements.values()),
                        self.facts, window=window)

    async def is_current(self, binding, action, ctx):
        return binding.generation == self.version

    async def dispatch(self, binding, action, ctx):
        self.dispatched.append(action)
        if action.operation == "fill":
            elements = self.screens[self.screen][1]
            elements[action.target_ref] = replace(elements[action.target_ref], value=action.value)
            self.version += 1
        elif action.target_ref in self.opens:
            self.screen = self.opens[action.target_ref]
            self.version += 1
        return DispatchReceipt(action.id, "sent")


def note(*elements: Element) -> AppWorld:
    return AppWorld({"A": ("1", (field("body", "Body"), *elements))})


async def run_app(world: AppWorld, *completion: tuple[str, str], generic: bool = True):
    goal = {**generic_goal(*completion), "inputs": BODY_INPUT,
            "target": {"application": "Notes"}}
    binder = Binder()
    binder.binding = TargetBinding("com.apple.Notes", False, frozenset(), generic)
    return await ComputerUseController(world, world, selector=PickFirst(), binder=binder).run(
        SubAgentRequest("Note", "", "task", goal), context())


@pytest.mark.parametrize(("generic", "world", "status", "reason"), [
    (True, note(), "completed", "goal_verified"),
    (True, note(text("note", "56")), "partial", "no_viable_actions"),
    (False, note(), "needs_input", "unsupported_completion_evidence"),
])
async def test_controller_verifies_generic_conditions_from_its_baseline(
    generic, world, status, reason,
) -> None:
    result = await run_app(world, ("ax:present:body", "56"), generic=generic)
    assert (result.status, result.reason) == (status, reason)


def test_observable_click_is_a_candidate_without_declared_effects() -> None:
    goal = GoalContract.from_input(generic_goal(("ax:present:body", "56")))
    plain = replace(button("new", "New Note"), click_observable=False)
    assert ActionBuilder().build("g", 1, goal, Snapshot("obs", "window", 1, (plain,))).actions == ()
    snapshot = Snapshot("obs", "window", 1, (button("new", "New Note"),))
    actions = ActionBuilder().build("g", 1, goal, snapshot)
    assert [a.operation for a in actions.actions] == ["click"] and actions.details[0].observable
    view, criteria, _, _ = compact_model_view(snapshot, actions)
    assert "observable" not in str(view) and "observable" not in str(criteria)


@pytest.mark.parametrize(("opens", "status", "reason"), [
    ({"new": "B"}, "completed", "goal_verified"),
    ({}, "unknown", "effect_unknown"),
])
async def test_observable_click_is_verified_by_a_changed_snapshot(opens, status, reason) -> None:
    world = AppWorld({"A": ("1", (button("new", "New Note"),)),
                      "B": ("1", (field("body", "Body"),))}, opens)
    result = await run_app(world, ("ax:present:body", "56"))
    assert (result.status, result.reason) == (status, reason)


DIALOG = text("dialog", "Save changes?")
@pytest.mark.parametrize(("screens", "opens", "condition", "status"), [
    # The original window still shows the dialog; another window lacking it proves nothing.
    ({"A": ("1", (DIALOG, button("new", "New Note"))), "B": ("2", (field("body", "Body"),))},
     {"new": "B"}, ("ax:absent:dialog", "Save changes?"), "partial"),
    # A value the new window already showed did not appear during the task.
    ({"A": ("1", (button("new", "New Note"),)), "B": ("2", (field("body", "Body", "56"),))},
     {"new": "B"}, ("ax:present:body", "56"), "partial"),
    ({"A": ("1", (button("new", "New Note"),)), "B": ("2", (field("body", "Body"),))},
     {"new": "B"}, ("ax:present:body", "56"), "completed"),
    # Returning to the original window keeps its task-start baseline.
    ({"A": ("1", (DIALOG, button("new", "New Note"))),
      "B": ("2", (button("close", "Close"),)), "C": ("1", (button("new", "New Note"),))},
     {"new": "B", "close": "C"}, ("ax:absent:dialog", "Save changes?"), "completed"),
])
async def test_each_window_is_judged_against_its_own_baseline(
    screens, opens, condition, status,
) -> None:
    result = await run_app(AppWorld(screens, opens), condition)
    assert result.status == status


async def test_generic_outcomes_never_hold_without_a_generic_target() -> None:
    world = AppWorld({"A": ("1", (field("body", "Body"),))},
                     facts=(Fact(key="status:open", value="yes"),))
    goal = {**generic_goal(("status:open", "yes")), "inputs": BODY_INPUT,
            "outcomes": [{"id": "written", "conditions": [{"key": "ax:present:body",
                                                           "value": "56"}]}]}
    result = await ComputerUseController(world, world).run(
        SubAgentRequest("Note", "", "task", goal), context())
    assert world.dispatched
    assert (result.status, result.reason) == ("partial", "no_viable_actions")
