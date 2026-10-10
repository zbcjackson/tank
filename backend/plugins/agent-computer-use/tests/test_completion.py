"""Generic completion evidence for apps without a profile."""

import pytest
from pydantic import JsonValue
from agent_computer_use.contracts import Element, Fact, GoalContract, Snapshot
from agent_computer_use.controller import achieved


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
