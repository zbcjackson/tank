"""Tests for session reset (wake word conversation lifecycle)."""

from unittest.mock import MagicMock

import pytest

from tank_backend.audio.output import AudioOutput
from tank_backend.config.settings import VoiceAssistantConfig
from tank_backend.core.brain import Brain
from tank_backend.core.events import BrainInputEvent, InputType
from tank_backend.core.runtime import RuntimeContext
from tank_backend.core.shutdown import GracefulShutdown


class TestBrainSessionReset:
    """Tests for Brain.reset_conversation() and system reset event handling."""

    @pytest.fixture
    def runtime(self):
        return RuntimeContext.create()

    @pytest.fixture
    def shutdown_signal(self):
        return GracefulShutdown()

    @pytest.fixture
    def mock_llm(self):
        return MagicMock()

    @pytest.fixture
    def mock_config(self):
        return VoiceAssistantConfig(max_conversation_history=10)

    @pytest.fixture
    def brain(self, shutdown_signal, runtime, mock_llm, mock_config):
        return Brain(
            shutdown_signal=shutdown_signal,
            runtime=runtime,
            speaker_ref=MagicMock(spec=AudioOutput),
            llm=mock_llm,
            tool_manager=MagicMock(),
            config=mock_config,
        )

    def test_reset_conversation_clears_history(self, brain):
        """reset_conversation() should keep only the system prompt."""
        # Add some messages to history
        brain._conversation_history.append({"role": "user", "content": "hello"})
        brain._conversation_history.append({"role": "assistant", "content": "hi there"})
        brain._conversation_history.append({"role": "user", "content": "how are you?"})
        assert len(brain._conversation_history) == 4  # system + 3

        brain.reset_conversation()

        assert len(brain._conversation_history) == 1
        assert brain._conversation_history[0]["role"] == "system"
        assert brain._conversation_history[0]["content"] == brain._system_prompt

    def test_handle_system_reset_event(self, brain, mock_llm):
        """handle() with SYSTEM/__reset__ should reset history and not call LLM."""
        # Add messages first
        brain._conversation_history.append({"role": "user", "content": "hello"})
        brain._conversation_history.append({"role": "assistant", "content": "hi"})

        event = BrainInputEvent(
            type=InputType.SYSTEM,
            text="__reset__",
            user="system",
            language=None,
            confidence=None,
        )
        brain.handle(event)

        # History should be reset
        assert len(brain._conversation_history) == 1
        assert brain._conversation_history[0]["role"] == "system"

        # LLM should NOT have been called
        mock_llm.chat_stream.assert_not_called()

    def test_handle_system_reset_does_not_emit_signals(self, brain, runtime):
        """System reset should not put any messages on the UI queue."""
        event = BrainInputEvent(
            type=InputType.SYSTEM,
            text="__reset__",
            user="system",
            language=None,
            confidence=None,
        )
        brain.handle(event)

        assert runtime.ui_queue.empty()

    def test_handle_ignores_non_reset_system_events(self, brain, mock_llm):
        """System events with text other than __reset__ should be skipped (blank check)."""
        brain._conversation_history.append({"role": "user", "content": "hello"})

        event = BrainInputEvent(
            type=InputType.SYSTEM,
            text="",
            user="system",
            language=None,
            confidence=None,
        )
        brain.handle(event)

        # History should NOT be reset (still has the extra message)
        assert len(brain._conversation_history) == 2
        # LLM should NOT have been called
        mock_llm.chat_stream.assert_not_called()


class TestAssistantResetSession:
    """Tests for Assistant.reset_session() thread-safe queue dispatch."""

    def test_reset_session_enqueues_system_event(self):
        """reset_session() should put a SYSTEM/__reset__ event on brain_input_queue."""
        from unittest.mock import patch

        with patch("tank_backend.core.assistant.load_config") as mock_load, \
             patch("tank_backend.core.assistant.PluginManager"), \
             patch("tank_backend.core.assistant.AppConfig") as mock_app_config, \
             patch("tank_backend.core.assistant.create_llm_from_profile"), \
             patch("tank_backend.core.assistant.ToolManager"), \
             patch("tank_backend.core.assistant.Brain"):

            mock_load.return_value = VoiceAssistantConfig()
            mock_app_cfg = MagicMock()
            mock_app_cfg.get_feature_config.return_value = MagicMock(enabled=False)
            mock_app_cfg.is_feature_enabled.return_value = False
            mock_app_cfg._config = {}
            mock_app_config.return_value = mock_app_cfg

            from tank_backend.core.assistant import Assistant

            assistant = Assistant()

            assistant.reset_session()

            event = assistant.runtime.brain_input_queue.get_nowait()
            assert event.type == InputType.SYSTEM
            assert event.text == "__reset__"
            assert event.user == "system"
