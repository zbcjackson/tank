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
    for item in brief.inputs:
        if item.value is None:
            continue
        value = plain_text(item.value).casefold()
        if not value or value not in source:
            return False
    return True


def _quote_from_request(value: str, request: str) -> str | None:
    """Return the request's verbatim span for value, preferring a trailing newline when present."""
    if not value:
        return None
    if value + "\n" in request:
        return value + "\n"
    if value in request:
        return value
    folded = request.casefold()
    needle = value.casefold()
    index = folded.find(needle)
    if index < 0:
        return None
    exact = request[index:index + len(value)]
    if exact + "\n" in request:
        return exact + "\n"
    return exact


def recover_inputs(brief: TaskBrief, request: str) -> TaskBrief:
    """Copy long present values quoted in the request into inputs when the model omitted them."""
    if any(item.value for item in brief.inputs):
        return brief
    inputs: list[BriefInput] = []
    completion: list[BriefCondition] = []
    for item in brief.completion:
        quoted = _quote_from_request(item.value, request) if item.type == "present" else None
        # Judge length on the model value; quote may add a join newline from task\ncontext.
        if quoted is not None and (len(plain_text(item.value)) >= 8 or "\n" in item.value):
            inputs.append(BriefInput(purpose="entered text", value=quoted))
            completion.append(BriefCondition(type=item.type, value=quoted))
        else:
            completion.append(item)
    if not inputs:
        return brief
    return TaskBrief(
        application=brief.application, objective=brief.objective, constraints=brief.constraints,
        inputs=tuple(inputs), completion=tuple(completion),
    )


def align_completion(goal: GoalContract, completion_keys: frozenset[str]) -> GoalContract:
    """Map a lone present check onto a profile result readout when the app declares one."""
    presents = [fact for fact in goal.completion if fact.key.startswith("ax:present:")]
    if len(presents) != 1 or "ax:value:result" not in completion_keys:
        return goal
    rest = [fact for fact in goal.completion if not fact.key.startswith("ax:present:")]
    return GoalContract.from_input({
        **goal.model_dump(mode="json"),
        "completion": [{"key": "ax:value:result", "value": presents[0].value},
                       *[fact.model_dump(mode="json") for fact in rest]],
    })


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
                "when it is not null. inputs are values the user stated for the app to type or fill; "
                "copy them verbatim including whitespace and trailing newlines, or use null when the "
                "user must still provide one. Never invent user values. Do not put fill text only in "
                "completion—text the app must enter belongs in inputs, and completion.present may "
                "repeat that same text. completion lists text the app window shows once the task is "
                "done: present for a new field value, absent for a value that disappears, title for "
                "the window title. Expected results may be derived, such as a computed number, and "
                "those short results are not inputs. Return unable with application_unknown when the "
                "app is unclear, no_observable_completion when no visible text can confirm completion, "
                "or missing_user_input when required information is missing."
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
        source = f"{request.task}\n{request.context}"
        brief = recover_inputs(reply.brief, source)
        return brief if grounded(brief, source) else "ungrounded_input"
