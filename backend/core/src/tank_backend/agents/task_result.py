"""Versioned task outcome; plugin-specific progress stays opaque to the host."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .base import AgentOutput, AgentOutputType
from .subagent import JsonValue, validate_task_input

TaskStatus = Literal["completed", "partial", "unknown", "needs_input", "stopped"]
INCOMPLETE_TASK_STATUSES = frozenset({"partial", "unknown", "needs_input", "stopped"})


class TaskResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal[1] = 1
    status: TaskStatus
    summary: str
    reason: str = ""
    details: dict[str, JsonValue] = Field(default_factory=dict)
    cleanup: Literal["pending", "confirmed", "unknown"] = "pending"

    @field_validator("schema_version", mode="before")
    @classmethod
    def validate_version(cls, value: object) -> int:
        if type(value) is not int or value != 1:
            raise ValueError("task result schema_version must be integer 1")
        return value

    @field_validator("details", mode="before")
    @classmethod
    def validate_details(cls, value: object) -> dict[str, JsonValue]:
        result = validate_task_input(value)
        if result is None:
            raise ValueError("task result details must be a JSON object")
        return result

    def to_output(self) -> AgentOutput:
        return AgentOutput(
            AgentOutputType.DONE, self.summary,
            {"stop_reason": self.status, "task_result": self.model_dump(mode="json")},
        )
