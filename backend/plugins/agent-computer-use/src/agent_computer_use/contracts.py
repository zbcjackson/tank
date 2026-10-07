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


class GoalInput(GoalModel):
    key: str = Field(min_length=1, max_length=128)
    purpose: str = Field(min_length=1, max_length=512)
    field_scope: str | None = Field(default=None, min_length=1, max_length=256)
    field_label: str | None = Field(default=None, min_length=1, max_length=512)
    value: str | None = Field(default=None, max_length=4096)
    source: Literal["user", "generated"] = "user"
    input_type: Literal["text", "email", "url", "tel", "search", "password"] = "text"


class Outcome(GoalModel):
    id: str = Field(min_length=1, max_length=128)
    conditions: tuple[Fact, ...] = Field(min_length=1, max_length=32)
    depends_on: tuple[str, ...] = Field(default=(), max_length=32)


class GoalContract(GoalModel):
    """Desired outcomes and input purposes, never an ordered action script.

    authorization_ref identifies the existing task grant; it cannot grant capabilities.
    Completion currently supports channel facts only, not arbitrary verification code.
    """

    schema_version: Literal[2]
    goal_id: str = Field(min_length=1, max_length=128)
    intent: str = Field(min_length=1, max_length=4096)
    objective: str = Field(min_length=1, max_length=4096)
    scope: str = Field(min_length=1, max_length=256)
    authorization_ref: str = Field(min_length=1, max_length=128)
    allowed_operations: tuple[Operation, ...] = Field(min_length=1, max_length=2)
    constraints: tuple[str, ...] = Field(default=(), max_length=32)
    inputs: tuple[GoalInput, ...] = Field(default=(), max_length=32)
    outcomes: tuple[Outcome, ...] = Field(default=(), max_length=32)
    completion: tuple[Fact, ...] = Field(min_length=1, max_length=32)

    @field_validator("schema_version", mode="before")
    @classmethod
    def validate_schema(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("schema_version must be integer 2")
        return value

    @model_validator(mode="after")
    def validate_identity(self) -> GoalContract:
        for names in (
            [item.key for item in self.inputs], [item.id for item in self.outcomes],
            [item.key for item in self.completion], list(self.allowed_operations),
        ):
            if len(set(names)) != len(names):
                raise ValueError("Duplicate goal identity")
        # Resolve the bounded dependency graph without relying on declaration order.
        remaining = {item.id: set(item.depends_on) for item in self.outcomes}
        resolved: set[str] = set()
        while remaining:
            ready = {key for key, dependencies in remaining.items() if dependencies <= resolved}
            if not ready:
                raise ValueError("Unknown or cyclic outcome dependency")
            resolved.update(ready)
            remaining = {key: value for key, value in remaining.items() if key not in ready}
        return self


    @classmethod
    def from_input(cls, value: object) -> GoalContract:
        # JSON arrays become immutable tuples without coercing scalar values.
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
    click_effect: tuple[Fact, ...] = ()
    submits: bool = False
    input_type: str = "text"


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
    details: tuple[ActionDetails, ...] = ()
    progress: GoalProgress | None = None


@dataclass(frozen=True)
class ActionDetails:
    action_id: str
    role: str
    label: str
    ancestors: tuple[tuple[str, str], ...]
    current_value: str
    input_key: str | None
    effect: tuple[Fact, ...] = ()


@dataclass(frozen=True)
class GoalProgress:
    goal_version: int = 1
    recent_action: Action | None = None
    verified_actions: tuple[str, ...] = ()
    pending_action: Action | None = None
    no_progress: int = 0
    input_bindings: tuple[tuple[str, str], ...] = ()
    verified_outcomes: tuple[str, ...] = ()


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


def snapshot_json(snapshot: Snapshot) -> dict[str, object]:
    """Serialize nested Pydantic facts as well as dataclass observation fields."""
    elements = []
    for element in snapshot.elements:
        data = asdict(element)
        # Preserve the v1 wire shape when no goal-driven capability was observed.
        data.pop("click_effect")
        data.pop("submits")
        if element.input_type == "text":
            data.pop("input_type")
        if element.click_effect:
            data["click_effect"] = [fact.model_dump(mode="json") for fact in element.click_effect]
        if element.submits:
            data["submits"] = True
        elements.append(data)
    return {**asdict(snapshot), "elements": elements,
            "facts": [fact.model_dump(mode="json") for fact in snapshot.facts]}


def snapshot_text(snapshot: Snapshot) -> str:
    """Current semantic view only; native handles and image bytes have no fields here."""
    return json.dumps(snapshot_json(snapshot), ensure_ascii=False, allow_nan=False)
