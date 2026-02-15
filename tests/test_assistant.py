"""Tests for Assistant orchestrator."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.voice_assistant.core.assistant import Assistant
from src.voice_assistant.config.settings import VoiceAssistantConfig, load_config


class TestAssistant:
    """Unit tests for Assistant."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config."""
        return VoiceAssistantConfig(
            llm_api_key="test_key",
            llm_model="test_model",
            llm_base_url="https://test.com/v1",
            serper_api_key="test_serper_key",
        )

    @patch('src.voice_assistant.core.assistant.load_config')
    @patch('src.voice_assistant.core.assistant.LLM')
    @patch('src.voice_assistant.core.assistant.ToolManager')
    def test_assistant_loads_config(
        self, mock_tool_manager, mock_llm_class, mock_load_config, mock_config
    ):
        """Assistant should load config on initialization."""
        mock_load_config.return_value = mock_config
        mock_llm_instance = MagicMock()
        mock_llm_class.return_value = mock_llm_instance
        mock_tool_manager_instance = MagicMock()
        mock_tool_manager.return_value = mock_tool_manager_instance

        assistant = Assistant(config_path=Path(".env"))

        mock_load_config.assert_called_once_with(Path(".env"))
        assert assistant._config == mock_config

    @patch('src.voice_assistant.core.assistant.load_config')
    @patch('src.voice_assistant.core.assistant.LLM')
    @patch('src.voice_assistant.core.assistant.ToolManager')
    def test_assistant_creates_llm(
        self, mock_tool_manager, mock_llm_class, mock_load_config, mock_config
    ):
        """Assistant should create LLM instance."""
        mock_load_config.return_value = mock_config
        mock_llm_instance = MagicMock()
        mock_llm_class.return_value = mock_llm_instance
        mock_tool_manager_instance = MagicMock()
        mock_tool_manager.return_value = mock_tool_manager_instance

        assistant = Assistant()

        mock_llm_class.assert_called_once_with(
            api_key=mock_config.llm_api_key,
            model=mock_config.llm_model,
            base_url=mock_config.llm_base_url,
        )
        assert assistant._llm == mock_llm_instance

    @patch('src.voice_assistant.core.assistant.load_config')
    @patch('src.voice_assistant.core.assistant.LLM')
    @patch('src.voice_assistant.core.assistant.ToolManager')
    def test_assistant_creates_tool_manager(
        self, mock_tool_manager, mock_llm_class, mock_load_config, mock_config
    ):
        """Assistant should create ToolManager instance."""
        mock_load_config.return_value = mock_config
        mock_llm_instance = MagicMock()
        mock_llm_class.return_value = mock_llm_instance
        mock_tool_manager_instance = MagicMock()
        mock_tool_manager.return_value = mock_tool_manager_instance

        assistant = Assistant()

        mock_tool_manager.assert_called_once_with(
            serper_api_key=mock_config.serper_api_key,
        )
        assert assistant._tool_manager == mock_tool_manager_instance

    @patch('src.voice_assistant.core.assistant.load_config')
    @patch('src.voice_assistant.core.assistant.LLM')
    @patch('src.voice_assistant.core.assistant.ToolManager')
    @patch('src.voice_assistant.core.assistant.Brain')
    @patch('src.voice_assistant.core.assistant.AudioOutput')
    @patch('src.voice_assistant.core.assistant.AudioInput')
    @pytest.mark.parametrize("text", ["quit", "exit"])
    def test_process_input_quit_or_exit_interrupts_speaker_and_stops(
        self,
        mock_audio_input_cls,
        mock_audio_output_cls,
        mock_brain_cls,
        mock_tool_manager,
        mock_llm_class,
        mock_load_config,
        mock_config,
        text,
    ):
        """process_input('quit' or 'exit') interrupts speaker, sets shutdown, and calls on_exit_request."""
        mock_load_config.return_value = mock_config
        mock_llm_class.return_value = MagicMock()
        mock_tool_manager.return_value = MagicMock()
        mock_audio_input_cls.return_value = MagicMock()
        mock_speaker = MagicMock()
        mock_audio_output_cls.return_value = MagicMock(speaker=mock_speaker)
        mock_brain_cls.return_value = MagicMock()

        on_exit_request = MagicMock()
        assistant = Assistant(on_exit_request=on_exit_request)

        assistant.process_input(text)

        mock_speaker.interrupt.assert_called_once()
        assert assistant.shutdown_signal.is_set()
        on_exit_request.assert_called_once()

    @patch('src.voice_assistant.core.assistant.load_config')
    @patch('src.voice_assistant.core.assistant.LLM')
    @patch('src.voice_assistant.core.assistant.ToolManager')
    def test_process_input_puts_display_message(
        self, mock_tool_manager, mock_llm_class, mock_load_config, mock_config
    ):
        """process_input should put a DisplayMessage into the display_queue."""
        mock_load_config.return_value = mock_config
        mock_llm_class.return_value = MagicMock()
        mock_tool_manager.return_value = MagicMock()

        assistant = Assistant()
        assistant.process_input("hello")

        assert not assistant.runtime.display_queue.empty()
        msg = assistant.runtime.display_queue.get_nowait()
        assert msg.speaker == "Keyboard"
        assert msg.text == "hello"
        assert msg.is_user is True
        assert msg.msg_id is not None
        assert msg.msg_id.startswith("kbd_")
