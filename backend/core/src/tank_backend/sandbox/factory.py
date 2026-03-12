"""Sandbox factory — detects platform and constructs the appropriate backend."""

from __future__ import annotations

import logging
import platform
import shutil
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
    def create(cls, policy: SandboxPolicy) -> Sandbox:
        """Return the best available sandbox for the given policy."""
        backend_name = cls._resolve_backend(policy.backend)
        logger.info(f"Creating sandbox backend: {backend_name}")
        return cls._build(backend_name, policy)

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
            logger.debug(f"Probe for {name} failed: {e}")
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
    def _build(cls, name: str, policy: SandboxPolicy) -> Sandbox:
        """Build a sandbox instance for the given backend."""
        if name == "seatbelt":
            from .backends.seatbelt import SeatbeltSandbox

            return SeatbeltSandbox(cls._to_backend_policy(policy, "seatbelt"))

        if name == "bubblewrap":
            from .backends.bubblewrap import BubblewrapSandbox

            return BubblewrapSandbox(cls._to_backend_policy(policy, "bubblewrap"))

        if name == "docker":
            from .config import SandboxConfig
            from .manager import SandboxManager

            # Translate SandboxPolicy to legacy SandboxConfig
            config = SandboxConfig(
                enabled=True,
                memory_limit=policy.memory_limit,
                cpu_count=policy.cpu_count,
                default_timeout=policy.timeout,
                max_timeout=policy.max_timeout,
                network_enabled=(policy.network.mode != "none"),
            )
            return SandboxManager(config)

        raise ValueError(f"Unknown backend: {name}")

    @classmethod
    def _to_backend_policy(cls, policy: SandboxPolicy, backend: str) -> object:
        """Translate shared SandboxPolicy to a backend-local SandboxPolicy.

        Each backend defines its own SandboxPolicy + NetworkMode types.
        This method bridges the shared policy to the backend-specific one.
        """
        if backend == "seatbelt":
            from .backends.seatbelt import NetworkMode as SeatbeltNetworkMode
            from .backends.seatbelt import SandboxPolicy as SeatbeltPolicy

            return SeatbeltPolicy(
                read_only_paths=policy.read_only_paths,
                writable_paths=policy.writable_paths,
                denied_paths=policy.denied_paths,
                network=SeatbeltNetworkMode(policy.network.mode),
                allowed_hosts=policy.network.allowed_hosts,
                default_timeout=policy.timeout,
                max_timeout=policy.max_timeout,
            )

        if backend == "bubblewrap":
            from .backends.bubblewrap import NetworkMode as BwrapNetworkMode
            from .backends.bubblewrap import SandboxPolicy as BwrapPolicy

            return BwrapPolicy(
                read_only_paths=policy.read_only_paths,
                writable_paths=policy.writable_paths,
                denied_paths=policy.denied_paths,
                network=BwrapNetworkMode(policy.network.mode),
                allowed_hosts=policy.network.allowed_hosts,
                default_timeout=policy.timeout,
                max_timeout=policy.max_timeout,
            )

        raise ValueError(f"No policy translation for backend: {backend}")
