"""Tests for ServiceCredentialManager."""

from __future__ import annotations

import os
from unittest.mock import patch

from tank_backend.config.models import ServiceCredentialConfig
from tank_backend.policy.credentials import ServiceCredentialManager


class TestServiceCredentialManager:
    def test_empty_manager(self):
        mgr = ServiceCredentialManager()
        assert mgr.get_env_for_sandbox() == {}
        assert mgr.get_credential("serper") is None
        assert mgr.validate_host("example.com", "serper") is False
        assert mgr.available_services == []

    def test_get_env_for_sandbox_returns_set_vars(self):
        mgr = ServiceCredentialManager(
            credentials=(
                ServiceCredentialConfig(
                    name="serper",
                    env_var="SERPER_API_KEY",
                    allowed_hosts=("google.serper.dev",),
                ),
                ServiceCredentialConfig(
                    name="github",
                    env_var="GITHUB_TOKEN",
                    allowed_hosts=("api.github.com",),
                ),
            ),
        )
        with patch.dict(os.environ, {"SERPER_API_KEY": "sk-123"}, clear=False):
            env = mgr.get_env_for_sandbox()
            assert env == {"SERPER_API_KEY": "sk-123"}
            # GITHUB_TOKEN not set → not included

    def test_get_env_for_sandbox_both_set(self):
        mgr = ServiceCredentialManager(
            credentials=(
                ServiceCredentialConfig(name="a", env_var="A_KEY", allowed_hosts=()),
                ServiceCredentialConfig(name="b", env_var="B_KEY", allowed_hosts=()),
            ),
        )
        with patch.dict(os.environ, {"A_KEY": "aaa", "B_KEY": "bbb"}, clear=False):
            env = mgr.get_env_for_sandbox()
            assert env == {"A_KEY": "aaa", "B_KEY": "bbb"}

    def test_validate_host_exact_match(self):
        mgr = ServiceCredentialManager(
            credentials=(
                ServiceCredentialConfig(
                    name="serper",
                    env_var="SERPER_API_KEY",
                    allowed_hosts=("google.serper.dev",),
                ),
            ),
        )
        assert mgr.validate_host("google.serper.dev", "serper") is True
        assert mgr.validate_host("evil.com", "serper") is False

    def test_validate_host_wildcard(self):
        mgr = ServiceCredentialManager(
            credentials=(
                ServiceCredentialConfig(
                    name="github",
                    env_var="GITHUB_TOKEN",
                    allowed_hosts=("*.github.com",),
                ),
            ),
        )
        assert mgr.validate_host("api.github.com", "github") is True
        assert mgr.validate_host("github.com", "github") is False  # no subdomain

    def test_validate_host_unknown_credential(self):
        mgr = ServiceCredentialManager(
            credentials=(
                ServiceCredentialConfig(name="serper", env_var="X", allowed_hosts=("a.com",)),
            ),
        )
        assert mgr.validate_host("a.com", "unknown") is False

    def test_validate_host_case_insensitive(self):
        mgr = ServiceCredentialManager(
            credentials=(
                ServiceCredentialConfig(
                    name="s", env_var="X", allowed_hosts=("API.GitHub.COM",),
                ),
            ),
        )
        assert mgr.validate_host("api.github.com", "s") is True

    def test_get_credential_returns_env_value(self):
        mgr = ServiceCredentialManager(
            credentials=(
                ServiceCredentialConfig(name="serper", env_var="SERPER_API_KEY", allowed_hosts=()),
            ),
        )
        with patch.dict(os.environ, {"SERPER_API_KEY": "sk-test"}, clear=False):
            assert mgr.get_credential("serper") == "sk-test"

    def test_get_credential_returns_none_when_not_set(self):
        mgr = ServiceCredentialManager(
            credentials=(
                ServiceCredentialConfig(name="serper", env_var="SERPER_API_KEY", allowed_hosts=()),
            ),
        )
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SERPER_API_KEY", None)
            assert mgr.get_credential("serper") is None

    def test_get_credential_unknown_name(self):
        mgr = ServiceCredentialManager()
        assert mgr.get_credential("unknown") is None

    def test_available_services(self):
        mgr = ServiceCredentialManager(
            credentials=(
                ServiceCredentialConfig(name="serper", env_var="SERPER_API_KEY", allowed_hosts=()),
                ServiceCredentialConfig(name="github", env_var="GITHUB_TOKEN", allowed_hosts=()),
            ),
        )
        with patch.dict(os.environ, {"SERPER_API_KEY": "sk-123"}, clear=False):
            os.environ.pop("GITHUB_TOKEN", None)
            services = mgr.available_services
            assert "serper" in services
            assert "github" not in services

    def test_config_empty(self):
        mgr = ServiceCredentialManager(())
        assert mgr.get_env_for_sandbox() == {}
        assert mgr.available_services == []

    def test_config_full(self):
        mgr = ServiceCredentialManager(
            credentials=(
                ServiceCredentialConfig(
                    name="serper",
                    env_var="SERPER_API_KEY",
                    allowed_hosts=("google.serper.dev", "*.serper.com"),
                ),
            ),
        )
        with patch.dict(os.environ, {"SERPER_API_KEY": "sk-123"}, clear=False):
            assert mgr.validate_host("google.serper.dev", "serper") is True
            assert mgr.get_credential("serper") == "sk-123"
