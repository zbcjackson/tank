"""Tests for FileAccessPolicy — rule matching, glob patterns, defaults."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tank_backend.policy.file_access import (
    AccessDecision,
    FileAccessPolicy,
    FileAccessRule,
)


# ---------------------------------------------------------------------------
# from_dict
# ---------------------------------------------------------------------------

def test_from_dict_empty():
    policy = FileAccessPolicy.from_dict({})
    decision = policy.evaluate("/tmp/foo.txt", "read")
    assert decision.level == "allow"
    assert decision.reason == "default policy"


def test_from_dict_full_config():
    policy = FileAccessPolicy.from_dict({
        "default_read": "allow",
        "default_write": "deny",
        "default_delete": "deny",
        "rules": [
            {
                "paths": ["~/.ssh/**"],
                "read": "deny",
                "write": "deny",
                "delete": "deny",
                "reason": "Secrets",
            },
        ],
    })
    # Check defaults changed
    decision = policy.evaluate("/tmp/foo.txt", "write")
    assert decision.level == "deny"
    assert decision.reason == "default policy"


def test_from_dict_partial_rule():
    """Rule with only some operations specified defaults others to 'allow'."""
    policy = FileAccessPolicy.from_dict({
        "rules": [
            {"paths": ["/etc/**"], "write": "deny", "reason": "System"},
        ],
    })
    decision = policy.evaluate("/etc/hosts", "read")
    assert decision.level == "allow"
    assert decision.reason == "System"

    decision = policy.evaluate("/etc/hosts", "write")
    assert decision.level == "deny"


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

def test_default_read_allow():
    policy = FileAccessPolicy()
    decision = policy.evaluate("/tmp/foo.txt", "read")
    assert decision.level == "allow"


def test_default_write_require_approval():
    policy = FileAccessPolicy()
    decision = policy.evaluate("/tmp/foo.txt", "write")
    assert decision.level == "require_approval"


def test_default_delete_require_approval():
    policy = FileAccessPolicy()
    decision = policy.evaluate("/tmp/foo.txt", "delete")
    assert decision.level == "require_approval"


def test_unknown_operation_denied():
    policy = FileAccessPolicy()
    decision = policy.evaluate("/tmp/foo.txt", "execute")
    assert decision.level == "deny"
    assert "unknown operation" in decision.reason


# ---------------------------------------------------------------------------
# First-match-wins ordering
# ---------------------------------------------------------------------------

def test_first_match_wins():
    policy = FileAccessPolicy(
        rules=(
            FileAccessRule(paths=("/tmp/special.txt",), read="deny", reason="special"),
            FileAccessRule(paths=("/tmp/**",), read="allow", reason="tmp"),
        ),
    )
    # /tmp/special.txt matches first rule
    decision = policy.evaluate("/tmp/special.txt", "read")
    assert decision.level == "deny"
    assert decision.reason == "special"

    # /tmp/other.txt matches second rule
    decision = policy.evaluate("/tmp/other.txt", "read")
    assert decision.level == "allow"
    assert decision.reason == "tmp"


# ---------------------------------------------------------------------------
# Tilde expansion
# ---------------------------------------------------------------------------

def test_tilde_expansion():
    home = os.path.expanduser("~")
    policy = FileAccessPolicy(
        rules=(
            FileAccessRule(paths=("~/.ssh/**",), read="deny", reason="SSH keys"),
        ),
    )
    decision = policy.evaluate(f"{home}/.ssh/id_rsa", "read")
    assert decision.level == "deny"
    assert decision.reason == "SSH keys"


def test_tilde_in_input_path():
    policy = FileAccessPolicy(
        rules=(
            FileAccessRule(paths=("~/.ssh/**",), read="deny", reason="SSH keys"),
        ),
    )
    decision = policy.evaluate("~/.ssh/id_rsa", "read")
    assert decision.level == "deny"


# ---------------------------------------------------------------------------
# ** recursive glob
# ---------------------------------------------------------------------------

def test_double_star_prefix():
    """~/.ssh/** matches anything under ~/.ssh/."""
    home = os.path.expanduser("~")
    policy = FileAccessPolicy(
        rules=(
            FileAccessRule(paths=("~/.ssh/**",), read="deny", reason="SSH"),
        ),
    )
    assert policy.evaluate(f"{home}/.ssh/id_rsa", "read").level == "deny"
    assert policy.evaluate(f"{home}/.ssh/config", "read").level == "deny"
    assert policy.evaluate(f"{home}/.ssh/keys/deploy.pem", "read").level == "deny"
    # Not under .ssh
    assert policy.evaluate(f"{home}/.bashrc", "read").level == "allow"


def test_double_star_suffix():
    """**/.env matches .env anywhere in the tree."""
    policy = FileAccessPolicy(
        rules=(
            FileAccessRule(paths=("**/.env",), read="deny", reason="env file"),
        ),
    )
    assert policy.evaluate("/home/user/project/.env", "read").level == "deny"
    assert policy.evaluate("/var/app/.env", "read").level == "deny"
    assert policy.evaluate("/home/user/.env", "read").level == "deny"


def test_double_star_with_wildcard_suffix():
    """**/*.pem matches any .pem file anywhere."""
    policy = FileAccessPolicy(
        rules=(
            FileAccessRule(paths=("**/*.pem",), read="deny", reason="PEM file"),
        ),
    )
    assert policy.evaluate("/home/user/cert.pem", "read").level == "deny"
    assert policy.evaluate("/etc/ssl/server.pem", "read").level == "deny"
    assert policy.evaluate("/home/user/cert.txt", "read").level == "allow"


