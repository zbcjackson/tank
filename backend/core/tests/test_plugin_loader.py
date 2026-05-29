"""Test plugin configuration and registry."""

import pytest

from tank_backend.plugin import PluginConfig
from tank_backend.plugin.manifest import ExtensionManifest
from tank_backend.plugin.registry import ExtensionRegistry

# AppConfig.from_raw_dict requires a 'default' LLM profile, so every YAML
# fixture in this file includes one.
_DEFAULT_LLM = (
    "llm:\n"
    "  default:\n"
    "    api_key: k\n"
    "    model: m\n"
    "    base_url: u\n"
)


def test_plugin_config_loads_yaml(tmp_path):
    """Test PluginConfig loads YAML file."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(_DEFAULT_LLM + """
tts:
  plugin: tts-edge
  config:
    voice_en: en-US-JennyNeural
    voice_zh: zh-CN-XiaoxiaoNeural
""")

    config = PluginConfig.load(config_file)
    cfg = config.get_feature_config("tts")

    assert cfg.plugin == "tts-edge"
    assert cfg.config["voice_en"] == "en-US-JennyNeural"
    assert cfg.config["voice_zh"] == "zh-CN-XiaoxiaoNeural"


def test_plugin_config_missing_slot_returns_disabled(tmp_path):
    """Test PluginConfig returns disabled FeatureConfig for missing feature."""
    empty_yaml = tmp_path / "config.yaml"
    empty_yaml.write_text(_DEFAULT_LLM)
    config = PluginConfig.load(empty_yaml)

    cfg = config.get_feature_config("nonexistent")
    assert cfg.enabled is False


def test_plugin_config_missing_plugin_name_returns_disabled(tmp_path):
    """Test PluginConfig returns disabled FeatureConfig when plugin name not specified."""
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text(_DEFAULT_LLM + "tts:\n  config:\n    voice: test\n")
    config = PluginConfig.load(yaml_file)

    cfg = config.get_feature_config("tts")
    assert cfg.enabled is False


def test_registry_instantiate_missing_raises():
    """Test registry.instantiate raises KeyError for unregistered extension."""
    reg = ExtensionRegistry()
    with pytest.raises(KeyError, match="not registered"):
        reg.instantiate("nonexistent:ext", {})


def test_registry_instantiate_calls_factory():
    """Test registry.instantiate imports module and calls factory."""
    reg = ExtensionRegistry()
    manifest = ExtensionManifest(name="tts", type="tts", factory="json:loads")
    reg.register("test-plugin", manifest)

    # json.loads('{}') returns {}
    result = reg.instantiate("test-plugin:tts", '{}')
    assert result == {}
