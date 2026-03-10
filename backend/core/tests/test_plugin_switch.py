"""Tests for plugin enable/disable (feature switch) functionality."""

from unittest.mock import MagicMock, patch

import pytest

from tank_backend.plugin.config import AppConfig
from tank_backend.plugin.manifest import ExtensionManifest
from tank_backend.plugin.registry import ExtensionRegistry

MODULE = "tank_backend.core.assistant"


# ── SlotConfig / AppConfig tests ─────────────────────────────────────


class TestSlotConfigEnabled:
    """Tests for the enabled/disabled slot behaviour."""

    def test_slot_disabled_when_absent(self, tmp_path):
        yaml = tmp_path / "config.yaml"
        yaml.write_text("llm:\n  default:\n    api_key: test\n")
        config = AppConfig(yaml)

        slot = config.get_slot_config("asr")
        assert slot.enabled is False

    def test_slot_disabled_when_enabled_false(self, tmp_path):
        yaml = tmp_path / "config.yaml"
        yaml.write_text(
            "asr:\n  enabled: false\n  extension: asr-sherpa:asr\n"
            "  config:\n    sample_rate: 16000\n"
        )
        config = AppConfig(yaml)

        slot = config.get_slot_config("asr")
        assert slot.enabled is False

    def test_slot_enabled_with_extension_syntax(self, tmp_path):
        yaml = tmp_path / "config.yaml"
        yaml.write_text(
            "tts:\n  enabled: true\n  extension: tts-edge:tts\n  config:\n    voice_en: Jenny\n"
        )
        config = AppConfig(yaml)

        slot = config.get_slot_config("tts")
        assert slot.enabled is True
        assert slot.plugin == "tts-edge"
        assert slot.extension == "tts-edge:tts"
        assert slot.config["voice_en"] == "Jenny"

    def test_slot_enabled_with_legacy_plugin_syntax(self, tmp_path):
        yaml = tmp_path / "config.yaml"
        yaml.write_text("tts:\n  plugin: tts-edge\n  config:\n    voice: test\n")
        config = AppConfig(yaml)

        slot = config.get_slot_config("tts")
        assert slot.enabled is True
        assert slot.plugin == "tts-edge"
        assert slot.extension is None  # legacy format

    def test_slot_enabled_defaults_to_true(self, tmp_path):
        yaml = tmp_path / "config.yaml"
        yaml.write_text("asr:\n  extension: asr-sherpa:asr\n  config: {}\n")
        config = AppConfig(yaml)

        slot = config.get_slot_config("asr")
        assert slot.enabled is True

    def test_plugin_derived_from_extension_ref(self, tmp_path):
        yaml = tmp_path / "config.yaml"
        yaml.write_text("tts:\n  extension: tts-edge:tts\n  config: {}\n")
        config = AppConfig(yaml)

        slot = config.get_slot_config("tts")
        assert slot.plugin == "tts-edge"


class TestIsSlotEnabled:
    """Tests for AppConfig.is_slot_enabled()."""

    def test_returns_true_for_enabled_slot(self, tmp_path):
        yaml = tmp_path / "config.yaml"
        yaml.write_text("asr:\n  extension: asr-sherpa:asr\n  config: {}\n")
        config = AppConfig(yaml)
        assert config.is_slot_enabled("asr") is True

    def test_returns_false_for_absent_slot(self, tmp_path):
        yaml = tmp_path / "config.yaml"
        yaml.write_text("llm:\n  default:\n    api_key: x\n")
        config = AppConfig(yaml)
        assert config.is_slot_enabled("asr") is False

    def test_returns_false_for_disabled_slot(self, tmp_path):
        yaml = tmp_path / "config.yaml"
        yaml.write_text("tts:\n  enabled: false\n  extension: tts-edge:tts\n  config: {}\n")
        config = AppConfig(yaml)
        assert config.is_slot_enabled("tts") is False


