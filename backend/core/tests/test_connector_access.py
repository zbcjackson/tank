"""Unit tests for :mod:`tank_backend.policy.connector_access`.

Covers the policy's first-match-wins semantics, fnmatch glob behaviour,
audit-bus publication, and the parser's input validation (including the
explicit ``REQUIRE_APPROVAL``-not-supported rejection).
"""

from __future__ import annotations

import pytest
from tank_contracts.connector import Identity

from tank_backend.config.parser import ConfigError
from tank_backend.pipeline.bus import Bus, BusMessage
from tank_backend.policy.connector_access import (
    ConnectorAllowlistConfig,
    ConnectorAllowlistPolicy,
    ConnectorAllowRule,
    parse_allowlist,
)
from tank_backend.policy.verdict import AccessLevel, PolicyVerdict


def _identity(
    *,
    platform: str = "telegram",
    external_id: str = "tg:user:42",
    display_name: str = "Alice",
    is_group: bool = False,
) -> Identity:
    return Identity(
        platform=platform,
        external_id=external_id,
        display_name=display_name,
        is_group=is_group,
    )


# ---------------------------------------------------------------------------
# ConnectorAllowlistPolicy.evaluate()
# ---------------------------------------------------------------------------


class TestPolicyEvaluate:
    def test_default_allow_when_no_rules(self) -> None:
        policy = ConnectorAllowlistPolicy(
            ConnectorAllowlistConfig(),
            instance_name="bot",
        )
        verdict = policy.evaluate(_identity())
        assert verdict.level is AccessLevel.ALLOW
        assert verdict.reason == "no matching rule; using default"
        assert verdict.policy == "connector_access"

    def test_default_deny_blocks_everything(self) -> None:
        policy = ConnectorAllowlistPolicy(
            ConnectorAllowlistConfig(default=AccessLevel.DENY),
            instance_name="bot",
        )
        assert policy.evaluate(_identity()).level is AccessLevel.DENY

    def test_exact_match_allows(self) -> None:
        policy = ConnectorAllowlistPolicy(
            ConnectorAllowlistConfig(
                default=AccessLevel.DENY,
                rules=(
                    ConnectorAllowRule(
                        external_ids=("tg:user:42",),
                        policy=AccessLevel.ALLOW,
                        reason="alice",
                    ),
                ),
            ),
            instance_name="bot",
        )
        verdict = policy.evaluate(_identity(external_id="tg:user:42"))
        assert verdict.level is AccessLevel.ALLOW
        assert verdict.reason == "alice"
        assert verdict.context["matched_pattern"] == "tg:user:42"

    def test_non_matching_identity_falls_through_to_default(self) -> None:
        policy = ConnectorAllowlistPolicy(
            ConnectorAllowlistConfig(
                default=AccessLevel.DENY,
                rules=(
                    ConnectorAllowRule(
                        external_ids=("tg:user:42",),
                        policy=AccessLevel.ALLOW,
                    ),
                ),
            ),
            instance_name="bot",
        )
        assert policy.evaluate(
            _identity(external_id="tg:user:99"),
        ).level is AccessLevel.DENY

    def test_first_match_wins_in_rule_order(self) -> None:
        """When two rules match, the earlier one dictates the verdict.

        Operators rely on rule order to express exceptions: an early
        ALLOW for a specific user overrides a later broad DENY. This
        test pins the ordering contract.
        """
        policy = ConnectorAllowlistPolicy(
            ConnectorAllowlistConfig(
                default=AccessLevel.DENY,
                rules=(
                    ConnectorAllowRule(
                        external_ids=("tg:user:42",),
                        policy=AccessLevel.ALLOW,
                        reason="specific carve-out",
                    ),
                    ConnectorAllowRule(
                        external_ids=("tg:user:*",),
                        policy=AccessLevel.DENY,
                        reason="ban all DMs",
                    ),
                ),
            ),
            instance_name="bot",
        )
        assert policy.evaluate(
            _identity(external_id="tg:user:42"),
        ).reason == "specific carve-out"
        assert policy.evaluate(
            _identity(external_id="tg:user:99"),
        ).reason == "ban all DMs"

    def test_glob_patterns_match_fnmatch_semantics(self) -> None:
        policy = ConnectorAllowlistPolicy(
            ConnectorAllowlistConfig(
                default=AccessLevel.DENY,
                rules=(
                    ConnectorAllowRule(
                        external_ids=("tg:chat:-100*",),
                        policy=AccessLevel.ALLOW,
                    ),
                ),
            ),
            instance_name="bot",
        )
        # Supergroup id matches.
        assert policy.evaluate(
            _identity(external_id="tg:chat:-1001234567"),
        ).level is AccessLevel.ALLOW
        # Private chat doesn't.
        assert policy.evaluate(
            _identity(external_id="tg:chat:12345"),
        ).level is AccessLevel.DENY

    def test_pattern_match_is_case_sensitive(self) -> None:
        """Identity strings from platforms are already lowercase-safe,
        so glob matching is case-sensitive — a typo like ``TG:USER:*``
        won't accidentally match real ids."""
        policy = ConnectorAllowlistPolicy(
            ConnectorAllowlistConfig(
                default=AccessLevel.DENY,
                rules=(
                    ConnectorAllowRule(
                        external_ids=("TG:USER:*",),
                        policy=AccessLevel.ALLOW,
                    ),
                ),
            ),
            instance_name="bot",
        )
        assert policy.evaluate(
            _identity(external_id="tg:user:42"),
        ).level is AccessLevel.DENY

    def test_verdict_context_carries_identity_fields(self) -> None:
        policy = ConnectorAllowlistPolicy(
            ConnectorAllowlistConfig(default=AccessLevel.DENY),
            instance_name="my-bot",
        )
        verdict = policy.evaluate(
            _identity(
                platform="telegram",
                external_id="tg:user:99",
                display_name="Bob",
            ),
        )
        assert verdict.context["connector"] == "my-bot"
        assert verdict.context["platform"] == "telegram"
        assert verdict.context["external_id"] == "tg:user:99"
        assert verdict.context["display_name"] == "Bob"

    def test_admin_always_allowed_even_under_deny_default(self) -> None:
        """Admins must be reachable even when not explicitly listed in allow
        rules. Without this, a ``default: deny`` config would lock the admin
        out and make the approval workflow deadlock."""
        policy = ConnectorAllowlistPolicy(
            ConnectorAllowlistConfig(
                default=AccessLevel.DENY,
                admin_external_ids=("tg:user:42",),
            ),
            instance_name="bot",
        )
        verdict = policy.evaluate(_identity(external_id="tg:user:42"))
        assert verdict.level is AccessLevel.ALLOW
        assert verdict.reason == "admin identity"
        assert verdict.context["matched_pattern"] == "<admin>"

    def test_admin_always_allowed_under_require_approval_default(self) -> None:
        """REQUIRE_APPROVAL default must not create an approval deadlock for
        the admin itself."""
        policy = ConnectorAllowlistPolicy(
            ConnectorAllowlistConfig(
                default=AccessLevel.REQUIRE_APPROVAL,
                admin_external_ids=("tg:user:42",),
            ),
            instance_name="bot",
        )
        assert policy.evaluate(
            _identity(external_id="tg:user:42"),
        ).level is AccessLevel.ALLOW

    def test_non_admin_still_subject_to_rules(self) -> None:
        """Admin short-circuit must not affect non-admin identities."""
        policy = ConnectorAllowlistPolicy(
            ConnectorAllowlistConfig(
                default=AccessLevel.DENY,
                admin_external_ids=("tg:user:42",),
            ),
            instance_name="bot",
        )
        assert policy.evaluate(
            _identity(external_id="tg:user:99"),
        ).level is AccessLevel.DENY


