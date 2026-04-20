"""Tests for tool result extraction logic in llm.py."""

import json

import pytest

from tank_backend.llm.llm import _tool_result_to_str
from tank_backend.tools.base import ToolResult


class TestToolResultToStr:
    """Test the _tool_result_to_str() helper function."""

    def test_tool_result_with_display(self):
        """ToolResult with display returns (content, display)."""
        result = ToolResult(
            content='{"key": "value"}',
            display="Operation completed",
        )
        llm_content, ui_display = _tool_result_to_str(result)
        assert llm_content == '{"key": "value"}'
        assert ui_display == "Operation completed"

    def test_tool_result_without_display_short(self):
        """ToolResult without display returns (content, content) when short."""
        result = ToolResult(content="Short result")
        llm_content, ui_display = _tool_result_to_str(result)
        assert llm_content == "Short result"
        assert ui_display == "Short result"

    def test_tool_result_without_display_long(self):
        """ToolResult without display truncates content for UI when long."""
        long_content = "x" * 300
        result = ToolResult(content=long_content)
        llm_content, ui_display = _tool_result_to_str(result)
        assert llm_content == long_content
        assert ui_display == long_content[:200] + "..."
        assert len(ui_display) == 203

    def test_plain_string_short(self):
        """Plain string returns (str, str) when short."""
        llm_content, ui_display = _tool_result_to_str("Hello world")
        assert llm_content == "Hello world"
        assert ui_display == "Hello world"

    def test_plain_string_long(self):
        """Plain string truncates for UI when long."""
        long_str = "y" * 250
        llm_content, ui_display = _tool_result_to_str(long_str)
        assert llm_content == long_str
        assert ui_display == long_str[:200] + "..."

    def test_unexpected_type_logs_warning(self, caplog):
        """Unexpected type logs warning and converts to string."""
        llm_content, ui_display = _tool_result_to_str(42)
        assert llm_content == "42"
        assert ui_display == "42"
        assert "Tool returned unexpected type" in caplog.text

    def test_tool_result_error_flag(self):
        """ToolResult.error flag is preserved (not used by _tool_result_to_str)."""
        result = ToolResult(
            content='{"error": "failed"}',
            display="Error occurred",
            error=True,
        )
        llm_content, ui_display = _tool_result_to_str(result)
        assert llm_content == '{"error": "failed"}'
        assert ui_display == "Error occurred"


class TestToolResultIntegration:
    """Integration tests for tool result flow through LLM."""

    @pytest.mark.asyncio()
    async def test_file_read_llm_receives_full_content(self):
        """Verify LLM receives full file content, not just summary."""
        import os
        import tempfile

        from tank_backend.policy.file_access import FileAccessPolicy
        from tank_backend.tools.file_read import FileReadTool

        policy = FileAccessPolicy()
        tool = FileReadTool(policy)

        # Create a temp file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("This is the full file content that the LLM must see.")
            temp_path = f.name

        try:
            result = await tool.execute(path=temp_path)

            # Verify result structure
            assert isinstance(result, ToolResult)
            assert not result.error

            # Verify LLM content is complete
            content_data = json.loads(result.content)
            assert "content" in content_data
            assert content_data["content"] == (
                "This is the full file content that the LLM must see."
            )

            # Verify UI display is concise
            assert "Read" in result.display
            assert "chars" in result.display
            assert len(result.display) < 300
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio()
    async def test_calculator_llm_receives_result(self):
        """Verify calculator result reaches LLM."""
        from tank_backend.tools.calculator import CalculatorTool

        tool = CalculatorTool()
        result = await tool.execute(expression="2 + 2")

        assert isinstance(result, ToolResult)
        assert not result.error

        content_data = json.loads(result.content)
        assert content_data["expression"] == "2 + 2"
        assert content_data["result"] == 4

        assert result.display == "2 + 2 = 4"

    @pytest.mark.asyncio()
    async def test_skill_inline_returns_string(self):
        """Verify skill inline mode returns plain string for LLM."""
        import tempfile
        from pathlib import Path

        from tank_backend.skills.manager import SkillManager
        from tank_backend.skills.registry import SkillRegistry
        from tank_backend.skills.reviewer import SecurityReviewer
        from tank_backend.tools.skill_tools import UseSkillTool
        with tempfile.TemporaryDirectory() as tmpdir:
            from pathlib import Path
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "---\nname: test-skill\ndescription: Test\n---\nInstructions here"
            )

            registry = SkillRegistry([Path(tmpdir)])
            registry.scan()
            mgr = SkillManager(registry, SecurityReviewer())
            mgr.startup()

            tool = UseSkillTool(mgr)
            result = await tool.execute(skill="test-skill")

            # Inline mode returns plain string
            assert isinstance(result, str)
            assert "SKILL ACTIVATED" in result
            assert "Instructions here" in result

    @pytest.mark.asyncio()
    async def test_error_result_has_error_flag(self):
        """Verify error results have error=True."""
        from tank_backend.tools.calculator import CalculatorTool

        tool = CalculatorTool()
        result = await tool.execute(expression="invalid syntax!")

        assert isinstance(result, ToolResult)
        assert result.error is True

        content_data = json.loads(result.content)
        assert "error" in content_data
        assert "Error calculating" in result.display
