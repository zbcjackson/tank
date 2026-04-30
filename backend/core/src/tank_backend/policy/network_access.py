"""Network access policy — evaluate allow/require_approval/deny per host."""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .verdict import AccessLevel, PolicyVerdict

if TYPE_CHECKING:
    from ..config.models import NetworkAccessConfig
    from ..pipeline.bus import Bus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NetworkAccessRule:
    """A single network access rule matching a set of host patterns."""

    hosts: tuple[str, ...]
    policy: AccessLevel = AccessLevel.ALLOW
    reason: str = ""


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
        default: AccessLevel = AccessLevel.ALLOW,
        bus: Bus | None = None,
    ) -> None:
        self._rules = rules
        self._default = default
        self._bus = bus

    def evaluate(self, host: str) -> PolicyVerdict:
        """Evaluate network access for a host."""
        host_lower = host.lower()

        for rule in self._rules:
            for pattern in rule.hosts:
                if fnmatch.fnmatch(host_lower, pattern.lower()):
                    decision = PolicyVerdict(
                        level=rule.policy, reason=rule.reason, policy="network",
                    )
                    self._publish(host, decision)
                    return decision

        decision = PolicyVerdict(
            level=self._default, reason="default policy", policy="network",
        )
        self._publish(host, decision)
        return decision

    # ------------------------------------------------------------------
    # Bus integration
    # ------------------------------------------------------------------

    def _publish(self, host: str, decision: PolicyVerdict) -> None:
        """Publish decision to the Bus if connected."""
        if self._bus is None:
            return
        from ..pipeline.bus import BusMessage

        self._bus.post(BusMessage(
            type="network_access_decision",
            source="network_access_policy",
            payload={
                "host": host,
                "level": decision.level.value,
                "reason": decision.reason,
            },
        ))

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(
        cls, config: NetworkAccessConfig, bus: Bus | None = None,
    ) -> NetworkAccessPolicy:
        """Create from typed NetworkAccessConfig."""
        rules: list[NetworkAccessRule] = []
        for rule_data in config.rules:
            hosts = tuple(rule_data.get("hosts", []))
            rules.append(
                NetworkAccessRule(
                    hosts=hosts,
                    policy=AccessLevel(rule_data.get("policy", "allow")),
                    reason=rule_data.get("reason", ""),
                )
            )
        return cls(
            rules=tuple(rules),
            default=AccessLevel(config.default),
            bus=bus,
        )

    @staticmethod
    def from_dict(data: dict, bus: Bus | None = None) -> NetworkAccessPolicy:
        """Create policy from a dict (e.g. parsed YAML ``network_access:`` section)."""
        if not data:
            return NetworkAccessPolicy(bus=bus)

        rules: list[NetworkAccessRule] = []
        for rule_data in data.get("rules", []):
            hosts = tuple(rule_data.get("hosts", []))
            rules.append(
                NetworkAccessRule(
                    hosts=hosts,
                    policy=AccessLevel(rule_data.get("policy", "allow")),
                    reason=rule_data.get("reason", ""),
                )
            )

        return NetworkAccessPolicy(
            rules=tuple(rules),
            default=AccessLevel(data.get("default", "allow")),
            bus=bus,
        )
