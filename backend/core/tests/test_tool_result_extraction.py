"""Tests for tool result extraction logic in llm.py."""

import json

import pytest

from tank_backend.core.content import ImageBlock, TextBlock
from tank_backend.llm.llm import (
    _TOOL_FOLLOW_UP_STUB,
    _blocks_to_openai_parts,
    _build_follow_up_user_message,
    _tool_result_to_llm,
)
from tank_backend.tools.base import ToolResult


class TestToolResultToLLM:
    """Test the _tool_result_to_llm() helper function."""

    def test_tool_result_with_display(self):
        """ToolResult with display returns (content, display, []) for text."""
        result = ToolResult(
            content='{"key": "value"}',
            display="Operation completed",
        )
        llm_content, ui_display, follow_up = _tool_result_to_llm(result)
        assert llm_content == '{"key": "value"}'
        assert ui_display == "Operation completed"
        assert follow_up == []

    def test_tool_result_without_display_short(self):
        """ToolResult without display returns (content, content, []) when short."""
        result = ToolResult(content="Short result")
        llm_content, ui_display, follow_up = _tool_result_to_llm(result)
        assert llm_content == "Short result"
        assert ui_display == "Short result"
        assert follow_up == []

    def test_tool_result_without_display_long(self):
        """ToolResult without display truncates content for UI when long."""
        long_content = "x" * 300
        result = ToolResult(content=long_content)
        llm_content, ui_display, follow_up = _tool_result_to_llm(result)
        assert llm_content == long_content
        assert ui_display == long_content[:200] + "..."
        assert len(ui_display) == 203
        assert follow_up == []

    def test_plain_string_short(self):
        """Plain string returns (str, str, []) when short."""
        llm_content, ui_display, follow_up = _tool_result_to_llm("Hello world")
        assert llm_content == "Hello world"
        assert ui_display == "Hello world"
        assert follow_up == []

    def test_plain_string_long(self):
        """Plain string truncates for UI when long."""
        long_str = "y" * 250
        llm_content, ui_display, follow_up = _tool_result_to_llm(long_str)
        assert llm_content == long_str
        assert ui_display == long_str[:200] + "..."
        assert follow_up == []

    def test_unexpected_type_logs_warning(self, caplog):
        """Unexpected type logs warning and converts to string."""
        llm_content, ui_display, follow_up = _tool_result_to_llm(42)
        assert llm_content == "42"
        assert ui_display == "42"
        assert follow_up == []
        assert "Tool returned unexpected type" in caplog.text

    def test_tool_result_error_flag(self):
        """ToolResult.error flag does not affect conversion shape."""
        result = ToolResult(
            content='{"error": "failed"}',
            display="Error occurred",
            error=True,
        )
        llm_content, ui_display, follow_up = _tool_result_to_llm(result)
        assert llm_content == '{"error": "failed"}'
        assert ui_display == "Error occurred"
        assert follow_up == []


class TestToolResultBlocks:
    """Test block-aware paths — tools returning ContentBlocks."""

    def test_text_blocks_flatten_to_string(self):
        """All-text blocks collapse to a concatenated string, no follow-up."""
        result = ToolResult(
            content=[TextBlock(text="line one"), TextBlock(text="line two")],
            display="two lines",
        )
        llm_content, ui_display, follow_up = _tool_result_to_llm(result)
        assert llm_content == "line one\nline two"
        assert ui_display == "two lines"
        assert follow_up == []

    def test_image_block_triggers_follow_up(self):
        """An ImageBlock returns a stub + follow-up blocks list."""
        img = ImageBlock(
            source="data:image/png;base64,iVBORw0KGgo=",
            mime_type="image/png",
        )
        result = ToolResult(
            content=[TextBlock(text="Here's the chart:"), img],
            display="rendered chart",
        )
        llm_content, ui_display, follow_up = _tool_result_to_llm(result)
        assert llm_content == _TOOL_FOLLOW_UP_STUB
        assert ui_display == "rendered chart"
        assert len(follow_up) == 2
        assert follow_up[0].type == "text"
        assert follow_up[1].type == "image"

    def test_image_only_uses_text_fallback_for_display(self):
        """No display + image-only content: display describes what came back."""
        img = ImageBlock(source="/tmp/x.png", mime_type="image/png")
        result = ToolResult(content=[img])
        _, ui_display, follow_up = _tool_result_to_llm(result)
        assert "[image:" in ui_display
        assert len(follow_up) == 1


class TestBlocksToOpenAIParts:
    """Test the block → OpenAI wire-format converter."""

    def test_text_blocks_merge(self):
        """Consecutive text blocks merge into one part."""
        parts = _blocks_to_openai_parts([
            TextBlock(text="first"),
            TextBlock(text="second"),
        ])
        assert parts == [{"type": "text", "text": "first\nsecond"}]

    def test_image_block_emits_image_url_part(self):
        """ImageBlock renders as {type: image_url, image_url: {url, detail}}."""
        parts = _blocks_to_openai_parts([
            ImageBlock(source="data:image/png;base64,xxx", mime_type="image/png"),
        ])
        assert parts == [{
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,xxx", "detail": "auto"},
        }]

    def test_interleaved_text_and_image(self):
        """Text-image-text produces three parts in order."""
        parts = _blocks_to_openai_parts([
            TextBlock(text="before"),
            ImageBlock(source="/x.jpg", mime_type="image/jpeg"),
            TextBlock(text="after"),
        ])
        assert len(parts) == 3
        assert parts[0]["type"] == "text"
        assert parts[1]["type"] == "image_url"
        assert parts[2]["type"] == "text"


class TestFollowUpMessage:
    """Test the follow-up user message builder."""

    def test_follow_up_has_metadata_for_grouping(self):
        """Follow-up message carries tool_call_id so UI can group."""
        img = ImageBlock(source="/x.png", mime_type="image/png")
        msg = _build_follow_up_user_message(
            tool_call_id="call_abc",
            tool_name="file_read",
            blocks=[img],
        )
        assert msg["role"] == "user"
        assert msg["metadata"]["tool_follow_up"] is True
        assert msg["metadata"]["tool_call_id"] == "call_abc"
        assert msg["metadata"]["tool_name"] == "file_read"
        assert len(msg["content"]) == 1


class TestToolResultIntegration:
    """Integration tests for tool result flow through LLM."""

    @pytest.mark.asyncio()
    async def test_file_read_llm_receives_full_content(self):
        """Verify LLM receives full file content, not just summary."""
        import os
        import tempfile

        from tank_backend.config.models import FileAccessConfig
        from tank_backend.policy.file_access import FileAccessPolicy
        from tank_backend.tools.file_read import FileReadTool

        policy = FileAccessPolicy(FileAccessConfig())
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

