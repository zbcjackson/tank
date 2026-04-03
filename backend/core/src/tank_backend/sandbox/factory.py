"""Sandbox factory — detects platform and constructs the appropriate backend."""

from __future__ import annotations

import logging
import os
import platform
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .protocol import Sandbox

from .policy import SandboxPolicy

logger = logging.getLogger(__name__)


class SandboxBackendUnavailable(Exception):
    """Raised when a requested sandbox backend is not available."""


class SandboxFactory:
    """Detects platform capabilities and constructs the appropriate Sandbox."""

    # Probe results cached at class level (process-lifetime)
    _probe_cache: dict[str, bool] = {}

    @classmethod
    def create(cls, policy: SandboxPolicy, credential_env: dict[str, str] | None = None) -> Sandbox:
        """Return the best available sandbox for the given policy."""
        backend_name = cls._resolve_backend(policy.backend)
        logger.info("Creating sandbox backend: %s", backend_name)
        return cls._build(backend_name, policy, credential_env=credential_env)

    @classmethod
    def _resolve_backend(cls, requested: str) -> str:
        """Resolve backend name from policy, with auto-detection."""
        if requested != "auto":
            if not cls._is_available(requested):
                raise SandboxBackendUnavailable(
                    f"Requested backend '{requested}' is not available on this system"
                )
            return requested

        # Auto-detection priority: seatbelt (macOS) > bubblewrap (Linux) > docker
        for name in cls._detection_order():
            if cls._is_available(name):
                return name

        raise SandboxBackendUnavailable("No sandbox backend available")

    @classmethod
    def _detection_order(cls) -> list[str]:
        """Return backend detection order based on platform."""
        system = platform.system()
        if system == "Darwin":
            return ["seatbelt", "docker"]
        if system == "Linux":
            return ["bubblewrap", "docker"]
        return ["docker"]

    @classmethod
    def _is_available(cls, name: str) -> bool:
        """Check if a backend is available (cached)."""
        if name not in cls._probe_cache:
            cls._probe_cache[name] = cls._probe(name)
        return cls._probe_cache[name]

    @classmethod
    def _probe(cls, name: str) -> bool:
        """Probe for backend availability."""
        probes = {
            "seatbelt": lambda: shutil.which("sandbox-exec") is not None,
            "bubblewrap": lambda: shutil.which("bwrap") is not None,
            "docker": cls._probe_docker,
        }
        probe_fn = probes.get(name)
        if probe_fn is None:
            return False
        try:
            return probe_fn()
        except Exception as e:
            logger.debug("Probe for %s failed: %s", name, e)
            return False

    @classmethod
    def _probe_docker(cls) -> bool:
        """Probe for Docker availability."""
        try:
            import docker

            client = docker.from_env()
            client.ping()
            return True
        except Exception:
            return False

    @classmethod
    def _build(
        cls,
        name: str,
        policy: SandboxPolicy,
        credential_env: dict[str, str] | None = None,
    ) -> Sandbox:
        """Build a sandbox instance for the given backend."""
        if name == "seatbelt":
            from .backends.seatbelt import SeatbeltSandbox

            return SeatbeltSandbox(cls._to_backend_policy(policy, "seatbelt"))

        if name == "bubblewrap":
            from .backends.bubblewrap import BubblewrapSandbox

            return BubblewrapSandbox(cls._to_backend_policy(policy, "bubblewrap"))

        if name == "docker":
            return cls._build_docker(policy, credential_env=credential_env)

        raise ValueError(f"Unknown backend: {name}")

    @classmethod
    def _build_docker(
        cls,
        policy: SandboxPolicy,
        credential_env: dict[str, str] | None = None,
    ) -> Sandbox:
        """Build a Docker sandbox with same-path mounts.

        Translates the unified SandboxPolicy into a SandboxConfig that
        uses same-path volume mounts (host path == container path) so
        the agent sees the same paths the user talks about.
        """
        from .config import SandboxConfig
        from .manager import DockerSandbox

        # Build same-path volume mounts from policy.mounts
        volumes: dict[str, dict[str, str]] = {}
        denied_set = set(policy.denied_paths)

        for mount in policy.mounts:
            abs_host = str(Path(os.path.expanduser(mount.host)).resolve())
            # Skip if the mount overlaps with a denied path
            if cls._is_denied(abs_host, denied_set):
                logger.debug("Skipping denied mount: %s", abs_host)
                continue
            # Same-path: mount at the same absolute path inside container
            volumes[abs_host] = {"bind": abs_host, "mode": mount.mode}

        # Always include workspace as rw at /workspace for backward compat
        workspace = str(Path(policy.docker_workspace).resolve())
        if workspace not in volumes:
            volumes[workspace] = {"bind": "/workspace", "mode": "rw"}

        config = SandboxConfig(
            enabled=True,
            image=policy.docker_image,
            workspace_host_path=policy.docker_workspace,
            memory_limit=policy.memory_limit,
            cpu_count=policy.cpu_count,
            default_timeout=policy.timeout,
            max_timeout=policy.max_timeout,
            network_enabled=(policy.network.mode != "none"),
        )
        manager = DockerSandbox(config, volumes=volumes, extra_env=credential_env)
        return manager

    @staticmethod
    def _is_denied(path: str, denied_set: set[str]) -> bool:
        """Check if *path* falls under any denied path."""
        return any(path == denied or path.startswith(denied + "/") for denied in denied_set)

    @classmethod
    def _to_backend_policy(cls, policy: SandboxPolicy, backend: str) -> object:
        """Translate shared SandboxPolicy to a backend-local BackendPolicy.

        Both native backends (Seatbelt, Bubblewrap) share the same
        ``BackendPolicy`` dataclass from ``backends.shared``.
        """
        from .backends.shared import BackendPolicy, NetworkMode

        if backend in ("seatbelt", "bubblewrap"):
            return BackendPolicy(
                read_only_paths=policy.read_only_paths,
                writable_paths=policy.writable_paths,
                denied_paths=policy.denied_paths,
                network=NetworkMode(policy.network.mode),
                allowed_hosts=policy.network.allowed_hosts,
                default_timeout=policy.timeout,
                max_timeout=policy.max_timeout,
            )

        raise ValueError(f"No policy translation for backend: {backend}")
