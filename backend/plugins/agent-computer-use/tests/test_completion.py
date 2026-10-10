"""Generic completion evidence for apps without a profile."""

import pytest
from pydantic import JsonValue
from agent_computer_use.contracts import GoalContract


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
