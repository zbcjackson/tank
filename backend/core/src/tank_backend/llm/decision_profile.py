"""Core decision model configuration, independent of plugin registration."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from ..agents.task_runtime import TaskRuntime


def validate_version(model: str) -> None:
    if not re.fullmatch(r"jev-[0-9]+\.[0-9]+\.[0-9]+", model):
        raise ValueError("Decision model requires an explicit Jev version")


@dataclass(frozen=True)
class DecisionModelProfile:
    url: str
    model: str
    credential_env: str
    images: bool = False

    def __post_init__(self) -> None:
        if any(not isinstance(v, str) or not v.strip() for v in
               (self.url, self.model, self.credential_env)):
            raise ValueError("Decision model fields must be nonempty strings")
        validate_version(self.model)
        if type(self.images) is not bool:
            raise ValueError("Decision images opt-in must be a boolean")
        url = httpx.URL(self.url)
        if (url.scheme != "https" or not url.host
                or url.userinfo or url.query or url.fragment or url.path != "/v1/systemone"
                or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.credential_env)):
            raise ValueError("Decision model requires the Jev HTTPS endpoint and an env name")


def parse_decision_profiles(raw: object) -> dict[str, DecisionModelProfile]:
    if not isinstance(raw, dict):
        raise ValueError("decision_models must be a mapping")
    profiles = {}
    for name, values in raw.items():
        if (not isinstance(name, str) or not name.strip() or not isinstance(values, dict)
                or not {"url", "model", "credential_env"} <= set(values)
                or set(values) - {"url", "model", "credential_env", "images"}):
            raise ValueError(
                "decision_models entries require url/model/credential_env and optional images"
            )
        profiles[name] = DecisionModelProfile(**values)
    return profiles


def configure_decision_profile(runtime: TaskRuntime, task_id: str, name: str,
                               profiles: dict[str, DecisionModelProfile]) -> None:
    profile = profiles.get(name)
    if profile is None:
        raise ValueError("Decision model profile is not configured")
    credential = os.environ.get(profile.credential_env, "")
    if not credential.strip():
        raise ValueError("Decision model credential environment variable is missing")
    runtime.configure_decision_model(task_id, profile, credential=credential)
