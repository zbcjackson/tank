"""Small model result helpers; no HTTP interception or task ownership."""

from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any


@dataclass(frozen=True)
class ModelRequest:
    url: str
    model: str
    parameters: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", copy.deepcopy(self.parameters))


def model_usage(value: object) -> tuple[int | None, int | None]:
    if value is None:
        return None, None
    usage = getattr(value, "usage", None)
    inputs = getattr(value, "input_tokens", getattr(usage, "prompt_tokens", None))
    outputs = getattr(value, "output_tokens", getattr(usage, "completion_tokens", None))
    if type(inputs) is int and type(outputs) is int and inputs >= 0 and outputs >= 0:
        return inputs, outputs
    return None, None


def model_payload(value: object) -> dict[str, Any]:
    payload = getattr(value, "payload", None)
    if isinstance(payload, dict):
        return payload
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        data = dump(mode="json")
        return data if isinstance(data, dict) else {}
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return {}


def parse_chat_usage(usage: object) -> tuple[int, int]:
    """Validate raw Chat Completions counts before SDK coercion or accounting."""
    if not isinstance(usage, dict):
        raise ValueError("model response has no trustworthy usage")
    counts: list[int] = []
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if type(value) is not int or value < 0:
            raise ValueError("model response has invalid usage")
        counts.append(value)
    inputs, outputs, total = counts
    if inputs + outputs != total:
        raise ValueError("model response has inconsistent usage")
    return inputs, outputs


def json_object(data: str | bytes) -> dict[str, object]:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    result = json.loads(data, object_pairs_hook=unique)
    if not isinstance(result, dict):
        raise ValueError("JSON object required")
    return result