def test_double_star_middle():
    """Pattern with ** in the middle: ~/projects/**/node_modules."""
    home = os.path.expanduser("~")
    policy = FileAccessPolicy(
        rules=(
            FileAccessRule(
                paths=(f"{home}/projects/**/node_modules",),
                read="deny",
                reason="node_modules",
            ),
        ),
    )
    assert policy.evaluate(f"{home}/projects/app/node_modules", "read").level == "deny"
    assert policy.evaluate(f"{home}/projects/app/sub/node_modules", "read").level == "deny"
    assert policy.evaluate(f"{home}/projects/node_modules", "read").level == "deny"


# ---------------------------------------------------------------------------
# * single-level glob
# ---------------------------------------------------------------------------

def test_single_star():
    policy = FileAccessPolicy(
        rules=(
            FileAccessRule(paths=("/tmp/*.log",), read="deny", reason="logs"),
        ),
    )
    assert policy.evaluate("/tmp/app.log", "read").level == "deny"
    assert policy.evaluate("/tmp/app.txt", "read").level == "allow"
    # * does not cross directory boundaries in fnmatch
    assert policy.evaluate("/tmp/sub/app.log", "read").level == "allow"


# ---------------------------------------------------------------------------
# Exact path
# ---------------------------------------------------------------------------

def test_exact_path():
    policy = FileAccessPolicy(
        rules=(
            FileAccessRule(paths=("/etc/passwd",), read="deny", reason="passwd"),
        ),
    )
    assert policy.evaluate("/etc/passwd", "read").level == "deny"
    assert policy.evaluate("/etc/shadow", "read").level == "allow"


# ---------------------------------------------------------------------------
# Multiple paths in one rule
# ---------------------------------------------------------------------------

def test_multiple_paths_in_rule():
    policy = FileAccessPolicy(
        rules=(
            FileAccessRule(
                paths=("~/.ssh/**", "~/.gnupg/**"),
                read="deny",
                reason="Secrets",
            ),
        ),
    )
    home = os.path.expanduser("~")
    assert policy.evaluate(f"{home}/.ssh/id_rsa", "read").level == "deny"
    assert policy.evaluate(f"{home}/.gnupg/pubring.kbx", "read").level == "deny"
    assert policy.evaluate(f"{home}/.bashrc", "read").level == "allow"


# ---------------------------------------------------------------------------
# Different operations on same rule
# ---------------------------------------------------------------------------

def test_different_operations():
    policy = FileAccessPolicy(
        rules=(
            FileAccessRule(
                paths=("/etc/**",),
                read="allow",
                write="require_approval",
                delete="deny",
                reason="System config",
            ),
        ),
    )
    assert policy.evaluate("/etc/hosts", "read").level == "allow"
    assert policy.evaluate("/etc/hosts", "write").level == "require_approval"
    assert policy.evaluate("/etc/hosts", "delete").level == "deny"


# ---------------------------------------------------------------------------
# AccessDecision
# ---------------------------------------------------------------------------

def test_access_decision_frozen():
    d = AccessDecision(level="deny", reason="test")
    assert d.level == "deny"
    assert d.reason == "test"
    with pytest.raises(AttributeError):
        d.level = "allow"  # type: ignore[misc]
