"""Tests for NetworkAccessPolicy."""

from __future__ import annotations

from tank_backend.policy.network_access import (
    NetworkAccessPolicy,
    NetworkAccessRule,
)
from tank_backend.policy.verdict import AccessLevel


class TestNetworkAccessPolicy:
    def test_default_allow(self):
        policy = NetworkAccessPolicy()
        decision = policy.evaluate("example.com")
        assert decision.level == AccessLevel.ALLOW
        assert decision.reason == "default policy"

    def test_default_deny(self):
        policy = NetworkAccessPolicy(default=AccessLevel.DENY)
        decision = policy.evaluate("example.com")
        assert decision.level == AccessLevel.DENY

    def test_exact_host_match(self):
        policy = NetworkAccessPolicy(
            rules=(
                NetworkAccessRule(
                    hosts=("pastebin.com",),
                    policy=AccessLevel.REQUIRE_APPROVAL,
                    reason="Content sharing",
                ),
            ),
        )
        decision = policy.evaluate("pastebin.com")
        assert decision.level == AccessLevel.REQUIRE_APPROVAL
        assert decision.reason == "Content sharing"

    def test_exact_host_no_match_falls_to_default(self):
        policy = NetworkAccessPolicy(
            rules=(
                NetworkAccessRule(
                    hosts=("pastebin.com",),
                    policy=AccessLevel.DENY,
                    reason="blocked",
                ),
            ),
        )
        decision = policy.evaluate("example.com")
        assert decision.level == AccessLevel.ALLOW

    def test_wildcard_host_match(self):
        policy = NetworkAccessPolicy(
            rules=(
                NetworkAccessRule(
                    hosts=("*.onion",),
                    policy=AccessLevel.DENY,
                    reason="Anonymous network",
                ),
            ),
        )
        decision = policy.evaluate("hidden.onion")
        assert decision.level == AccessLevel.DENY
        assert decision.reason == "Anonymous network"

    def test_wildcard_no_match(self):
        policy = NetworkAccessPolicy(
            rules=(
                NetworkAccessRule(
                    hosts=("*.onion",),
                    policy=AccessLevel.DENY,
                    reason="Anonymous network",
                ),
            ),
        )
        decision = policy.evaluate("example.com")
        assert decision.level == AccessLevel.ALLOW

    def test_first_match_wins(self):
        policy = NetworkAccessPolicy(
            rules=(
                NetworkAccessRule(
                    hosts=("pastebin.com",),
                    policy=AccessLevel.REQUIRE_APPROVAL,
                    reason="Content sharing",
                ),
                NetworkAccessRule(
                    hosts=("pastebin.com",),
                    policy=AccessLevel.DENY,
                    reason="Also blocked",
                ),
            ),
        )
        decision = policy.evaluate("pastebin.com")
        assert decision.level == AccessLevel.REQUIRE_APPROVAL
        assert decision.reason == "Content sharing"

    def test_multiple_hosts_in_rule(self):
        policy = NetworkAccessPolicy(
            rules=(
                NetworkAccessRule(
                    hosts=("pastebin.com", "hastebin.com", "0x0.st"),
                    policy=AccessLevel.REQUIRE_APPROVAL,
                    reason="Content sharing",
                ),
            ),
        )
        assert policy.evaluate("hastebin.com").level == AccessLevel.REQUIRE_APPROVAL
        assert policy.evaluate("0x0.st").level == AccessLevel.REQUIRE_APPROVAL
        assert policy.evaluate("github.com").level == AccessLevel.ALLOW

    def test_case_insensitive(self):
        policy = NetworkAccessPolicy(
            rules=(
                NetworkAccessRule(
                    hosts=("Pastebin.COM",),
                    policy=AccessLevel.DENY,
                    reason="blocked",
                ),
            ),
        )
        assert policy.evaluate("pastebin.com").level == AccessLevel.DENY
        assert policy.evaluate("PASTEBIN.COM").level == AccessLevel.DENY

    def test_from_dict_empty(self):
        policy = NetworkAccessPolicy.from_dict({})
        assert policy.evaluate("example.com").level == AccessLevel.ALLOW

    def test_from_dict_none(self):
        policy = NetworkAccessPolicy.from_dict(None)
        assert policy.evaluate("example.com").level == AccessLevel.ALLOW

    def test_from_dict_full(self):
        data = {
            "default": "require_approval",
            "rules": [
                {
                    "hosts": ["pastebin.com", "0x0.st"],
                    "policy": "deny",
                    "reason": "Content sharing",
                },
                {
                    "hosts": ["*.onion"],
                    "policy": "deny",
                    "reason": "Anonymous",
                },
            ],
        }
        policy = NetworkAccessPolicy.from_dict(data)
        assert policy.evaluate("pastebin.com").level == AccessLevel.DENY
        assert policy.evaluate("hidden.onion").level == AccessLevel.DENY
        assert policy.evaluate("github.com").level == AccessLevel.REQUIRE_APPROVAL

    def test_from_dict_missing_fields_use_defaults(self):
        data = {
            "rules": [
                {"hosts": ["bad.com"]},
            ],
        }
        policy = NetworkAccessPolicy.from_dict(data)
        # Rule with no policy defaults to "allow"
        assert policy.evaluate("bad.com").level == AccessLevel.ALLOW
