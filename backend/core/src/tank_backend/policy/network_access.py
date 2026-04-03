"""Network access policy — evaluate allow/require_approval/deny per host."""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

AccessLevel = Literal["allow", "require_approval", "deny"]


@dataclass(frozen=True)
class NetworkAccessRule:
    """A single network access rule matching a set of host patterns."""

    hosts: tuple[str, ...]
    policy: AccessLevel = "allow"
    reason: str = ""


@dataclass(frozen=True)
class NetworkAccessDecision:
    """Result of evaluating a network access policy."""

    level: AccessLevel
    reason: str


class NetworkAccessPolicy:
    """Evaluates network access rules per host.

    Rules are matched first-match-wins: the first rule whose host pattern
    matches the queried host determines the decision.  If no rule matches,
    the default policy is returned.

    Host patterns support ``fnmatch`` wildcards (e.g. ``*.onion``).
    """

    def __init__(
        self,
        rules: tuple[NetworkAccessRule, ...] = (),
        default: AccessLevel = "allow",
    ) -> None:
        self._rules = rules
        self._default = default

    def evaluate(self, host: str) -> NetworkAccessDecision:
        """Evaluate network access for a host.

        Args:
            host: Hostname to check (e.g. ``"pastebin.com"``).

        Returns:
            NetworkAccessDecision with level and reason.
        """
        host_lower = host.lower()

        for rule in self._rules:
            for pattern in rule.hosts:
                if fnmatch.fnmatch(host_lower, pattern.lower()):
                    return NetworkAccessDecision(
                        level=rule.policy, reason=rule.reason,
                    )

        return NetworkAccessDecision(level=self._default, reason="default policy")

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @staticmethod
    def from_dict(data: dict) -> NetworkAccessPolicy:
        """Create policy from a dict (e.g. parsed YAML ``network_access:`` section)."""
        if not data:
            return NetworkAccessPolicy()

        rules: list[NetworkAccessRule] = []
        for rule_data in data.get("rules", []):
            hosts = tuple(rule_data.get("hosts", []))
            rules.append(
                NetworkAccessRule(
                    hosts=hosts,
                    policy=rule_data.get("policy", "allow"),
                    reason=rule_data.get("reason", ""),
                )
            )

        return NetworkAccessPolicy(
            rules=tuple(rules),
            default=data.get("default", "allow"),
        )
