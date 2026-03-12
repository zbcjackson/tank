"""Tests for SandboxFactory — backend detection and construction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tank_backend.sandbox.factory import SandboxBackendUnavailable, SandboxFactory
from tank_backend.sandbox.policy import NetworkPolicy, SandboxPolicy
from tank_backend.sandbox.protocol import Sandbox

MODULE = "tank_backend.sandbox.factory"


@pytest.fixture(autouse=True)
def _clear_probe_cache():
    """Reset the class-level probe cache between tests."""
    SandboxFactory._probe_cache.clear()
    yield
    SandboxFactory._probe_cache.clear()


# ── Detection order ───────────────────────────────────────────────


class TestDetectionOrder:
    @patch(f"{MODULE}.platform.system", return_value="Darwin")
    def test_darwin_prefers_seatbelt(self, _mock):
        order = SandboxFactory._detection_order()
        assert order == ["seatbelt", "docker"]

    @patch(f"{MODULE}.platform.system", return_value="Linux")
    def test_linux_prefers_bubblewrap(self, _mock):
        order = SandboxFactory._detection_order()
        assert order == ["bubblewrap", "docker"]

    @patch(f"{MODULE}.platform.system", return_value="Windows")
    def test_windows_falls_back_to_docker(self, _mock):
        order = SandboxFactory._detection_order()
        assert order == ["docker"]


# ── Probing ───────────────────────────────────────────────────────


class TestProbing:
    @patch(f"{MODULE}.shutil.which", return_value="/usr/bin/sandbox-exec")
    def test_seatbelt_available(self, _mock):
        assert SandboxFactory._probe("seatbelt") is True

    @patch(f"{MODULE}.shutil.which", return_value=None)
    def test_seatbelt_unavailable(self, _mock):
        assert SandboxFactory._probe("seatbelt") is False

    @patch(f"{MODULE}.shutil.which", return_value="/usr/bin/bwrap")
    def test_bubblewrap_available(self, _mock):
        assert SandboxFactory._probe("bubblewrap") is True

    @patch(f"{MODULE}.shutil.which", return_value=None)
    def test_bubblewrap_unavailable(self, _mock):
        assert SandboxFactory._probe("bubblewrap") is False

    def test_unknown_backend_returns_false(self):
        assert SandboxFactory._probe("unknown") is False

    def test_probe_cache_is_used(self):
        SandboxFactory._probe_cache["seatbelt"] = True
        assert SandboxFactory._is_available("seatbelt") is True

    @patch(f"{MODULE}.shutil.which", return_value=None)
    def test_probe_cache_populated_on_first_check(self, _mock):
        assert SandboxFactory._is_available("seatbelt") is False
        assert "seatbelt" in SandboxFactory._probe_cache


# ── Backend resolution ────────────────────────────────────────────


class TestResolveBackend:
    @patch(f"{MODULE}.shutil.which", return_value="/usr/bin/sandbox-exec")
    def test_explicit_seatbelt(self, _mock):
        assert SandboxFactory._resolve_backend("seatbelt") == "seatbelt"

    @patch(f"{MODULE}.shutil.which", return_value=None)
    def test_explicit_unavailable_raises(self, _mock):
        with pytest.raises(SandboxBackendUnavailable, match="seatbelt"):
            SandboxFactory._resolve_backend("seatbelt")

    @patch(f"{MODULE}.platform.system", return_value="Darwin")
    @patch(f"{MODULE}.shutil.which", return_value="/usr/bin/sandbox-exec")
    def test_auto_selects_seatbelt_on_macos(self, _which, _sys):
        assert SandboxFactory._resolve_backend("auto") == "seatbelt"

    @patch(f"{MODULE}.platform.system", return_value="Linux")
    @patch(f"{MODULE}.shutil.which", return_value="/usr/bin/bwrap")
    def test_auto_selects_bubblewrap_on_linux(self, _which, _sys):
        assert SandboxFactory._resolve_backend("auto") == "bubblewrap"

    @patch(f"{MODULE}.platform.system", return_value="Linux")
    @patch(f"{MODULE}.shutil.which", return_value=None)
    def test_auto_no_backend_raises(self, _which, _sys):
        # Docker probe also fails (no docker module)
        with patch.dict("sys.modules", {"docker": None}), pytest.raises(
            SandboxBackendUnavailable, match="No sandbox backend"
        ):
            SandboxFactory._resolve_backend("auto")


# ── Factory.create ────────────────────────────────────────────────


class TestCreate:
    @patch(f"{MODULE}.platform.system", return_value="Darwin")
    @patch(f"{MODULE}.shutil.which", return_value="/usr/bin/sandbox-exec")
    def test_create_seatbelt(self, _which, _sys):
        policy = SandboxPolicy(backend="auto")
        sandbox = SandboxFactory.create(policy)
        assert isinstance(sandbox, Sandbox)
        assert sandbox.is_running is True

    @patch(f"{MODULE}.platform.system", return_value="Linux")
    @patch(f"{MODULE}.shutil.which", return_value="/usr/bin/bwrap")
    def test_create_bubblewrap(self, _which, _sys):
        policy = SandboxPolicy(backend="auto")
        sandbox = SandboxFactory.create(policy)
        assert isinstance(sandbox, Sandbox)
        assert sandbox.is_running is True

    @patch(f"{MODULE}.shutil.which", return_value="/usr/bin/sandbox-exec")
    def test_create_explicit_seatbelt(self, _mock):
        policy = SandboxPolicy(backend="seatbelt")
        sandbox = SandboxFactory.create(policy)
        from tank_backend.sandbox.backends.seatbelt import SeatbeltSandbox

        assert isinstance(sandbox, SeatbeltSandbox)

    @patch(f"{MODULE}.shutil.which", return_value="/usr/bin/bwrap")
    def test_create_explicit_bubblewrap(self, _mock):
        policy = SandboxPolicy(backend="bubblewrap")
        sandbox = SandboxFactory.create(policy)
        from tank_backend.sandbox.backends.bubblewrap import BubblewrapSandbox

        assert isinstance(sandbox, BubblewrapSandbox)

    def test_create_explicit_docker(self):
        mock_docker = MagicMock()
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_client.ping.return_value = True

        with patch.dict("sys.modules", {"docker": mock_docker}):
            policy = SandboxPolicy(backend="docker")
            sandbox = SandboxFactory.create(policy)
            from tank_backend.sandbox.manager import SandboxManager

            assert isinstance(sandbox, SandboxManager)

    def test_policy_values_propagated_to_docker(self):
        mock_docker = MagicMock()
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_client.ping.return_value = True

        with patch.dict("sys.modules", {"docker": mock_docker}):
            policy = SandboxPolicy(
                backend="docker",
                memory_limit="2g",
                cpu_count=4,
                timeout=60,
                max_timeout=300,
                network=NetworkPolicy(mode="none"),
            )
            sandbox = SandboxFactory.create(policy)
            assert sandbox._config.memory_limit == "2g"
            assert sandbox._config.cpu_count == 4
            assert sandbox._config.default_timeout == 60
            assert sandbox._config.max_timeout == 300
            assert sandbox._config.network_enabled is False


# ── SandboxPolicy ─────────────────────────────────────────────────


class TestSandboxPolicy:
    def test_defaults(self):
        policy = SandboxPolicy()
        assert policy.backend == "auto"
        assert policy.timeout == 120
        assert policy.network.mode == "allow_all"

    def test_from_dict(self):
        data = {
            "backend": "seatbelt",
            "timeout": 60,
            "read_only_paths": ["/usr", "/lib"],
            "network": {"mode": "none"},
        }
        policy = SandboxPolicy.from_dict(data)
        assert policy.backend == "seatbelt"
        assert policy.timeout == 60
        assert policy.read_only_paths == ("/usr", "/lib")
        assert policy.network.mode == "none"

    def test_from_dict_empty(self):
        policy = SandboxPolicy.from_dict({})
        assert policy == SandboxPolicy()

    def test_from_dict_ignores_unknown_keys(self):
        data = {"backend": "docker", "unknown_key": "value"}
        policy = SandboxPolicy.from_dict(data)
        assert policy.backend == "docker"

    def test_immutable(self):
        policy = SandboxPolicy()
        with pytest.raises(AttributeError):
            policy.timeout = 999
