"""Tests for PluginManager lifecycle."""

from unittest.mock import MagicMock

import pytest
import yaml

from tank_backend.plugin.manager import (
    FEATURE_TYPE_MAP,
    ConfigError,
    ExtensionEntry,
    PluginEntry,
    PluginManager,
)
from tank_backend.plugin.manifest import ExtensionManifest, PluginManifest
from tank_backend.plugin.registry import ExtensionRegistry


def _tts_ext():
    return ExtensionManifest(
        name="tts", type="tts", factory="tts_edge:create_engine",
    )


def _asr_ext():
    return ExtensionManifest(
        name="asr", type="asr", factory="asr_sherpa:create_engine",
    )


def _tts_manifest():
    return PluginManifest(
        plugin_name="tts-edge",
        display_name="Edge TTS",
        description="test",
        extensions=[_tts_ext()],
    )


def _asr_manifest():
    return PluginManifest(
        plugin_name="asr-sherpa",
        display_name="Sherpa ASR",
        description="test",
        extensions=[_asr_ext()],
    )


def _make_plugin_dir(plugins_dir, name, manifest_data):
    """Create a plugin directory with plugin.yaml."""
    plugin_dir = plugins_dir / name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.yaml").write_text(
        yaml.safe_dump(manifest_data)
    )
    return plugin_dir


# ── Discovery tests ──────────────────────────────────────────────