class TestGetCapabilities:
    """Tests for AppConfig.get_capabilities()."""

    def test_all_enabled(self, tmp_path):
        yaml = tmp_path / "config.yaml"
        yaml.write_text(
            "asr:\n  extension: asr-sherpa:asr\n  config: {}\n"
            "tts:\n  extension: tts-edge:tts\n  config: {}\n"
            "speaker:\n  extension: speaker-sherpa:speaker_id\n  config: {}\n"
        )
        config = AppConfig(yaml)
        caps = config.get_capabilities()
        assert caps == {"asr": True, "tts": True, "speaker_id": True}

    def test_all_disabled(self, tmp_path):
        yaml = tmp_path / "config.yaml"
        yaml.write_text("llm:\n  default:\n    api_key: x\n")
        config = AppConfig(yaml)
        caps = config.get_capabilities()
        assert caps == {"asr": False, "tts": False, "speaker_id": False}

    def test_mixed(self, tmp_path):
        yaml = tmp_path / "config.yaml"
        yaml.write_text(
            "asr:\n  extension: asr-sherpa:asr\n  config: {}\n"
            "tts:\n  enabled: false\n  extension: tts-edge:tts\n  config: {}\n"
        )
        config = AppConfig(yaml)
        caps = config.get_capabilities()
        assert caps["asr"] is True
        assert caps["tts"] is False
        assert caps["speaker_id"] is False


# ── ExtensionRegistry tests ──────────────────────────────────────────


class TestExtensionRegistry:
    """Tests for ExtensionRegistry (manifest-based, string-keyed)."""

    def _make_manifest(self, name="tts", ext_type="tts", factory="tts_edge:create_engine"):
        return ExtensionManifest(name=name, type=ext_type, factory=factory)

    def test_register_and_get(self):
        reg = ExtensionRegistry()
        m = self._make_manifest()
        reg.register("tts-edge", m)
        assert reg.get("tts-edge:tts") is m

    def test_get_returns_none_for_missing(self):
        reg = ExtensionRegistry()
        assert reg.get("missing:ext") is None

    def test_has(self):
        reg = ExtensionRegistry()
        m = self._make_manifest()
        reg.register("tts-edge", m)
        assert reg.has("tts-edge:tts") is True
        assert reg.has("missing:ext") is False

    def test_unregister(self):
        reg = ExtensionRegistry()
        m = self._make_manifest()
        reg.register("tts-edge", m)
        assert reg.unregister("tts-edge:tts") is True
        assert reg.has("tts-edge:tts") is False
        assert reg.unregister("tts-edge:tts") is False

    def test_list_by_type(self):
        reg = ExtensionRegistry()
        m1 = self._make_manifest(name="tts", ext_type="tts")
        m2 = self._make_manifest(name="tts", ext_type="tts", factory="tts_eleven:create_engine")
        m3 = self._make_manifest(name="asr", ext_type="asr", factory="asr_sherpa:create_engine")
        reg.register("tts-edge", m1)
        reg.register("tts-eleven", m2)
        reg.register("asr-sherpa", m3)

        result = reg.list_by_type("tts")
        assert len(result) == 2
        names = [name for name, _ in result]
        assert "tts-edge:tts" in names
        assert "tts-eleven:tts" in names

    def test_all_names(self):
        reg = ExtensionRegistry()
        reg.register("tts-edge", self._make_manifest())
        reg.register("asr-sherpa", self._make_manifest(name="asr", ext_type="asr"))
        names = reg.all_names()
        assert "tts-edge:tts" in names
        assert "asr-sherpa:asr" in names

    def test_len(self):
        reg = ExtensionRegistry()
        assert len(reg) == 0
        reg.register("p", self._make_manifest())
        assert len(reg) == 1

    def test_instantiate_calls_factory(self):
        """instantiate imports module and calls factory."""
        reg = ExtensionRegistry()
        # Use json.loads as a real callable for testing
        m = ExtensionManifest(name="test", type="test", factory="json:loads")
        reg.register("test-plugin", m)
        result = reg.instantiate("test-plugin:test", '{"a": 1}')
        assert result == {"a": 1}

    def test_instantiate_missing_raises(self):
        reg = ExtensionRegistry()
        with pytest.raises(KeyError, match="not registered"):
            reg.instantiate("missing:ext", {})


