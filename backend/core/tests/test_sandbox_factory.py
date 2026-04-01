"""Tests for SandboxFactory — backend detection and construction."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tank_backend.sandbox.factory import SandboxBackendUnavailable, SandboxFactory
from tank_backend.sandbox.policy import (
    DENIED_MOUNTS_HARDCODED,
    MountSpec,
    NetworkPolicy,
    SandboxPolicy,
)
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


# ── Docker same-path mounts ──────────────────────────────────────


class TestDockerSamePathMounts:
    def _make_docker_sandbox(self, policy: SandboxPolicy):
        mock_docker = MagicMock()
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_client.ping.return_value = True

        with patch.dict("sys.modules", {"docker": mock_docker}):
            return SandboxFactory.create(policy)

    def test_mounts_produce_same_path_volumes(self):
        home = str(Path.home())
        policy = SandboxPolicy(
            backend="docker",
            mounts=(MountSpec(host="~", mode="ro"),),
        )
        sandbox = self._make_docker_sandbox(policy)
        volumes = sandbox._volumes
        assert volumes is not None
        # Home dir should be mounted at the same path
        assert home in volumes
        assert volumes[home]["bind"] == home
        assert volumes[home]["mode"] == "ro"

    def test_denied_paths_excluded_from_mounts(self):
        home = str(Path.home())
        ssh_path = os.path.join(home, ".ssh")
        policy = SandboxPolicy(
            backend="docker",
            mounts=(MountSpec(host="~/.ssh", mode="ro"),),
            denied_paths=(ssh_path,),
        )
        sandbox = self._make_docker_sandbox(policy)
        volumes = sandbox._volumes
        # .ssh should NOT be in volumes because it's denied
        assert ssh_path not in volumes

    def test_workspace_fallback_included(self):
        policy = SandboxPolicy(backend="docker")
        sandbox = self._make_docker_sandbox(policy)
        volumes = sandbox._volumes
        # Should have at least the workspace mount
        workspace = str(Path("./workspace").resolve())
        assert workspace in volumes
        assert volumes[workspace]["bind"] == "/workspace"
        assert volumes[workspace]["mode"] == "rw"

    def test_rw_mount_mode_propagated(self):
        policy = SandboxPolicy(
            backend="docker",
            mounts=(MountSpec(host="/tmp", mode="rw"),),
        )
        sandbox = self._make_docker_sandbox(policy)
        volumes = sandbox._volumes
        # /tmp resolves to /private/tmp on macOS
        tmp_resolved = str(Path("/tmp").resolve())
        assert tmp_resolved in volumes
        assert volumes[tmp_resolved]["mode"] == "rw"


# ── SandboxPolicy ─────────────────────────────────────────────────


class TestSandboxPolicy:
    def test_defaults(self):
        policy = SandboxPolicy()
        assert policy.backend == "auto"
        assert policy.timeout == 120
        assert policy.network.mode == "allow_all"
        assert policy.enabled is True

    def test_from_dict_empty_returns_disabled(self):
        policy = SandboxPolicy.from_dict({})
        assert policy.enabled is False

    def test_immutable(self):
        policy = SandboxPolicy()
        with pytest.raises(AttributeError):
            policy.timeout = 999


class TestSandboxPolicyNewFormat:
    """Tests for the new config format with mounts and denied_mounts."""

    def test_mounts_parsed(self):
        data = {
            "backend": "auto",
            "mounts": [
                {"host": "~", "mode": "ro"},
                {"host": "/tmp", "mode": "rw"},
            ],
        }
        policy = SandboxPolicy.from_dict(data)
        assert len(policy.mounts) == 2
        assert policy.mounts[0].host == "~"
        assert policy.mounts[0].mode == "ro"
        assert policy.mounts[1].host == "/tmp"
        assert policy.mounts[1].mode == "rw"

    def test_mounts_expand_to_read_only_paths(self):
        home = str(Path.home())
        data = {
            "mounts": [{"host": "~", "mode": "ro"}],
        }
        policy = SandboxPolicy.from_dict(data)
        assert home in policy.read_only_paths

    def test_mounts_expand_to_writable_paths(self):
        data = {
            "mounts": [{"host": "/tmp", "mode": "rw"}],
        }
        policy = SandboxPolicy.from_dict(data)
        tmp_expanded = os.path.expanduser("/tmp")
        assert tmp_expanded in policy.writable_paths

    def test_denied_mounts_merged_with_hardcoded(self):
        data = {
            "denied_mounts": ["~/.aws", "~/.azure"],
        }
        policy = SandboxPolicy.from_dict(data)
        # Should contain both hardcoded and user-specified
        home = str(Path.home())
        assert os.path.join(home, ".ssh") in policy.denied_paths
        assert os.path.join(home, ".gnupg") in policy.denied_paths
        assert os.path.join(home, ".aws") in policy.denied_paths
        assert os.path.join(home, ".azure") in policy.denied_paths

    def test_hardcoded_denied_always_present(self):
        """denied_mounts_hardcoded cannot be removed by user config."""
        data = {"denied_mounts": []}
        policy = SandboxPolicy.from_dict(data)
        home = str(Path.home())
        assert os.path.join(home, ".ssh") in policy.denied_paths
        assert os.path.join(home, ".gnupg") in policy.denied_paths

    def test_network_from_dict(self):
        data = {
            "network": {"mode": "restricted", "allowed_hosts": ["api.example.com"]},
        }
        policy = SandboxPolicy.from_dict(data)
        assert policy.network.mode == "restricted"
        assert "api.example.com" in policy.network.allowed_hosts

    def test_docker_settings_parsed(self):
        data = {
            "docker": {
                "image": "my-sandbox:v2",
                "workspace_host_path": "/data/workspace",
            },
        }
        policy = SandboxPolicy.from_dict(data)
        assert policy.docker_image == "my-sandbox:v2"
        assert policy.docker_workspace == "/data/workspace"

    def test_resource_limits(self):
        data = {
            "memory_limit": "4g",
            "cpu_count": 8,
            "timeout": 30,
            "max_timeout": 120,
        }
        policy = SandboxPolicy.from_dict(data)
        assert policy.memory_limit == "4g"
        assert policy.cpu_count == 8
        assert policy.timeout == 30
        assert policy.max_timeout == 120

    def test_enabled_defaults_true(self):
        data = {"backend": "auto"}
        policy = SandboxPolicy.from_dict(data)
        assert policy.enabled is True

    def test_enabled_false(self):
        data = {"enabled": False}
        policy = SandboxPolicy.from_dict(data)
        assert policy.enabled is False


class TestSandboxPolicyLegacyFormat:
    """Tests for backward compatibility with the old Docker-specific format."""

    def test_legacy_format_detected(self):
        data = {
            "enabled": True,
            "image": "tank-sandbox:latest",
            "workspace_host_path": "./workspace",
            "memory_limit": "1g",
            "cpu_count": 2,
            "default_timeout": 120,
            "max_timeout": 600,
            "network_enabled": True,
        }
        policy = SandboxPolicy.from_dict(data)
        assert policy.enabled is True
        assert policy.backend == "docker"
        assert policy.docker_image == "tank-sandbox:latest"
        assert policy.docker_workspace == "./workspace"
        assert policy.memory_limit == "1g"
        assert policy.cpu_count == 2
        assert policy.timeout == 120
        assert policy.max_timeout == 600
        assert policy.network.mode == "allow_all"

    def test_legacy_network_disabled(self):
        data = {
            "image": "tank-sandbox:latest",
            "network_enabled": False,
        }
        policy = SandboxPolicy.from_dict(data)
        assert policy.network.mode == "none"

    def test_legacy_disabled(self):
        data = {
            "enabled": False,
            "image": "tank-sandbox:latest",
        }
        policy = SandboxPolicy.from_dict(data)
        assert policy.enabled is False


# ── Backend policy translation ───────────────────────────────────


class TestBackendPolicyTranslation:
    def test_seatbelt_receives_denied_paths(self):
        home = str(Path.home())
        policy = SandboxPolicy(
            read_only_paths=(home,),
            denied_paths=(
                os.path.join(home, ".ssh"),
                os.path.join(home, ".gnupg"),
            ),
        )
        backend_policy = SandboxFactory._to_backend_policy(policy, "seatbelt")
        assert os.path.join(home, ".ssh") in backend_policy.denied_paths
        assert os.path.join(home, ".gnupg") in backend_policy.denied_paths
        assert home in backend_policy.read_only_paths

    def test_bubblewrap_receives_denied_paths(self):
        home = str(Path.home())
        policy = SandboxPolicy(
            read_only_paths=(home,),
            denied_paths=(
                os.path.join(home, ".ssh"),
                os.path.join(home, ".gnupg"),
            ),
        )
        backend_policy = SandboxFactory._to_backend_policy(policy, "bubblewrap")
        assert os.path.join(home, ".ssh") in backend_policy.denied_paths
        assert os.path.join(home, ".gnupg") in backend_policy.denied_paths
        assert home in backend_policy.read_only_paths

    def test_seatbelt_network_mode_translated(self):
        policy = SandboxPolicy(network=NetworkPolicy(mode="none"))
        backend_policy = SandboxFactory._to_backend_policy(policy, "seatbelt")
        assert backend_policy.network.value == "none"

    def test_bubblewrap_network_mode_translated(self):
        policy = SandboxPolicy(
            network=NetworkPolicy(
                mode="restricted", allowed_hosts=("api.example.com",)
            ),
        )
        backend_policy = SandboxFactory._to_backend_policy(policy, "bubblewrap")
        assert backend_policy.network.value == "restricted"
        assert "api.example.com" in backend_policy.allowed_hosts


# ── DENIED_MOUNTS_HARDCODED ─────────────────────────────────────


class TestDeniedMountsHardcoded:
    def test_contains_ssh(self):
        assert "~/.ssh" in DENIED_MOUNTS_HARDCODED

    def test_contains_gnupg(self):
        assert "~/.gnupg" in DENIED_MOUNTS_HARDCODED

    def test_contains_keychains(self):
        assert "~/Library/Keychains" in DENIED_MOUNTS_HARDCODED

    def test_contains_docker_socket(self):
        assert "/var/run/docker.sock" in DENIED_MOUNTS_HARDCODED


# ── _is_denied helper ────────────────────────────────────────────


class TestIsDenied:
    def test_exact_match(self):
        assert SandboxFactory._is_denied("/home/user/.ssh", {"/home/user/.ssh"})

    def test_subpath_match(self):
        assert SandboxFactory._is_denied(
            "/home/user/.ssh/id_rsa", {"/home/user/.ssh"}
        )

    def test_no_match(self):
        assert not SandboxFactory._is_denied(
            "/home/user/projects", {"/home/user/.ssh"}
        )

    def test_partial_name_no_match(self):
        """'/home/user/.ssh2' should NOT match denied '/home/user/.ssh'."""
        assert not SandboxFactory._is_denied(
            "/home/user/.ssh2", {"/home/user/.ssh"}
        )