# ---------------------------------------------------------------------------
# Bus publication (the audit hook)
# ---------------------------------------------------------------------------


class TestBusPublication:
    def test_decision_posts_to_bus_when_wired(self) -> None:
        bus = Bus()
        received: list[BusMessage] = []
        bus.subscribe("connector_access_decision", received.append)

        policy = ConnectorAllowlistPolicy(
            ConnectorAllowlistConfig(default=AccessLevel.DENY),
            instance_name="bot",
            bus=bus,
        )
        policy.evaluate(_identity())
        bus.poll()

        assert len(received) == 1
        verdict = received[0].payload["verdict"]
        assert isinstance(verdict, PolicyVerdict)
        assert verdict.level is AccessLevel.DENY
        assert received[0].source == "ConnectorAllowlistPolicy"

    def test_no_post_when_bus_absent(self) -> None:
        """Bus is optional — the policy is usable in unit tests / scripts
        without a full pipeline plumbed in."""
        policy = ConnectorAllowlistPolicy(
            ConnectorAllowlistConfig(default=AccessLevel.DENY),
            instance_name="bot",
        )
        # Should not raise.
        verdict = policy.evaluate(_identity())
        assert verdict.level is AccessLevel.DENY

    def test_both_allow_and_deny_get_audited(self) -> None:
        """Audit log records every decision, not just denials — needed
        for demonstrating ALLOW traffic under compliance review."""
        bus = Bus()
        received: list[BusMessage] = []
        bus.subscribe("connector_access_decision", received.append)

        policy = ConnectorAllowlistPolicy(
            ConnectorAllowlistConfig(
                default=AccessLevel.DENY,
                rules=(
                    ConnectorAllowRule(
                        external_ids=("tg:user:42",),
                        policy=AccessLevel.ALLOW,
                    ),
                ),
            ),
            instance_name="bot",
            bus=bus,
        )
        policy.evaluate(_identity(external_id="tg:user:42"))  # allow
        policy.evaluate(_identity(external_id="tg:user:99"))  # deny (default)
        bus.poll()

        assert [m.payload["verdict"].level for m in received] == [
            AccessLevel.ALLOW,
            AccessLevel.DENY,
        ]


