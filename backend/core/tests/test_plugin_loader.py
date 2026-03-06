"""Test plugin loading."""

import pytest

from tank_backend.plugin import PluginConfig, load_plugin


def test_plugin_config_loads_yaml(tmp_path):
    """Test PluginConfig loads YAML file."""
    config_file = tmp_path / "plugins.yaml"
    config_file.write_text("""
tts:
  plugin: tts-edge
  config:
    voice_en: en-US-JennyNeural
    voice_zh: zh-CN-XiaoxiaoNeural
""")

    config = PluginConfig(config_file)
    slot_config = config.get_slot_config("tts")

    assert slot_config["plugin"] == "tts-edge"
    assert slot_config["config"]["voice_en"] == "en-US-JennyNeural"
    assert slot_config["config"]["voice_zh"] == "zh-CN-XiaoxiaoNeural"


def test_plugin_config_missing_slot():
    """Test PluginConfig raises error for missing slot."""
    config = PluginConfig()
    config._config = {}

    with pytest.raises(ValueError, match="No configuration found for slot"):
        config.get_slot_config("nonexistent")


def test_plugin_config_missing_plugin_name():
    """Test PluginConfig raises error when plugin name not specified."""
    config = PluginConfig()
    config._config = {"tts": {"config": {"voice": "test"}}}  # Has config but no plugin name

    with pytest.raises(ValueError, match="No plugin specified for slot"):
        config.get_slot_config("tts")


def test_load_plugin_missing_module():
    """Test load_plugin raises ImportError for missing plugin."""
    with pytest.raises(ImportError, match="Plugin 'nonexistent-plugin' not found"):
        load_plugin(
            slot="tts",
            plugin_name="nonexistent-plugin",
            config={},
        )
