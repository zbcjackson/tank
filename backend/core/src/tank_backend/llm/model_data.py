"""Small model result helpers; no HTTP interception or task ownership."""

from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any


def chat_data_types(messages: object) -> frozenset[str]:
    """Classify implemented chat content blocks, never infer permission from text."""
    if not isinstance(messages, list):
        raise ValueError("invalid chat messages")
    kinds = {"text"}
    for message in messages:
        if not isinstance(message, dict) or "audio" in message:
            raise ValueError("unsupported message data")
        content = message.get("content")
        if content is None or isinstance(content, str):
            continue
        if not isinstance(content, list):
            raise ValueError("unsupported message content")
        for part in content:
            if not isinstance(part, dict):
                raise ValueError("unsupported content block")
            kind = part.get("type")
            if kind == "text" or kind == "refusal":
                if set(part) != {"type", kind} or not isinstance(part.get(kind), str):
                    raise ValueError("invalid text block")
            elif kind == "image_url":
                value = part.get("image_url")
                if (set(part) != {"type", "image_url"} or not isinstance(value, dict)
                        or not set(value) <= {"url", "detail"}
                        or not isinstance(value.get("url"), str)):
                    raise ValueError("invalid image block")
                kinds.add("image")
            else:
                raise ValueError("unsupported content type")
    return frozenset(kinds)


@dataclass(frozen=True)
class ModelRequest:
    url: str
    model: str
    parameters: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", copy.deepcopy(self.parameters))


@dataclass(frozen=True)
class ModelDataScope:
    """Host allowance for SDK parameter JSON, independent of tokens and HTTP bytes."""

    allowed_types: frozenset[str] = frozenset({"text"})
    max_request_bytes: int = 4 * 1024 * 1024

    def __post_init__(self) -> None:
        if (not isinstance(self.allowed_types, frozenset)
                or not self.allowed_types <= {"text", "image"}
                or type(self.max_request_bytes) is not int or self.max_request_bytes < 0):
            raise ValueError("invalid model data scope")

    def check(self, request: ModelRequest) -> None:
        try:
            parameters = request.parameters
            kinds = (chat_data_types(parameters["messages"]) if "messages" in parameters
                     else frozenset({"text"}))
            if (not kinds <= self.allowed_types or "audio" in parameters
                    or any(kind != "text" for kind in parameters.get("modalities", []))):
                raise ValueError("unsupported request data")
            encoded = json.dumps(parameters, ensure_ascii=False, allow_nan=False,
                                 separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError, UnicodeError, RecursionError):
            raise ValueError("model_data_denied") from None
        if len(encoded) > self.max_request_bytes:
            raise ValueError("model_request_too_large")


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
