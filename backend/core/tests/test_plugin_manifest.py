"""Tests for plugin manifest reading from plugin.yaml."""

import pytest
import yaml

from tank_backend.plugin.manifest import (
    ExtensionManifest,
    PluginManifest,
    read_manifest_from_yaml,
    read_plugin_manifest,
)


class TestReadManifestFromYaml:
    """Tests for read_manifest_from_yaml."""

    def test_parses_single_extension(self, tmp_path):
        manifest_path = tmp_path / "plugin.yaml"
        manifest_path.write_text(yaml.safe_dump({
            "name": "tts-edge",
            "display_name": "Edge TTS",
            "description": "Microsoft Edge TTS plugin",
            "extensions": [
                {"name": "tts", "type": "tts", "factory": "tts_edge:create_engine"},
            ],
        }))

        manifest = read_manifest_from_yaml(manifest_path)

        assert manifest.plugin_name == "tts-edge"
        assert manifest.display_name == "Edge TTS"
        assert manifest.description == "Microsoft Edge TTS plugin"
        assert len(manifest.extensions) == 1
        assert manifest.extensions[0].name == "tts"
        assert manifest.extensions[0].type == "tts"
        assert manifest.extensions[0].factory == "tts_edge:create_engine"

    def test_parses_multiple_extensions(self, tmp_path):
        manifest_path = tmp_path / "plugin.yaml"
        manifest_path.write_text(yaml.safe_dump({
            "name": "multi-plugin",
            "display_name": "Multi",
            "description": "Plugin with multiple extensions",
            "extensions": [
                {"name": "asr", "type": "asr", "factory": "multi:create_asr"},
                {"name": "tts", "type": "tts", "factory": "multi:create_tts"},
            ],
        }))

        manifest = read_manifest_from_yaml(manifest_path)
        assert len(manifest.extensions) == 2
        assert manifest.extensions[0].name == "asr"
        assert manifest.extensions[1].name == "tts"

    def test_defaults_for_missing_optional_fields(self, tmp_path):
        manifest_path = tmp_path / "plugin.yaml"
        manifest_path.write_text(yaml.safe_dump({"name": "my-plugin"}))

        manifest = read_manifest_from_yaml(manifest_path)
        assert manifest.plugin_name == "my-plugin"
        assert manifest.display_name == "my-plugin"
        assert manifest.description == ""
        assert manifest.extensions == []

    def test_raises_on_missing_name(self, tmp_path):
        manifest_path = tmp_path / "plugin.yaml"
        manifest_path.write_text(yaml.safe_dump({"display_name": "No Name"}))

        with pytest.raises(ValueError, match="missing 'name'"):
            read_manifest_from_yaml(manifest_path)

    def test_raises_on_invalid_yaml(self, tmp_path):
        manifest_path = tmp_path / "plugin.yaml"
        manifest_path.write_text("just a string")

        with pytest.raises(ValueError, match="missing 'name'"):
            read_manifest_from_yaml(manifest_path)

    def test_raises_on_missing_file(self, tmp_path):
        manifest_path = tmp_path / "nonexistent.yaml"

        with pytest.raises(FileNotFoundError):
            read_manifest_from_yaml(manifest_path)


class TestReadPluginManifest:
    """Tests for read_plugin_manifest with plugins_dir."""

    def test_reads_from_plugins_dir(self, tmp_path):
        plugin_dir = tmp_path / "tts-edge"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.yaml").write_text(yaml.safe_dump({
            "name": "tts-edge",
            "display_name": "Edge TTS",
            "description": "test",
            "extensions": [
                {"name": "tts", "type": "tts", "factory": "tts_edge:create_engine"},
            ],
        }))

        manifest = read_plugin_manifest("tts-edge", plugins_dir=tmp_path)
        assert manifest.plugin_name == "tts-edge"
        assert len(manifest.extensions) == 1

    def test_raises_when_plugin_not_found(self, tmp_path):
        with pytest.raises(ImportError, match="not found"):
            read_plugin_manifest("nonexistent", plugins_dir=tmp_path)


class TestExtensionManifest:
    """Tests for ExtensionManifest dataclass."""

    def test_frozen(self):
        ext = ExtensionManifest(name="tts", type="tts", factory="tts_edge:create_engine")
        assert ext.name == "tts"
        assert ext.type == "tts"
        assert ext.factory == "tts_edge:create_engine"


class TestPluginManifest:
    """Tests for PluginManifest dataclass."""

    def test_frozen_with_defaults(self):
        manifest = PluginManifest(
            plugin_name="test", display_name="Test", description="desc"
        )
        assert manifest.extensions == []