# ---------------------------------------------------------------------------
# parse_allowlist()
# ---------------------------------------------------------------------------


class TestParseAllowlist:
    def test_none_returns_allow_all(self) -> None:
        cfg = parse_allowlist(None, instance_name="bot")
        assert cfg.default is AccessLevel.ALLOW
        assert cfg.rules == ()

    def test_empty_dict_returns_allow_all(self) -> None:
        cfg = parse_allowlist({}, instance_name="bot")
        assert cfg.default is AccessLevel.ALLOW
        assert cfg.rules == ()

    def test_default_deny_and_explicit_rules(self) -> None:
        cfg = parse_allowlist(
            {
                "default": "deny",
                "rules": [
                    {
                        "external_ids": ["tg:user:42", "tg:user:99"],
                        "policy": "allow",
                        "reason": "team",
                    },
                ],
            },
            instance_name="bot",
        )
        assert cfg.default is AccessLevel.DENY
        assert len(cfg.rules) == 1
        rule = cfg.rules[0]
        assert rule.external_ids == ("tg:user:42", "tg:user:99")
        assert rule.policy is AccessLevel.ALLOW
        assert rule.reason == "team"

    def test_default_policy_on_rule_falls_back_to_allow(self) -> None:
        """Rules without an explicit ``policy:`` default to ALLOW — matches
        the natural reading of 'allowlist'."""
        cfg = parse_allowlist(
            {"rules": [{"external_ids": ["tg:user:42"]}]},
            instance_name="bot",
        )
        assert cfg.rules[0].policy is AccessLevel.ALLOW

    def test_require_approval_parses_as_default(self) -> None:
        """Phase 10: ``require_approval`` is a valid ``default`` — the
        manager routes REQUIRE_APPROVAL verdicts through an
        :class:`ApprovalBroker` when admins are configured, or fails
        closed at runtime when they aren't. Pin the parse contract so
        accidental re-introduction of the Phase-6 rejection is caught."""
        cfg = parse_allowlist(
            {"default": "require_approval"},
            instance_name="bot",
        )
        assert cfg.default is AccessLevel.REQUIRE_APPROVAL

    def test_require_approval_parses_on_rule_policy(self) -> None:
        cfg = parse_allowlist(
            {
                "rules": [{
                    "external_ids": ["tg:user:*"],
                    "policy": "require_approval",
                }],
            },
            instance_name="bot",
        )
        assert len(cfg.rules) == 1
        assert cfg.rules[0].policy is AccessLevel.REQUIRE_APPROVAL

    def test_unknown_access_level_raises(self) -> None:
        with pytest.raises(ConfigError, match="unknown value"):
            parse_allowlist(
                {"default": "maybe"},
                instance_name="bot",
            )

    def test_external_ids_required(self) -> None:
        with pytest.raises(ConfigError, match="external_ids"):
            parse_allowlist(
                {"rules": [{"policy": "allow"}]},
                instance_name="bot",
            )

    def test_external_ids_empty_list_rejected(self) -> None:
        with pytest.raises(ConfigError, match="non-empty"):
            parse_allowlist(
                {"rules": [{"external_ids": []}]},
                instance_name="bot",
            )

    def test_external_ids_non_string_rejected(self) -> None:
        with pytest.raises(ConfigError, match="non-empty string"):
            parse_allowlist(
                {"rules": [{"external_ids": ["tg:user:1", 42]}]},
                instance_name="bot",
            )

    def test_top_level_non_mapping_rejected(self) -> None:
        with pytest.raises(ConfigError, match="expected mapping"):
            parse_allowlist("not-a-dict", instance_name="bot")

    def test_rules_non_list_rejected(self) -> None:
        with pytest.raises(ConfigError, match="expected list"):
            parse_allowlist({"rules": "nope"}, instance_name="bot")

    def test_rule_non_mapping_rejected(self) -> None:
        with pytest.raises(ConfigError, match="expected mapping"):
            parse_allowlist(
                {"rules": ["not-a-mapping"]},
                instance_name="bot",
            )

    def test_error_messages_include_instance_name(self) -> None:
        """Operators must be able to locate the bad block in config.yaml
        — the instance name is the most specific anchor available at
        parse time."""
        with pytest.raises(ConfigError, match="my-tg-bot"):
            parse_allowlist(
                {"default": "maybe"},
                instance_name="my-tg-bot",
            )
