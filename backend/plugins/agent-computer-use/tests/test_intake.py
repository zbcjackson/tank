"""Natural-language intake: the model only structures the request; the host builds the contract."""

import pytest
from agent_computer_use.contracts import Fact, GoalInput
from agent_computer_use.intake import TaskBrief, goal_from_brief
from pydantic import ValidationError

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