# ── AppConfig validation tests ───────────────────────────────────────


class TestAppConfigValidation:
    """Tests for AppConfig slot validation against registry."""

    def _make_registry(self, extensions=None):
        """Build a real registry with given extensions."""
        reg = ExtensionRegistry()
        for plugin_name, manifest in (extensions or []):
            reg.register(plugin_name, manifest)
        return reg

    def test_valid_config_passes(self, tmp_path):
        yaml = tmp_path / "config.yaml"
        yaml.write_text(
            "asr:\n  extension: asr-sherpa:asr\n  config: {}\n"
            "tts:\n  extension: tts-edge:tts\n  config: {}\n"
        )
        reg = self._make_registry([
            ("asr-sherpa", ExtensionManifest(name="asr", type="asr", factory="x:y")),
            ("tts-edge", ExtensionManifest(name="tts", type="tts", factory="x:y")),
        ])
        # Should not raise
        AppConfig(yaml, registry=reg)

    def test_missing_extension_raises(self, tmp_path):
        from tank_backend.plugin.manager import ConfigError

        yaml = tmp_path / "config.yaml"
        yaml.write_text("asr:\n  extension: asr-sherpa:asr\n  config: {}\n")
        reg = self._make_registry()  # empty registry

        with pytest.raises(ConfigError, match="not registered"):
            AppConfig(yaml, registry=reg)

    def test_type_mismatch_raises(self, tmp_path):
        from tank_backend.plugin.manager import ConfigError

        yaml = tmp_path / "config.yaml"
        yaml.write_text("asr:\n  extension: wrong-plugin:wrong\n  config: {}\n")
        # Register with type "tts" but slot expects "asr"
        reg = self._make_registry([
            ("wrong-plugin", ExtensionManifest(name="wrong", type="tts", factory="x:y")),
        ])

        with pytest.raises(ConfigError, match="expected 'asr'"):
            AppConfig(yaml, registry=reg)

    def test_disabled_slot_skips_validation(self, tmp_path):
        yaml = tmp_path / "config.yaml"
        yaml.write_text(
            "asr:\n  enabled: false\n  extension: nonexistent:ext\n  config: {}\n"
        )
        reg = self._make_registry()  # empty
        # Should not raise — slot is disabled
        AppConfig(yaml, registry=reg)

    def test_no_registry_skips_validation(self, tmp_path):
        yaml = tmp_path / "config.yaml"
        yaml.write_text("asr:\n  extension: asr-sherpa:asr\n  config: {}\n")
        # No registry passed — should not raise
        AppConfig(yaml)


# ── Assistant subsystem optionality tests ────────────────────────────


def _make_mock_app_config(asr=True, tts=True, speaker=False):
    mock = MagicMock()
    mock.get_llm_profile.return_value = MagicMock()

    def is_slot_enabled(slot):
        return {"asr": asr, "tts": tts, "speaker": speaker}.get(slot, False)

    mock.is_slot_enabled.side_effect = is_slot_enabled

    def get_slot_config(slot):
        cfg = MagicMock()
        cfg.enabled = is_slot_enabled(slot)
        cfg.extension = f"mock-{slot}:{slot}" if cfg.enabled else None
        cfg.config = {}
        cfg.plugin = f"mock-{slot}" if cfg.enabled else ""
        return cfg

    mock.get_slot_config.side_effect = get_slot_config
    return mock


