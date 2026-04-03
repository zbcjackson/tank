"""Service credential manager — inject API secrets at tool level."""

from __future__ import annotations

import fnmatch
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ServiceCredential:
    """A single service credential bound to specific hosts."""

    name: str
    env_var: str
    allowed_hosts: tuple[str, ...]


class ServiceCredentialManager:
    """Injects credentials at tool execution time.

    Credentials are stored in environment variables and bound to specific
    hosts.  The LLM never sees the raw secret — it only knows the service
    name (e.g. "serper").

    Host validation ensures a credential is only sent to its declared
    ``allowed_hosts``, preventing accidental leakage to unintended endpoints.
    """

    def __init__(self, credentials: tuple[ServiceCredential, ...] = ()) -> None:
        self._credentials = credentials
        self._by_name: dict[str, ServiceCredential] = {
            c.name: c for c in credentials
        }

    def get_env_for_sandbox(self) -> dict[str, str]:
        """Return env vars to inject into sandbox containers.

        Only includes credentials whose env var is actually set in the
        current process environment.
        """
        result: dict[str, str] = {}
        for cred in self._credentials:
            value = os.environ.get(cred.env_var)
            if value:
                result[cred.env_var] = value
        return result

    def validate_host(self, host: str, credential_name: str) -> bool:
        """Check if *host* is allowed to receive the named credential.

        Returns False if the credential is unknown or the host doesn't
        match any of the credential's ``allowed_hosts`` patterns.
        """
        cred = self._by_name.get(credential_name)
        if not cred:
            return False
        host_lower = host.lower()
        return any(
            fnmatch.fnmatch(host_lower, pattern.lower())
            for pattern in cred.allowed_hosts
        )

    def get_credential(self, name: str) -> str | None:
        """Return the credential value from env, or None if not set."""
        cred = self._by_name.get(name)
        if not cred:
            return None
        return os.environ.get(cred.env_var)

    @property
    def available_services(self) -> list[str]:
        """Return names of credentials that are actually set in env."""
        return [
            c.name for c in self._credentials
            if os.environ.get(c.env_var)
        ]

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @staticmethod
    def from_dict(data: list[dict]) -> ServiceCredentialManager:
        """Create from parsed YAML ``service_credentials:`` list."""
        if not data:
            return ServiceCredentialManager()

        credentials: list[ServiceCredential] = []
        for item in data:
            credentials.append(
                ServiceCredential(
                    name=item.get("name", ""),
                    env_var=item.get("env_var", ""),
                    allowed_hosts=tuple(item.get("allowed_hosts", [])),
                )
            )

        return ServiceCredentialManager(credentials=tuple(credentials))
