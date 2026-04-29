"""Integration test: Brain._build_agent_graph with real typed AppConfig.

This test exists because the migration from dict-based config to typed
dataclasses introduced a bug where ``agents_cfg.get("system_prompt")``
was called on an ``AgentsConfig`` dataclass (which has no ``.get()``).
Unit tests missed it because they always inject a pre-built AgentGraph,
bypassing ``_build_agent_graph`` entirely.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

from tank_backend.config.models import BrainConfig
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processors.brain import Brain
from tank_backend.plugin.config import AppConfig


def _make_real_app_config(tmp_path) -> AppConfig:
    """Create a real AppConfig from a minimal YAML file."""
    yaml = tmp_path / "config.yaml"
    yaml.write_text(
        "llm:\n"
        "  default:\n"
        "    api_key: test-key\n"
        "    model: gpt-4\n"
        "    base_url: https://api.example.com/v1\n"
        "agents:\n"
        "  dirs: []\n"  # no agent dirs — avoids filesystem scanning
    )
    return AppConfig(yaml)


class TestBrainBuildAgentGraph:
    """Brain._build_agent_graph must work with real typed AppConfig."""

    def test_build_agent_graph_with_typed_config(self, tmp_path):
        """_build_agent_graph should not crash with typed AgentsConfig.

        This is the exact scenario that caused the runtime error:
        ``agents_cfg.get("system_prompt")`` on a frozen dataclass.
        """
        app_config = _make_real_app_config(tmp_path)

        llm = MagicMock()
        llm.model = "gpt-4"
        tool_manager = MagicMock()
        tool_manager.get_openai_tools.return_value = []
        tool_manager.approval_policy = MagicMock()
        bus = Bus()
        config = BrainConfig(max_history_tokens=8000)

        mock_context = MagicMock()
        mock_context.session_id = "test"
        mock_context.messages = [{"role": "system", "content": "test"}]
        mock_context.resume_or_new.return_value = "test"
        mock_context.prepare_turn.return_value = [{"role": "system", "content": "test"}]
        mock_context.count_tokens.return_value = 0

        mock_cm_class = MagicMock(return_value=mock_context)
        with patch.dict(
            "tank_backend.context.__dict__",
            {"ContextManager": mock_cm_class},
        ):
            brain = Brain(
                llm=llm,
                tool_manager=tool_manager,
                config=config,
                bus=bus,
                interrupt_event=threading.Event(),
                app_config=app_config,
                tts_enabled=False,
            )

        # Verify the agent graph was built (not injected)
        assert brain._agent_graph is not None
