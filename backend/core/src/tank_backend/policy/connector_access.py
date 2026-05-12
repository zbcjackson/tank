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

    from ..connectors.dynamic_allowlist import DynamicAllowlistStore
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

    Phase 10 additions:

    - ``admin_external_ids``: identities on this connector who receive
      approval prompts when an unknown sender triggers a
      ``REQUIRE_APPROVAL`` verdict. Leave empty to disable the approval
      workflow (``REQUIRE_APPROVAL`` verdicts then fail closed with a
      warning in logs).
    - ``pending_reply``: optional override for the text sent to the
      unknown sender while they wait on the admin's decision.
    """

    default: AccessLevel = AccessLevel.ALLOW
    rules: tuple[ConnectorAllowRule, ...] = ()
    admin_external_ids: tuple[str, ...] = ()
    pending_reply: str | None = None


# ---------------------------------------------------------------------------
# Runtime policy
# ---------------------------------------------------------------------------


class ConnectorAllowlistPolicy:
    """Evaluate connector inbound identities against an allowlist.

    First-match-wins across ``rules``; falls back to ``default`` if no
    rule matches. Decisions are published as ``connector_access_decision``
    Bus messages when a :class:`Bus` is wired in — the
    :class:`AuditLogger` subscribes and records them.

    Phase 10 adds a runtime-grant short-circuit: when a
    :class:`~tank_backend.connectors.dynamic_allowlist.DynamicAllowlistStore`
    is wired in, it's consulted *before* the rule scan. An admin-granted
    identity (via the approval-prompt "Allow forever" button) bypasses
    all configured rules — the dynamic table is the single source of
    truth for post-approval allows.

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
        dynamic_store: DynamicAllowlistStore | None = None,
    ) -> None:
        self._default = config.default
        self._rules = config.rules
        self._admin_external_ids: frozenset[str] = frozenset(
            config.admin_external_ids,
        )
        self._pending_reply = config.pending_reply
        self._instance_name = instance_name
        self._bus = bus
        self._dynamic_store = dynamic_store

    @property
    def instance_name(self) -> str:
        return self._instance_name

    @property
    def admin_external_ids(self) -> frozenset[str]:
        """Read-only view of the configured admin identities.

        Exposed so :class:`ConnectorManager` can discover admins when it
        wires up the approval broker at startup, without re-parsing the
        config dict.
        """
        return self._admin_external_ids

    @property
    def pending_reply(self) -> str | None:
        """Operator-configured "please wait" text; ``None`` means use
        the framework default."""
        return self._pending_reply

    def evaluate(self, identity: Identity) -> PolicyVerdict:
        """Return the verdict for ``identity``.

        Posts a ``connector_access_decision`` Bus event when a ``bus``
        was provided at construction. Callers should use the returned
        verdict's ``level`` to decide behaviour; the Bus post is for
        audit, not control flow.

        Phase 10: a :class:`DynamicAllowlistStore` hit short-circuits
        the rule scan. The dynamic table records admin-granted allows
        (``Allow forever`` button clicks) and is the single source of
        truth for post-approval access — config rules are the
        operator's policy, dynamic rows are the admin's runtime grants.
        """
        # Phase 10 short-circuit: admin identities always get ALLOW so they
        # can reach the assistant even when not listed in the allow rules.
        # Without this, a default of DENY/REQUIRE_APPROVAL would lock the
        # admin out and make the approval workflow deadlock.
        if identity.external_id in self._admin_external_ids:
            verdict = PolicyVerdict(
                level=AccessLevel.ALLOW,
                reason="admin identity",
                policy="connector_access",
                context={
                    "connector": self._instance_name,
                    "platform": identity.platform,
                    "external_id": identity.external_id,
                    "display_name": identity.display_name,
                    "matched_pattern": "<admin>",
                },
            )
            self._publish(verdict)
            return verdict

        # Phase 10 short-circuit: admin-granted (persisted) allow.
        if self._dynamic_store is not None and self._dynamic_store.has(
            instance_name=self._instance_name,
            platform=identity.platform,
            external_id=identity.external_id,
        ):
            verdict = PolicyVerdict(
                level=AccessLevel.ALLOW,
                reason="dynamic allowlist",
                policy="connector_access",
                context={
                    "connector": self._instance_name,
                    "platform": identity.platform,
                    "external_id": identity.external_id,
                    "display_name": identity.display_name,
                    "matched_pattern": "<dynamic>",
                },
            )
            self._publish(verdict)
            return verdict

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

    Phase 10: ``REQUIRE_APPROVAL`` is now a valid ``default`` / ``policy``
    value. Operators who use it must also populate
    ``admin_external_ids`` — otherwise a ``REQUIRE_APPROVAL`` verdict
    has nowhere to send the prompt, and the manager fails closed with
    a warning in logs. ``admin_external_ids`` and ``pending_reply`` are
    both optional; leaving them unset preserves pre-Phase-10 shape.
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

    admin_external_ids = _parse_admin_external_ids(
        raw.get("admin_external_ids"),
        instance_name=instance_name,
    )

    pending_reply_raw = raw.get("pending_reply")
    pending_reply: str | None = None
    if pending_reply_raw is not None:
        if not isinstance(pending_reply_raw, str):
            raise ConfigError(
                f"connectors[{instance_name}].allowlist.pending_reply: "
                f"expected string, got {type(pending_reply_raw).__name__}",
            )
        pending_reply = pending_reply_raw

    return ConnectorAllowlistConfig(
        default=default,
        rules=tuple(rules),
        admin_external_ids=admin_external_ids,
        pending_reply=pending_reply,
    )


def _parse_admin_external_ids(
    raw: object | None, *, instance_name: str,
) -> tuple[str, ...]:
    """Parse the optional ``admin_external_ids`` list.

    Missing / empty list → empty tuple; a non-empty list of strings is
    returned verbatim. Non-string entries raise :class:`ConfigError`
    with a descriptive message so operators can locate the bad entry.
    """
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ConfigError(
            f"connectors[{instance_name}].allowlist.admin_external_ids: "
            f"expected list, got {type(raw).__name__}",
        )
    result: list[str] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, str) or not entry:
            raise ConfigError(
                f"connectors[{instance_name}].allowlist."
                f"admin_external_ids[{i}]: must be a non-empty string",
            )
        result.append(entry)
    return tuple(result)


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

    # Phase 10: REQUIRE_APPROVAL is accepted as a real verdict. The
    # manager handles it by routing through :class:`ApprovalBroker`
    # when ``admin_external_ids`` is set, and fails closed (deny + log)
    # when it isn't — the config parser deliberately doesn't enforce
    # "if REQUIRE_APPROVAL then admin_external_ids must be non-empty"
    # so operators can stage the change in two steps (declare the
    # default first, add admins next) without a chicken-and-egg
    # validation failure.
    return level


__all__ = [
    "ConnectorAllowRule",
    "ConnectorAllowlistConfig",
    "ConnectorAllowlistPolicy",
    "parse_allowlist",
]
