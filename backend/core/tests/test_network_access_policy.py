"""Tests for NetworkAccessPolicy."""

from __future__ import annotations

from tank_backend.config.models import NetworkAccessConfig, NetworkAccessRuleConfig
from tank_backend.policy.network_access import (
    NetworkAccessPolicy,
)
from tank_backend.policy.verdict import AccessLevel


def _policy(
    default: AccessLevel = AccessLevel.ALLOW,
    rules: tuple[NetworkAccessRuleConfig, ...] = (),
) -> NetworkAccessPolicy:
    return NetworkAccessPolicy(NetworkAccessConfig(default=default, rules=rules))


class TestNetworkAccessPolicy:
    def test_default_allow(self):
        policy = _policy()
        decision = policy.evaluate("example.com")
        assert decision.level == AccessLevel.ALLOW
        assert decision.reason == "default policy"

    def test_default_deny(self):
        policy = _policy(default=AccessLevel.DENY)
        decision = policy.evaluate("example.com")
        assert decision.level == AccessLevel.DENY

    def test_exact_host_match(self):
        policy = _policy(rules=(
            NetworkAccessRuleConfig(
                hosts=("pastebin.com",),
                policy=AccessLevel.REQUIRE_APPROVAL,
                reason="Content sharing",
            ),
        ))
        decision = policy.evaluate("pastebin.com")
        assert decision.level == AccessLevel.REQUIRE_APPROVAL
        assert decision.reason == "Content sharing"

    def test_exact_host_no_match_falls_to_default(self):
        policy = _policy(rules=(
            NetworkAccessRuleConfig(
                hosts=("pastebin.com",),
                policy=AccessLevel.DENY,
                reason="blocked",
            ),
        ))
        decision = policy.evaluate("example.com")
        assert decision.level == AccessLevel.ALLOW

    def test_wildcard_host_match(self):
        policy = _policy(rules=(
            NetworkAccessRuleConfig(
                hosts=("*.onion",),
                policy=AccessLevel.DENY,
                reason="Anonymous network",
            ),
        ))
        decision = policy.evaluate("hidden.onion")
        assert decision.level == AccessLevel.DENY
        assert decision.reason == "Anonymous network"

    def test_wildcard_no_match(self):
        policy = _policy(rules=(
            NetworkAccessRuleConfig(
                hosts=("*.onion",),
                policy=AccessLevel.DENY,
                reason="Anonymous network",
            ),
        ))
        decision = policy.evaluate("example.com")
        assert decision.level == AccessLevel.ALLOW

    def test_first_match_wins(self):
        policy = _policy(rules=(
            NetworkAccessRuleConfig(
                hosts=("pastebin.com",),
                policy=AccessLevel.REQUIRE_APPROVAL,
                reason="Content sharing",
            ),
            NetworkAccessRuleConfig(
                hosts=("pastebin.com",),
                policy=AccessLevel.DENY,
                reason="Also blocked",
            ),
        ))
        decision = policy.evaluate("pastebin.com")
        assert decision.level == AccessLevel.REQUIRE_APPROVAL
        assert decision.reason == "Content sharing"

    def test_multiple_hosts_in_rule(self):
        policy = _policy(rules=(
            NetworkAccessRuleConfig(
                hosts=("pastebin.com", "hastebin.com", "0x0.st"),
                policy=AccessLevel.REQUIRE_APPROVAL,
                reason="Content sharing",
            ),
        ))
        assert policy.evaluate("hastebin.com").level == AccessLevel.REQUIRE_APPROVAL
        assert policy.evaluate("0x0.st").level == AccessLevel.REQUIRE_APPROVAL
        assert policy.evaluate("github.com").level == AccessLevel.ALLOW

    def test_case_insensitive(self):
        policy = _policy(rules=(
            NetworkAccessRuleConfig(
                hosts=("Pastebin.COM",),
                policy=AccessLevel.DENY,
                reason="blocked",
            ),
        ))
        assert policy.evaluate("pastebin.com").level == AccessLevel.DENY
        assert policy.evaluate("PASTEBIN.COM").level == AccessLevel.DENY

    def test_config_empty(self):
        policy = _policy()
        assert policy.evaluate("example.com").level == AccessLevel.ALLOW

    def test_config_full(self):
        policy = _policy(
            default=AccessLevel.REQUIRE_APPROVAL,
            rules=(
                NetworkAccessRuleConfig(
                    hosts=("pastebin.com", "0x0.st"),
                    policy=AccessLevel.DENY,
                    reason="Content sharing",
                ),
                NetworkAccessRuleConfig(
                    hosts=("*.onion",),
                    policy=AccessLevel.DENY,
                    reason="Anonymous",
                ),
            ),
        )
        assert policy.evaluate("pastebin.com").level == AccessLevel.DENY
        assert policy.evaluate("hidden.onion").level == AccessLevel.DENY
        assert policy.evaluate("github.com").level == AccessLevel.REQUIRE_APPROVAL

    def test_config_missing_fields_use_defaults(self):
        policy = _policy(rules=(
            NetworkAccessRuleConfig(hosts=("bad.com",)),
        ))
        # Rule with no policy defaults to "allow"
        assert policy.evaluate("bad.com").level == AccessLevel.ALLOW
