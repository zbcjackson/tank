"""Bounded goal input and immutable, channel-independent host messages."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Operation = Literal["click", "fill"]


class GoalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Fact(GoalModel):
    key: str = Field(min_length=1, max_length=128)
    value: str = Field(max_length=4096)


class Milestone(GoalModel):
    id: str = Field(min_length=1, max_length=128)
    operation: Operation
    role: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=512)
    input_key: str | None = None
    postcondition: Fact

    @model_validator(mode="after")
    def validate_input(self) -> Milestone:
        if (self.operation == "fill") != bool(self.input_key):
            raise ValueError("Only fill requires an input_key")
        return self


class GoalContract(GoalModel):
    schema_version: Literal[1]
    objective: str = Field(min_length=1, max_length=4096)
    scope: str = Field(min_length=1, max_length=256)
    inputs: tuple[Fact, ...] = ()
    milestones: tuple[Milestone, ...] = Field(min_length=1, max_length=32)
    completion: tuple[Fact, ...] = Field(min_length=1, max_length=32)

    @field_validator("schema_version", mode="before")
    @classmethod
    def validate_schema(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("schema_version must be integer 1")
        return value

    @model_validator(mode="after")
    def validate_identity(self) -> GoalContract:
        for names in (
            [item.key for item in self.inputs],
            [item.id for item in self.milestones],
            [item.key for item in self.completion],
        ):
            if len(set(names)) != len(names):
                raise ValueError("Duplicate input, milestone or completion key")
        return self

    @classmethod
    def from_input(cls, value: object) -> GoalContract:
        # JSON tuples are arrays; strict mode still rejects coerced scalar values.
        return cls.model_validate_json(json.dumps(value, allow_nan=False))


@dataclass(frozen=True)
class Element:
    ref: str
    role: str
    label: str
    actions: tuple[Operation, ...]
    enabled: bool = True
    kind: Literal["control", "text_region"] = "control"
    source: Literal["ax", "ocr", "dom", "fixture"] = "fixture"
    value: str = ""
    focused: bool | None = None
    ancestors: tuple[tuple[str, str], ...] = ()
    bounds: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class Snapshot:
    observation_id: str
    scope: str
    generation: int
    elements: tuple[Element, ...] = ()
    facts: tuple[Fact, ...] = ()
    complete: bool = True
    ready: bool = True

    def __post_init__(self) -> None:
        if not self.observation_id or not self.scope or self.generation < 0:
            raise ValueError("Snapshot requires an observation identity and scope")
        for keys in ([element.ref for element in self.elements], [fact.key for fact in self.facts]):
            if len(set(keys)) != len(keys):
                raise ValueError("Snapshot identities must be unique")


@dataclass(frozen=True)
class Binding:
    goal_id: str
    goal_version: int
    observation_id: str
    scope: str
    generation: int
    candidate_set_id: str


@dataclass(frozen=True)
class Action:
    id: str
    target_ref: str
    operation: Operation
    value: str | None


@dataclass(frozen=True)
class ActionSet:
    binding: Binding
    actions: tuple[Action, ...]
    reason: str
    total_candidates: int = 0
    truncated: bool = False


@dataclass(frozen=True)
class DispatchReceipt:
    action_id: str
    status: Literal["not_sent", "sent", "unknown"]
    reason: str = ""


@dataclass(frozen=True)
class DecisionResult:
    binding: Binding
    choice: Literal["candidate", "none", "ambiguous", "need_more_context", "escalate"]
    candidate_id: str | None = None


@dataclass(frozen=True)
class AdvisorResult:
    binding: Binding
    kind: Literal["inputs", "candidate", "need_observation", "needs_user_input", "unable"]
    inputs: tuple[Fact, ...] = ()
    candidate_id: str | None = None


def snapshot_text(snapshot: Snapshot) -> str:
    """Current semantic view only; native handles and image bytes have no fields here."""
    return json.dumps(asdict(snapshot), ensure_ascii=False, allow_nan=False)
