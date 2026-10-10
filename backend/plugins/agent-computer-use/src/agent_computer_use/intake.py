"""Turns one natural-language request into a GoalContract through a model-written brief."""

from __future__ import annotations

import json
from typing import Literal
from uuid import uuid4

from pydantic import Field, ValidationError, model_validator

from tank_backend.agents.subagent import SubAgentContext, SubAgentRequest, SubAgentStopped
from tank_backend.llm.model_data import json_object

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


class IntakeReply(GoalModel):
    kind: Literal["brief", "unable"]
    brief: TaskBrief | None = None
    reason: Literal["application_unknown", "no_observable_completion", "missing_user_input"] | None = None

    @model_validator(mode="after")
    def matching_fields(self) -> IntakeReply:
        if (self.kind == "brief") != (self.brief is not None) or (self.brief is None) == (self.reason is None):
            raise ValueError("Intake must contain exactly the fields for its kind")
        return self


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


class LLMIntake:
    async def read(
        self, request: SubAgentRequest, application: str | None, context: SubAgentContext,
    ) -> TaskBrief | str:
        """One task-model call; returns the brief or a needs_input reason."""
        context.check("network")
        model = context.runtime.model
        if model is None:
            raise SubAgentStopped("intake_model_unavailable")
        payload = {
            "request": request.task, "context": request.context, "application": application,
            "response_schema": IntakeReply.model_json_schema(),
        }
        text = await model.complete([
            {"role": "system", "content": (
                "Return one JSON object matching response_schema that restates a desktop task for "
                "one macOS application. application is the app to operate; use the given application "
                "when it is not null. inputs are values the user stated for the app to enter; copy "
                "them verbatim, or use null when the user must still provide one. Never invent user "
                "values. completion lists text the app window shows once the task is done, written "
                "in the language the app displays: present for a new field value, absent for a value "
                "that disappears, title for the window title. Expected results may be derived, such "
                "as a computed number. Return unable with application_unknown when the app is unclear, "
                "no_observable_completion when no visible text can confirm completion, or "
                "missing_user_input when required information is missing."
            )},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, allow_nan=False)},
        ])
        context.check("network")
        try:
            if len(text) > 16384:
                raise ValueError("Intake exceeds the response bound")
            reply = IntakeReply.model_validate_json(json.dumps(json_object(text), allow_nan=False))
        except (ValueError, ValidationError):
            raise SubAgentStopped("invalid_intake") from None
        if reply.brief is None:
            assert reply.reason is not None
            return reply.reason
        return reply.brief if grounded(reply.brief, f"{request.task}\n{request.context}") else "ungrounded_input"
