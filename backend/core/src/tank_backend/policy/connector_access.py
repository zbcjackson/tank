"""Connector access policy — per-instance allowlists for inbound events.

Each connector instance (one Telegram bot, one Slack workspace, …) owns
a :class:`ConnectorAllowlistPolicy` that gates every inbound
:class:`Identity`. The :class:`ConnectorManager` evaluates the policy
before session resolution, denies rejected messages at the cheapest
possible point, and publishes every decision to the Bus as
``connector_access_decision`` — the existing :class:`AuditLogger`
subscribes and writes JSONL.

The shape mirrors :mod:`network_access` deliberately: operators who've
configured network rules transfer the mental model (first-match-wins,
fnmatch globs, typed rule list + default) to connector allowlists
without relearning anything.
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..config.parser import ConfigError
from .verdict import AccessLevel, PolicyVerdict

if TYPE_CHECKING:
    from tank_contracts.connector import Identity

    from ..pipeline.bus import Bus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConnectorAllowRule:
    """A single rule matching identities by external_id glob.

    ``external_ids`` accepts ``fnmatch`` patterns against the
    :attr:`Identity.external_id` string (e.g. ``"tg:user:*"``,
    ``"slack:U01ABCDEFG"``, ``"tg:chat:-100*"``). The patterns are
    matched case-sensitively — identity strings are already
    lowercase-safe because they come from platform IDs.
    """

    external_ids: tuple[str, ...]
    policy: AccessLevel = AccessLevel.ALLOW
    reason: str = ""


@dataclass(frozen=True)
class ConnectorAllowlistConfig:
    """Typed ``allowlist:`` sub-config for one connector instance.

    Absent ``allowlist`` key in config.yaml defaults to
    ``ConnectorAllowlistConfig()`` — allow-all, zero rules — which
    matches pre-Phase-6 behaviour.
    """

    default: AccessLevel = AccessLevel.ALLOW
    rules: tuple[ConnectorAllowRule, ...] = ()


# ---------------------------------------------------------------------------
# Runtime policy
# ---------------------------------------------------------------------------


class ConnectorAllowlistPolicy:
    """Evaluate connector inbound identities against an allowlist.

    First-match-wins across ``rules``; falls back to ``default`` if no
    rule matches. Decisions are published as ``connector_access_decision``
    Bus messages when a :class:`Bus` is wired in — the
    :class:`AuditLogger` subscribes and records them.

    Constructing with an empty :class:`ConnectorAllowlistConfig` gives
    an effectively inert policy (everything allowed, no rule scanning)
    — useful as a placeholder for instances that haven't declared an
    allowlist.
    """

    def __init__(
        self,
        config: ConnectorAllowlistConfig,
        *,
        instance_name: str,
        bus: Bus | None = None,
    ) -> None:
        self._default = config.default
        self._rules = config.rules
        self._instance_name = instance_name
        self._bus = bus

    @property
    def instance_name(self) -> str:
        return self._instance_name

    def evaluate(self, identity: Identity) -> PolicyVerdict:
        """Return the verdict for ``identity``.

        Posts a ``connector_access_decision`` Bus event when a ``bus``
        was provided at construction. Callers should use the returned
        verdict's ``level`` to decide behaviour; the Bus post is for
        audit, not control flow.
        """
        for rule in self._rules:
            for pattern in rule.external_ids:
                if fnmatch.fnmatchcase(identity.external_id, pattern):
                    verdict = PolicyVerdict(
                        level=rule.policy,
                        reason=rule.reason or f"matched pattern {pattern!r}",
                        policy="connector_access",
                        context={
                            "connector": self._instance_name,
                            "platform": identity.platform,
                            "external_id": identity.external_id,
                            "display_name": identity.display_name,
                            "matched_pattern": pattern,
                        },
                    )
                    self._publish(verdict)
                    return verdict

        verdict = PolicyVerdict(
            level=self._default,
            reason="no matching rule; using default",
            policy="connector_access",
            context={
                "connector": self._instance_name,
                "platform": identity.platform,
                "external_id": identity.external_id,
                "display_name": identity.display_name,
            },
        )
        self._publish(verdict)
        return verdict

    def _publish(self, verdict: PolicyVerdict) -> None:
        if self._bus is None:
            return
        from ..pipeline.bus import BusMessage

        self._bus.post(BusMessage(
            type="connector_access_decision",
            source="ConnectorAllowlistPolicy",
            payload={"verdict": verdict},
        ))


# ---------------------------------------------------------------------------
# Parser — raw YAML dict → typed config
# ---------------------------------------------------------------------------


def parse_allowlist(
    raw: object | None,
    *,
    instance_name: str,
) -> ConnectorAllowlistConfig:
    """Parse a raw ``allowlist:`` dict into :class:`ConnectorAllowlistConfig`.

    Missing / empty / ``None`` → default allow-all (zero-config case).
    Malformed input raises :class:`ConfigError` with the instance name
    in the message so operators can locate the bad entry in config.yaml.

    ``REQUIRE_APPROVAL`` parses but is rejected here — a connector-level
    approval workflow is Phase 7+ material and not supported in v1.
    """
    if raw is None or raw == {}:
        return ConnectorAllowlistConfig()

    if not isinstance(raw, dict):
        raise ConfigError(
            f"connectors[{instance_name}].allowlist: expected mapping, "
            f"got {type(raw).__name__}",
        )

    default = _parse_access_level(
        raw.get("default", "allow"),
        instance_name=instance_name,
        field="default",
    )

    rules_raw = raw.get("rules", [])
    if rules_raw is None:
        rules_raw = []
    if not isinstance(rules_raw, list):
        raise ConfigError(
            f"connectors[{instance_name}].allowlist.rules: expected list, "
            f"got {type(rules_raw).__name__}",
        )

    rules: list[ConnectorAllowRule] = []
    for index, rule_raw in enumerate(rules_raw):
        rules.append(_parse_rule(
            rule_raw, instance_name=instance_name, index=index,
        ))

    return ConnectorAllowlistConfig(default=default, rules=tuple(rules))


def _parse_rule(
    raw: object,
    *,
    instance_name: str,
    index: int,
) -> ConnectorAllowRule:
    where = f"connectors[{instance_name}].allowlist.rules[{index}]"
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: expected mapping, got {type(raw).__name__}")

    external_ids = raw.get("external_ids")
    if not isinstance(external_ids, list) or not external_ids:
        raise ConfigError(
            f"{where}.external_ids: required, must be a non-empty list of strings",
        )
    for pi, pattern in enumerate(external_ids):
        if not isinstance(pattern, str) or not pattern:
            raise ConfigError(
                f"{where}.external_ids[{pi}]: must be a non-empty string",
            )

    policy = _parse_access_level(
        raw.get("policy", "allow"),
        instance_name=instance_name,
        field=f"rules[{index}].policy",
    )

    reason_raw = raw.get("reason", "")
    if not isinstance(reason_raw, str):
        raise ConfigError(
            f"{where}.reason: expected string, got {type(reason_raw).__name__}",
        )

    return ConnectorAllowRule(
        external_ids=tuple(external_ids),
        policy=policy,
        reason=reason_raw,
    )


def _parse_access_level(
    raw: object,
    *,
    instance_name: str,
    field: str,
) -> AccessLevel:
    where = f"connectors[{instance_name}].allowlist.{field}"
    if not isinstance(raw, str):
        raise ConfigError(
            f"{where}: expected string, got {type(raw).__name__}",
        )
    try:
        level = AccessLevel(raw.lower())
    except ValueError:
        valid = ", ".join(lvl.value for lvl in AccessLevel)
        raise ConfigError(
            f"{where}: unknown value {raw!r}; must be one of {valid}",
        ) from None

    # REQUIRE_APPROVAL is a forward-compat parse target but not supported
    # by the enforcement layer today. Fail at startup with a clear message
    # so operators don't get silent allow-all behaviour.
    if level is AccessLevel.REQUIRE_APPROVAL:
        raise ConfigError(
            f"{where}: 'require_approval' is not supported for connector "
            "allowlists in this release — use 'allow' or 'deny'.",
        )

    return level


__all__ = [
    "ConnectorAllowRule",
    "ConnectorAllowlistConfig",
    "ConnectorAllowlistPolicy",
    "parse_allowlist",
]
