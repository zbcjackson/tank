"""Named JSON model routes: configuration contains references, never credentials."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from ..agents.task_runtime import TaskRuntime
    from ..plugin.registry import ExtensionRegistry


@dataclass(frozen=True)
class JSONModelProfile:
    extension: str
    url: str
    model: str
    credential_env: str

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) or not value.strip() for value in (
            self.extension, self.url, self.model, self.credential_env,
        )):
            raise ValueError("JSON model fields must be nonempty strings")
        url = httpx.URL(self.url)
        if (not re.fullmatch(r"[^\s:]+:[^\s:]+", self.extension)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.credential_env)
                or url.scheme != "https" or not url.host or url.userinfo
                or url.query or url.fragment):
            raise ValueError("JSON model requires a route reference, HTTPS URL and env name")


def parse_json_profiles(raw: object) -> dict[str, JSONModelProfile]:
    if not isinstance(raw, dict):
        raise ValueError("json_models must be a mapping")
    profiles = {}
    for name, values in raw.items():
        if (not isinstance(name, str) or not name.strip() or not isinstance(values, dict)
                or set(values) != {"extension", "url", "model", "credential_env"}):
            raise ValueError("json_models entries require extension/url/model/credential_env only")
        profiles[name] = JSONModelProfile(**values)
    return profiles


def configure_json_profile(
    runtime: TaskRuntime, task_id: str, name: str, profiles: dict[str, JSONModelProfile],
    registry: ExtensionRegistry,
) -> None:
    """Resolve only the selected profile; factories never receive the resolved key."""
    from .model_transport import ModelRoute

    profile = profiles.get(name)
    if profile is None:
        raise ValueError("JSON model profile is not configured")
    manifest = registry.get_manifest(profile.extension)
    if manifest is None or manifest.type != "model_route":
        raise ValueError("JSON model requires a registered model_route extension")
    credential = os.environ.get(profile.credential_env, "")
    if not credential.strip():
        raise ValueError("JSON model credential environment variable is missing")
    route = registry.instantiate(profile.extension, {
        "url": profile.url, "model": profile.model, "credential_ref": name,
    })
    if (not isinstance(route, ModelRoute) or route.url != profile.url
            or route.model != profile.model or route.credential_ref != name):
        raise ValueError("JSON model route disagrees with the host profile")
    runtime.configure_json_model(task_id, route, credential=credential)
