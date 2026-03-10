"""Tests for plugin manifest reading."""

from tank_backend.plugin.manifest import (
    ExtensionManifest,
    PluginManifest,
    _infer_type_from_name,
    _legacy_manifest,
    _parse_manifest,
)


class TestParseManifest:
    """Tests for _parse_manifest helper."""

    def test_parses_single_extension(self):
        tank_meta = {
            "plugin_name": "tts-edge",
            "display_name": "Edge TTS",
            "description": "Microsoft Edge TTS plugin",
            "extensions": [
                {"name": "tts", "type": "tts", "factory": "tts_edge:create_engine"}
            ],
        }
        manifest = _parse_manifest("tts-edge", tank_meta)

        assert manifest.plugin_name == "tts-edge"
        assert manifest.display_name == "Edge TTS"
        assert manifest.description == "Microsoft Edge TTS plugin"
        assert len(manifest.extensions) == 1
        assert manifest.extensions[0].name == "tts"
        assert manifest.extensions[0].type == "tts"
        assert manifest.extensions[0].factory == "tts_edge:create_engine"

    def test_parses_multiple_extensions(self):
        tank_meta = {
            "plugin_name": "multi-plugin",
            "display_name": "Multi",
            "description": "Plugin with multiple extensions",
            "extensions": [
                {"name": "asr", "type": "asr", "factory": "multi:create_asr"},
                {"name": "tts", "type": "tts", "factory": "multi:create_tts"},
            ],
        }
        manifest = _parse_manifest("multi-plugin", tank_meta)
        assert len(manifest.extensions) == 2
        assert manifest.extensions[0].name == "asr"
        assert manifest.extensions[1].name == "tts"

    def test_defaults_for_missing_fields(self):
        tank_meta = {}
        manifest = _parse_manifest("my-plugin", tank_meta)
        assert manifest.plugin_name == "my-plugin"
        assert manifest.display_name == "my-plugin"
        assert manifest.description == ""
        assert manifest.extensions == []


class TestLegacyManifest:
    """Tests for _legacy_manifest fallback."""

    def test_creates_single_extension_from_plugin_name(self):
        manifest = _legacy_manifest("tts-edge", slot_type="tts")
        assert manifest.plugin_name == "tts-edge"
        assert len(manifest.extensions) == 1
        ext = manifest.extensions[0]
        assert ext.name == "tts"
        assert ext.type == "tts"
        assert ext.factory == "tts_edge:create_engine"

    def test_infers_type_when_slot_type_not_given(self):
        manifest = _legacy_manifest("asr-sherpa")
        ext = manifest.extensions[0]
        assert ext.type == "asr"
        assert ext.name == "asr"

    def test_infers_speaker_type(self):
        manifest = _legacy_manifest("speaker-sherpa")
        assert manifest.extensions[0].type == "speaker_id"

    def test_unknown_type_for_unrecognized_prefix(self):
        manifest = _legacy_manifest("custom-plugin")
        assert manifest.extensions[0].type == "unknown"


class TestInferTypeFromName:
    """Tests for _infer_type_from_name."""

    def test_tts_prefix(self):
        assert _infer_type_from_name("tts-edge") == "tts"

    def test_asr_prefix(self):
        assert _infer_type_from_name("asr-sherpa") == "asr"

    def test_speaker_prefix(self):
        assert _infer_type_from_name("speaker-sherpa") == "speaker_id"

    def test_unknown_prefix(self):
        assert _infer_type_from_name("llm-openai") == "unknown"


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
