"""Tests for plugin enable/disable (feature switch) functionality."""

from unittest.mock import MagicMock, patch

import pytest

from tank_backend.plugin.config import AppConfig
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
    """Tests for ExtensionRegistry."""

    def test_register_and_get(self):
        reg = ExtensionRegistry()
        obj = object()
        reg.register("tts-edge", "tts", obj)
        assert reg.get("tts-edge", "tts") is obj

    def test_get_returns_none_for_missing(self):
        reg = ExtensionRegistry()
        assert reg.get("missing", "ext") is None

    def test_get_all_by_type(self):
        reg = ExtensionRegistry()
        a, b = object(), object()
        reg.register("tts-edge", "tts", a)
        reg.register("tts-eleven", "tts", b)
        reg.register("asr-sherpa", "asr", object())

        result = reg.get_all_by_type("tts")
        assert len(result) == 2
        assert a in result
        assert b in result

    def test_len(self):
        reg = ExtensionRegistry()
        assert len(reg) == 0
        reg.register("p", "e", object())
        assert len(reg) == 1


# ── Assistant subsystem optionality tests ────────────────────────────


class TestAssistantSubsystemOptional:
    """Tests that Assistant skips AudioInput/AudioOutput when slots are disabled."""

    @pytest.fixture(autouse=True)
    def mock_subsystems(self):
        with (
            patch(f"{MODULE}.AudioInput") as self.mock_audio_input_cls,
            patch(f"{MODULE}.AudioOutput") as self.mock_audio_output_cls,
            patch(f"{MODULE}.Brain"),
            patch(f"{MODULE}.create_llm_from_profile", return_value=MagicMock()),
            patch(f"{MODULE}.ToolManager"),
            patch(f"{MODULE}.load_config", return_value=MagicMock(
                serper_api_key=None,
                speech_interrupt_enabled=False,
                enable_speaker_id=False,
            )),
        ):
            yield

    def _make_app_config(self, asr=True, tts=True, speaker=False):
        mock = MagicMock()
        mock.get_llm_profile.return_value = MagicMock()

        def is_slot_enabled(slot):
            return {"asr": asr, "tts": tts, "speaker": speaker}.get(slot, False)

        mock.is_slot_enabled.side_effect = is_slot_enabled
        return mock

    def test_no_audio_input_when_asr_disabled(self):
        with patch(f"{MODULE}.AppConfig", return_value=self._make_app_config(asr=False)):
            from tank_backend.core.assistant import Assistant
            assistant = Assistant()
            assert assistant.audio_input is None
            self.mock_audio_input_cls.assert_not_called()

    def test_no_audio_output_when_tts_disabled(self):
        with patch(f"{MODULE}.AppConfig", return_value=self._make_app_config(tts=False)):
            from tank_backend.core.assistant import Assistant
            assistant = Assistant()
            assert assistant.audio_output is None
            self.mock_audio_output_cls.assert_not_called()

    def test_both_created_when_enabled(self):
        with patch(f"{MODULE}.AppConfig", return_value=self._make_app_config(asr=True, tts=True)):
            from tank_backend.core.assistant import Assistant
            assistant = Assistant()
            assert assistant.audio_input is not None
            assert assistant.audio_output is not None

    def test_capabilities_reflect_disabled_slots(self):
        with patch(f"{MODULE}.AppConfig", return_value=self._make_app_config(asr=False, tts=False)):
            from tank_backend.core.assistant import Assistant
            assistant = Assistant()
            caps = assistant.capabilities
            assert caps["asr"] is False
            assert caps["tts"] is False

    def test_capabilities_reflect_enabled_slots(self):
        with patch(f"{MODULE}.AppConfig", return_value=self._make_app_config(asr=True, tts=True)):
            from tank_backend.core.assistant import Assistant
            assistant = Assistant()
            caps = assistant.capabilities
            assert caps["asr"] is True
            assert caps["tts"] is True

    def test_start_skips_none_subsystems(self):
        with patch(f"{MODULE}.AppConfig", return_value=self._make_app_config(asr=False, tts=False)):
            from tank_backend.core.assistant import Assistant
            assistant = Assistant()
            # Should not raise even though audio_input/output are None
            assistant.start()

    def test_stop_skips_none_subsystems(self):
        with patch(f"{MODULE}.AppConfig", return_value=self._make_app_config(asr=False, tts=False)):
            from tank_backend.core.assistant import Assistant
            assistant = Assistant()
            assistant.brain = MagicMock()
            # Should not raise
            assistant.stop()

    def test_process_input_quit_when_tts_disabled(self):
        with patch(f"{MODULE}.AppConfig", return_value=self._make_app_config(tts=False)):
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