class TestDiscoverPlugins:
    """Tests for filesystem-based plugin discovery."""

    def test_discovers_plugins_from_directory(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        _make_plugin_dir(plugins_dir, "tts-edge", {
            "name": "tts-edge",
            "display_name": "Edge TTS",
            "description": "test",
            "extensions": [
                {"name": "tts", "type": "tts", "factory": "tts_edge:create_engine"},
            ],
        })
        _make_plugin_dir(plugins_dir, "asr-sherpa", {
            "name": "asr-sherpa",
            "display_name": "Sherpa ASR",
            "description": "test",
            "extensions": [
                {"name": "asr", "type": "asr", "factory": "asr_sherpa:create_engine"},
            ],
        })

        pm = PluginManager(
            plugins_yaml_path=tmp_path / "plugins.yaml",
            plugins_dir=plugins_dir,
        )
        found = pm.discover_plugins()

        assert len(found) == 2
        assert "tts-edge" in found
        assert "asr-sherpa" in found
        assert found["tts-edge"].extensions[0].type == "tts"

    def test_skips_dirs_without_manifest(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        _make_plugin_dir(plugins_dir, "tts-edge", {
            "name": "tts-edge",
            "extensions": [],
        })
        # Directory without plugin.yaml
        (plugins_dir / "no-manifest").mkdir()

        pm = PluginManager(
            plugins_yaml_path=tmp_path / "plugins.yaml",
            plugins_dir=plugins_dir,
        )
        found = pm.discover_plugins()

        assert len(found) == 1
        assert "tts-edge" in found

    def test_skips_invalid_manifests(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        _make_plugin_dir(plugins_dir, "good-plugin", {
            "name": "good-plugin",
            "extensions": [],
        })
        # Invalid manifest (missing name)
        bad_dir = plugins_dir / "bad-plugin"
        bad_dir.mkdir(parents=True)
        (bad_dir / "plugin.yaml").write_text(
            yaml.safe_dump({"display_name": "No Name"})
        )

        pm = PluginManager(
            plugins_yaml_path=tmp_path / "plugins.yaml",
            plugins_dir=plugins_dir,
        )
        found = pm.discover_plugins()

        assert len(found) == 1
        assert "good-plugin" in found

    def test_empty_plugins_dir(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        pm = PluginManager(
            plugins_yaml_path=tmp_path / "plugins.yaml",
            plugins_dir=plugins_dir,
        )
        found = pm.discover_plugins()

        assert found == {}

    def test_missing_plugins_dir(self, tmp_path):
        pm = PluginManager(
            plugins_yaml_path=tmp_path / "plugins.yaml",
            plugins_dir=tmp_path / "nonexistent",
        )
        found = pm.discover_plugins()

        assert found == {}


# ── PluginManager tests ──────────────────────────────────────────────


class TestPluginManager:
    """Tests for PluginManager lifecycle."""

    def _make_pm_with_plugin(self, tmp_path, plugin_name, manifest_data):
        """Create a PluginManager with a plugin dir and plugins.yaml."""
        plugins_dir = tmp_path / "plugins"
        _make_plugin_dir(plugins_dir, plugin_name, manifest_data)
        return PluginManager(
            plugins_yaml_path=tmp_path / "plugins.yaml",
            plugins_dir=plugins_dir,
        )

    def test_load_all_generates_yaml_when_missing(self, tmp_path):
        """load_all auto-generates plugins.yaml if it doesn't exist."""
        plugins_yaml = tmp_path / "plugins.yaml"
        assert not plugins_yaml.exists()

        pm = self._make_pm_with_plugin(tmp_path, "tts-edge", {
            "name": "tts-edge",
            "display_name": "Edge TTS",
            "description": "test",
            "extensions": [
                {"name": "tts", "type": "tts", "factory": "tts_edge:create_engine"},
            ],
        })
        registry = pm.load_all()

        assert plugins_yaml.exists()
        assert registry.has("tts-edge:tts")

    def test_load_all_reads_existing_yaml(self, tmp_path):
        """load_all reads plugins.yaml and registers enabled extensions."""
        plugins_yaml = tmp_path / "plugins.yaml"
        plugins_yaml.write_text(yaml.safe_dump({
            "tts-edge": {
                "enabled": True,
                "extensions": {"tts": {"enabled": True}},
            },
        }))

        pm = self._make_pm_with_plugin(tmp_path, "tts-edge", {
            "name": "tts-edge",
            "display_name": "Edge TTS",
            "description": "test",
            "extensions": [
                {"name": "tts", "type": "tts", "factory": "tts_edge:create_engine"},
            ],
        })
        registry = pm.load_all()

        assert registry.has("tts-edge:tts")
        assert len(registry) == 1

    def test_disabled_plugin_not_registered(self, tmp_path):
        """Disabled plugins are skipped during load_all."""
        plugins_yaml = tmp_path / "plugins.yaml"
        plugins_yaml.write_text(yaml.safe_dump({
            "tts-edge": {
                "enabled": False,
                "extensions": {"tts": {"enabled": True}},
            },
        }))

        pm = PluginManager(
            plugins_yaml_path=plugins_yaml,
            plugins_dir=tmp_path / "plugins",
        )
        registry = pm.load_all()

        assert not registry.has("tts-edge:tts")
        assert len(registry) == 0

    def test_disabled_extension_not_registered(self, tmp_path):
        """Disabled extensions within an enabled plugin are skipped."""
        plugins_yaml = tmp_path / "plugins.yaml"
        plugins_yaml.write_text(yaml.safe_dump({
            "tts-edge": {
                "enabled": True,
                "extensions": {"tts": {"enabled": False}},
            },
        }))

        pm = self._make_pm_with_plugin(tmp_path, "tts-edge", {
            "name": "tts-edge",
            "display_name": "Edge TTS",
            "description": "test",
            "extensions": [
                {"name": "tts", "type": "tts", "factory": "tts_edge:create_engine"},
            ],
        })
        registry = pm.load_all()

        assert not registry.has("tts-edge:tts")

    def test_install_adds_to_yaml(self, tmp_path):
        """install() adds a plugin to plugins.yaml."""
        plugins_yaml = tmp_path / "plugins.yaml"
        plugins_yaml.write_text("{}")

        plugins_dir = tmp_path / "plugins"
        _make_plugin_dir(plugins_dir, "asr-sherpa", {
            "name": "asr-sherpa",
            "display_name": "Sherpa ASR",
            "description": "test",
            "extensions": [
                {"name": "asr", "type": "asr", "factory": "asr_sherpa:create_engine"},
            ],
        })

        pm = PluginManager(
            plugins_yaml_path=plugins_yaml,
            plugins_dir=plugins_dir,
        )
        pm.load_all()
        pm.install("asr-sherpa")

        assert pm.registry.has("asr-sherpa:asr")

        data = yaml.safe_load(plugins_yaml.read_text())
        assert "asr-sherpa" in data
        assert data["asr-sherpa"]["enabled"] is True

    def test_uninstall_removes_from_yaml(self, tmp_path):
        """uninstall() removes plugin from plugins.yaml and registry."""
        plugins_yaml = tmp_path / "plugins.yaml"
        plugins_yaml.write_text(yaml.safe_dump({
            "tts-edge": {
                "enabled": True,
                "extensions": {"tts": {"enabled": True}},
            },
        }))

        pm = self._make_pm_with_plugin(tmp_path, "tts-edge", {
            "name": "tts-edge",
            "display_name": "Edge TTS",
            "description": "test",
            "extensions": [
                {"name": "tts", "type": "tts", "factory": "tts_edge:create_engine"},
            ],
        })
        pm.load_all()

        assert pm.registry.has("tts-edge:tts")

        pm.uninstall("tts-edge")

        assert not pm.registry.has("tts-edge:tts")
        data = yaml.safe_load(plugins_yaml.read_text()) or {}
        assert "tts-edge" not in data

    def test_enable_disable_plugin(self, tmp_path):
        """enable/disable_plugin toggles registration."""
        plugins_yaml = tmp_path / "plugins.yaml"
        plugins_yaml.write_text(yaml.safe_dump({
            "tts-edge": {
                "enabled": True,
                "extensions": {"tts": {"enabled": True}},
            },
        }))

        pm = self._make_pm_with_plugin(tmp_path, "tts-edge", {
            "name": "tts-edge",
            "display_name": "Edge TTS",
            "description": "test",
            "extensions": [
                {"name": "tts", "type": "tts", "factory": "tts_edge:create_engine"},
            ],
        })
        pm.load_all()
        assert pm.registry.has("tts-edge:tts")

        pm.disable_plugin("tts-edge")
        assert not pm.registry.has("tts-edge:tts")

        pm.enable_plugin("tts-edge")
        assert pm.registry.has("tts-edge:tts")

    def test_enable_disable_extension(self, tmp_path):
        """enable/disable_extension toggles individual extension."""
        plugins_yaml = tmp_path / "plugins.yaml"
        plugins_yaml.write_text(yaml.safe_dump({
            "tts-edge": {
                "enabled": True,
                "extensions": {"tts": {"enabled": True}},
            },
        }))

        pm = self._make_pm_with_plugin(tmp_path, "tts-edge", {
            "name": "tts-edge",
            "display_name": "Edge TTS",
            "description": "test",
            "extensions": [
                {"name": "tts", "type": "tts", "factory": "tts_edge:create_engine"},
            ],
        })
        pm.load_all()
        assert pm.registry.has("tts-edge:tts")

        pm.disable_extension("tts-edge", "tts")
        assert not pm.registry.has("tts-edge:tts")

        pm.enable_extension("tts-edge", "tts")
        assert pm.registry.has("tts-edge:tts")

    def test_missing_plugin_not_found_logs_warning(self, tmp_path):
        """Plugin in yaml but not in plugins dir is skipped with warning."""
        plugins_yaml = tmp_path / "plugins.yaml"
        plugins_yaml.write_text(yaml.safe_dump({
            "nonexistent-plugin": {
                "enabled": True,
                "extensions": {"ext": {"enabled": True}},
            },
        }))

        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        pm = PluginManager(
            plugins_yaml_path=plugins_yaml,
            plugins_dir=plugins_dir,
        )
        registry = pm.load_all()

        assert len(registry) == 0


# ── Config validation tests ──────────────────────────────────────────


class TestConfigValidation:
    """Tests for PluginManager.validate_config()."""

    def _make_registry(self, extensions=None):
        reg = ExtensionRegistry()
        for plugin_name, manifest in (extensions or []):
            reg.register(plugin_name, manifest)
        return reg

    def _make_app_config(self, features):
        """Build a mock AppConfig with given feature configs."""
        mock = MagicMock()

        def get_feature_config(name):
            if name in features:
                return features[name]
            cfg = MagicMock()
            cfg.enabled = False
            cfg.extension = None
            return cfg

        mock.get_feature_config.side_effect = get_feature_config
        return mock

    def test_valid_refs_pass(self):
        reg = self._make_registry([
            ("asr-sherpa", _asr_ext()),
        ])
        cfg = MagicMock()
        cfg.enabled = True
        cfg.extension = "asr-sherpa:asr"
        app_config = self._make_app_config({"asr": cfg})

        pm = PluginManager()
        pm._registry = reg
        pm.validate_config(app_config)

    def test_missing_ref_raises(self):
        reg = self._make_registry()
        cfg = MagicMock()
        cfg.enabled = True
        cfg.extension = "asr-sherpa:asr"
        app_config = self._make_app_config({"asr": cfg})

        pm = PluginManager()
        pm._registry = reg
        with pytest.raises(ConfigError, match="not registered"):
            pm.validate_config(app_config)

    def test_type_mismatch_raises(self):
        reg = self._make_registry([
            ("wrong", ExtensionManifest(
                name="wrong", type="tts", factory="x:y",
            )),
        ])
        cfg = MagicMock()
        cfg.enabled = True
        cfg.extension = "wrong:wrong"
        app_config = self._make_app_config({"asr": cfg})

        pm = PluginManager()
        pm._registry = reg
        with pytest.raises(ConfigError, match="expected 'asr'"):
            pm.validate_config(app_config)

    def test_disabled_feature_skipped(self):
        reg = self._make_registry()
        cfg = MagicMock()
        cfg.enabled = False
        cfg.extension = "nonexistent:ext"
        app_config = self._make_app_config({"asr": cfg})

        pm = PluginManager()
        pm._registry = reg
        pm.validate_config(app_config)

    def test_no_extension_ref_skipped(self):
        reg = self._make_registry()
        cfg = MagicMock()
        cfg.enabled = True
        cfg.extension = None
        app_config = self._make_app_config({"asr": cfg})

        pm = PluginManager()
        pm._registry = reg
        pm.validate_config(app_config)


# ── Plugins YAML round-trip tests ────────────────────────────────────


class TestPluginsYaml:
    """Tests for plugins.yaml read/write."""

    def test_round_trip(self, tmp_path):
        """Write and read back plugins.yaml."""
        plugins_yaml = tmp_path / "plugins.yaml"

        pm = PluginManager(plugins_yaml_path=plugins_yaml)
        pm._entries = {
            "tts-edge": PluginEntry(
                name="tts-edge",
                enabled=True,
                extensions={
                    "tts": ExtensionEntry(name="tts", enabled=True),
                },
            ),
            "asr-sherpa": PluginEntry(
                name="asr-sherpa",
                enabled=False,
                extensions={
                    "asr": ExtensionEntry(name="asr", enabled=True),
                },
            ),
        }
        pm._write_plugins_yaml()

        entries = pm._read_plugins_yaml(plugins_yaml)
        assert "tts-edge" in entries
        assert entries["tts-edge"].enabled is True
        assert entries["tts-edge"].extensions["tts"].enabled is True
        assert "asr-sherpa" in entries
        assert entries["asr-sherpa"].enabled is False

    def test_auto_generation(self, tmp_path):
        """generate_plugins_yaml creates file from discovered plugins."""
        plugins_yaml = tmp_path / "plugins.yaml"
        plugins_dir = tmp_path / "plugins"
        _make_plugin_dir(plugins_dir, "tts-edge", {
            "name": "tts-edge",
            "display_name": "Edge TTS",
            "description": "test",
            "extensions": [
                {"name": "tts", "type": "tts", "factory": "tts_edge:create_engine"},
            ],
        })

        pm = PluginManager(
            plugins_yaml_path=plugins_yaml,
            plugins_dir=plugins_dir,
        )
        path = pm.generate_plugins_yaml()

        assert path.exists()
        data = yaml.safe_load(path.read_text())
        assert "tts-edge" in data
        assert data["tts-edge"]["enabled"] is True
        assert data["tts-edge"]["extensions"]["tts"]["enabled"] is True


# ── FEATURE_TYPE_MAP tests ────────────────────────────────────────────


class TestFeatureTypeMap:
    """Verify FEATURE_TYPE_MAP covers expected features."""

    def test_expected_features(self):
        assert FEATURE_TYPE_MAP["asr"] == "asr"
        assert FEATURE_TYPE_MAP["tts"] == "tts"
        assert FEATURE_TYPE_MAP["speaker"] == "speaker_id"
