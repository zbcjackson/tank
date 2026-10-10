"""Turns one natural-language request into a GoalContract through a model-written brief."""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import Field

from .contracts import GoalContract, GoalModel, plain_text


class BriefInput(GoalModel):
    purpose: str = Field(min_length=1, max_length=512)
    value: str | None = Field(default=None, max_length=4096)


class BriefCondition(GoalModel):
    type: Literal["present", "absent", "title"]
    value: str = Field(min_length=1, max_length=4096)


class TaskBrief(GoalModel):
    application: str = Field(min_length=1, max_length=256)
    objective: str = Field(min_length=1, max_length=4096)
    constraints: tuple[str, ...] = Field(default=(), max_length=32)
    inputs: tuple[BriefInput, ...] = Field(default=(), max_length=32)
    completion: tuple[BriefCondition, ...] = Field(min_length=1, max_length=8)


def grounded(brief: TaskBrief, request: str) -> bool:
    """User values must be quoted from the request; expected results may be derived."""
    source = plain_text(request).casefold()
    return all(plain_text(item.value).casefold() in source
               for item in brief.inputs if item.value is not None)


def goal_from_brief(brief: TaskBrief, intent: str) -> GoalContract:
    return GoalContract.from_input({
        "schema_version": 2, "goal_id": uuid4().hex, "intent": intent,
        "objective": brief.objective, "scope": "app", "authorization_ref": "current_task",
        "allowed_operations": ["click", "fill"], "constraints": list(brief.constraints),
        "inputs": [{"key": f"input{index}", "purpose": item.purpose, "value": item.value}
                   for index, item in enumerate(brief.inputs, 1)],
        "completion": [{"key": f"ax:{item.type}:c{index}", "value": item.value}
                       for index, item in enumerate(brief.completion, 1)],
    })