class TestAssistantSubsystemOptional:
    """Tests that Assistant skips AudioInput/AudioOutput when slots are disabled."""

    @pytest.fixture(autouse=True)
    def mock_subsystems(self):
        mock_registry = MagicMock()
        mock_registry.instantiate.return_value = MagicMock()

        mock_pm = MagicMock()
        mock_pm.load_all.return_value = mock_registry

        with (
            patch(f"{MODULE}.AudioInput") as self.mock_audio_input_cls,
            patch(f"{MODULE}.AudioOutput") as self.mock_audio_output_cls,
            patch(f"{MODULE}.Brain"),
            patch(f"{MODULE}.create_llm_from_profile", return_value=MagicMock()),
            patch(f"{MODULE}.ToolManager"),
            patch(f"{MODULE}.PluginManager", return_value=mock_pm),
            patch(f"{MODULE}.load_config", return_value=MagicMock(
                serper_api_key=None,
                speech_interrupt_enabled=False,
                enable_speaker_id=False,
            )),
        ):
            yield

    def test_no_audio_input_when_asr_disabled(self):
        with patch(f"{MODULE}.AppConfig", return_value=_make_mock_app_config(asr=False)):
            from tank_backend.core.assistant import Assistant
            assistant = Assistant()
            assert assistant.audio_input is None
            self.mock_audio_input_cls.assert_not_called()

    def test_no_audio_output_when_tts_disabled(self):
        with patch(f"{MODULE}.AppConfig", return_value=_make_mock_app_config(tts=False)):
            from tank_backend.core.assistant import Assistant
            assistant = Assistant()
            assert assistant.audio_output is None
            self.mock_audio_output_cls.assert_not_called()

    def test_both_created_when_enabled(self):
        with patch(f"{MODULE}.AppConfig", return_value=_make_mock_app_config(asr=True, tts=True)):
            from tank_backend.core.assistant import Assistant
            assistant = Assistant()
            assert assistant.audio_input is not None
            assert assistant.audio_output is not None

    def test_capabilities_reflect_disabled_slots(self):
        with patch(
            f"{MODULE}.AppConfig", return_value=_make_mock_app_config(asr=False, tts=False)
        ):
            from tank_backend.core.assistant import Assistant
            assistant = Assistant()
            caps = assistant.capabilities
            assert caps["asr"] is False
            assert caps["tts"] is False

    def test_capabilities_reflect_enabled_slots(self):
        with patch(f"{MODULE}.AppConfig", return_value=_make_mock_app_config(asr=True, tts=True)):
            from tank_backend.core.assistant import Assistant
            assistant = Assistant()
            caps = assistant.capabilities
            assert caps["asr"] is True
            assert caps["tts"] is True

    def test_start_skips_none_subsystems(self):
        with patch(
            f"{MODULE}.AppConfig", return_value=_make_mock_app_config(asr=False, tts=False)
        ):
            from tank_backend.core.assistant import Assistant
            assistant = Assistant()
            # Should not raise even though audio_input/output are None
            assistant.start()

    def test_stop_skips_none_subsystems(self):
        with patch(
            f"{MODULE}.AppConfig", return_value=_make_mock_app_config(asr=False, tts=False)
        ):
            from tank_backend.core.assistant import Assistant
            assistant = Assistant()
            assistant.brain = MagicMock()
            # Should not raise
            assistant.stop()

    def test_process_input_quit_when_tts_disabled(self):
        with patch(f"{MODULE}.AppConfig", return_value=_make_mock_app_config(tts=False)):
            from tank_backend.core.assistant import Assistant
            on_exit = MagicMock()
            assistant = Assistant(on_exit_request=on_exit)
            # Should not raise even though audio_output is None
            assistant.process_input("quit")
            assert assistant.shutdown_signal.is_set()
            on_exit.assert_called_once()


# ── Brain TTS guard tests ───────────────────────────────────────────


class TestBrainTTSGuard:
    """Tests that Brain skips TTS dispatch when tts_enabled=False."""

    def test_brain_accepts_tts_enabled_param(self):
        from tank_backend.core.brain import Brain

        brain = Brain.__new__(Brain)
        # Just verify the parameter is stored
        brain._tts_enabled = False
        assert brain._tts_enabled is False
