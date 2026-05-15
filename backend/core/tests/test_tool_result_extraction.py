"""Tests for tool result extraction logic in llm.py."""

import json
from unittest.mock import AsyncMock, MagicMock

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

    def test_document_native_emits_file_part(self):
        """DocumentBlock(send_native=True) emits OpenAI file wire form."""
        from tank_backend.core.content import DocumentBlock, blocks_to_openai_parts

        blocks = [
            TextBlock(text="Summarise this:"),
            DocumentBlock(
                source="data:application/pdf;base64,JVBERi0xLjQ=",
                mime_type="application/pdf",
                send_native=True,
            ),
        ]
        parts = blocks_to_openai_parts(blocks)
        assert len(parts) == 2
        assert parts[0] == {"type": "text", "text": "Summarise this:"}
        assert parts[1]["type"] == "file"
        assert parts[1]["file"]["file_data"] == (
            "data:application/pdf;base64,JVBERi0xLjQ="
        )
        # Filename is derived best-effort; for a data URL we fall back
        # to a MIME-extension default.
        assert parts[1]["file"]["filename"].endswith(".pdf")

    def test_document_native_filename_from_media_uri(self):
        """media:// URIs contribute the filename to the file part."""
        from tank_backend.core.content import DocumentBlock, blocks_to_openai_parts

        parts = blocks_to_openai_parts([
            DocumentBlock(
                source="media://sess/abc123.pdf",
                mime_type="application/pdf",
                send_native=True,
            ),
        ])
        # Note: in real use, MediaStore.materialize_for_llm replaces
        # the media:// URI with a data URL before wire rendering. This
        # test exercises the filename derivation on the pre-materialized
        # shape because the filename field is the wire requirement.
        assert parts[0]["file"]["filename"] == "abc123.pdf"

    def test_document_with_extracted_text_and_pages(self):
        """Non-native doc: text prefix + one image_url part per page."""
        from tank_backend.core.content import DocumentBlock, blocks_to_openai_parts

        parts = blocks_to_openai_parts([
            DocumentBlock(
                source="media://sess/x.pdf",
                mime_type="application/pdf",
                extracted_text="Page 1 text\nPage 2 text",
                page_images=(
                    ImageBlock(
                        source="data:image/png;base64,AAA",
                        mime_type="image/png",
                    ),
                    ImageBlock(
                        source="data:image/png;base64,BBB",
                        mime_type="image/png",
                    ),
                ),
            ),
        ])
        # Expect: text part, image part, image part
        assert len(parts) == 3
        assert parts[0]["type"] == "text"
        assert "Page 1 text" in parts[0]["text"]
        assert parts[1]["type"] == "image_url"
        assert parts[2]["type"] == "image_url"


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



# ---------------------------------------------------------------------------
# Phase 18 follow-up: _materialize_blocks_for_llm
# ---------------------------------------------------------------------------


class TestMaterializeBlocksForLLM:
    """Regression for the post-Phase-18 ``image_url`` rejection bug.

    After ``render_chart`` returns a ToolResult containing
    ``ImageBlock(source="media://session/hash.png")``, the LLM loop's
    follow-up user-role message hands ``block.source`` straight to the
    OpenAI provider. Azure rejects it with

        Invalid 'input[N].content[M].image_url'. Expected a valid URL,
        but got a value with an invalid format.

    The fix routes blocks through ``MediaStore.materialize_for_llm``
    before they reach ``_blocks_to_openai_parts``. ``media://`` URIs
    become data URLs / pre-signed http URLs the LLM accepts. Other
    block sources (http(s)://, data:, plain text) pass through.
    """

    @pytest.mark.asyncio
    async def test_no_media_store_passes_blocks_through(self):
        """Without ``media_store`` the helper is a no-op — keeps the
        text-only path (no MediaStore configured) working unchanged."""
        from tank_backend.core.content import ImageBlock, TextBlock
        from tank_backend.llm.llm import _materialize_blocks_for_llm

        blocks = [
            TextBlock(text="hi"),
            ImageBlock(source="media://s1/x.png", mime_type="image/png"),
        ]
        out = await _materialize_blocks_for_llm(
            blocks, media_store=None, session_id="s1",
        )
        assert out == blocks

    @pytest.mark.asyncio
    async def test_no_session_id_passes_blocks_through(self):
        """Without a session_id we can't address the MediaStore
        folder; pass the original blocks through and let the LLM
        provider's validator decide."""
        from tank_backend.core.content import ImageBlock
        from tank_backend.llm.llm import _materialize_blocks_for_llm

        store = MagicMock()
        blocks = [ImageBlock(source="media://s1/x.png", mime_type="image/png")]
        out = await _materialize_blocks_for_llm(
            blocks, media_store=store, session_id=None,
        )
        assert out == blocks
        store.materialize_for_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_media_uri_routed_through_materialize(self):
        """Happy path: each block is handed to
        ``materialize_for_llm`` which returns a wire-ready substitute.
        The helper is shape-preserving — output list has the same
        length and order as input."""
        from tank_backend.core.content import ImageBlock
        from tank_backend.llm.llm import _materialize_blocks_for_llm

        materialized = ImageBlock(
            source="data:image/png;base64,XYZ", mime_type="image/png",
        )
        store = MagicMock()
        store.materialize_for_llm = AsyncMock(return_value=materialized)

        blocks = [ImageBlock(source="media://s1/x.png", mime_type="image/png")]
        out = await _materialize_blocks_for_llm(
            blocks, media_store=store, session_id="s1",
        )

        assert len(out) == 1
        assert out[0] is materialized
        store.materialize_for_llm.assert_awaited_once()
        # session_id must thread through; MediaStore.get raises
        # CrossSessionAccessError otherwise.
        kwargs = store.materialize_for_llm.call_args.kwargs
        assert kwargs["session_id"] == "s1"

    @pytest.mark.asyncio
    async def test_materialize_failure_falls_back_to_original(self):
        """When ``materialize_for_llm`` raises, the helper logs and
        substitutes the original block. The LLM call may still 400 on
        that turn but the user already saw the chart on their
        connector — better partial degradation than dropping the
        whole turn."""
        from tank_backend.core.content import ImageBlock
        from tank_backend.llm.llm import _materialize_blocks_for_llm

        store = MagicMock()
        store.materialize_for_llm = AsyncMock(
            side_effect=RuntimeError("storage offline"),
        )

        original = ImageBlock(source="media://s1/x.png", mime_type="image/png")
        out = await _materialize_blocks_for_llm(
            [original], media_store=store, session_id="s1",
        )

        assert out == [original]

    @pytest.mark.asyncio
    async def test_mixed_blocks_each_routed_independently(self):
        """A typical follow-up has a TextBlock + ImageBlock. Both
        flow through ``materialize_for_llm`` (the MediaStore method
        decides per-block whether work is needed); each result lands
        in the same position."""
        from tank_backend.core.content import ImageBlock, TextBlock
        from tank_backend.llm.llm import _materialize_blocks_for_llm

        text_block = TextBlock(text="Here:")
        materialized_image = ImageBlock(
            source="data:image/png;base64,XYZ", mime_type="image/png",
        )
        store = MagicMock()
        # Real MediaStore returns the input unchanged for non-media://;
        # mimic that here by checking source.
        async def _stub(block, *, session_id):
            if isinstance(block, ImageBlock) and block.source.startswith("media://"):
                return materialized_image
            return block
        store.materialize_for_llm = _stub

        blocks = [
            text_block,
            ImageBlock(source="media://s1/x.png", mime_type="image/png"),
        ]
        out = await _materialize_blocks_for_llm(
            blocks, media_store=store, session_id="s1",
        )
        assert out[0] is text_block
        assert out[1] is materialized_image


# ---------------------------------------------------------------------------
# Phase 18 follow-up: _materialize_messages_for_llm
# ---------------------------------------------------------------------------


class TestMaterializeMessagesForLLM:
    """Regression for the persisted-history image_url rejection bug.

    After the chart-tool turn, the conversation history contains a
    user-role message with ``content`` like::

        [{"type": "image_url", "image_url": {"url": "media://s1/x.png"}}]

    Replaying that on the *next* turn handed the raw ``media://`` URI
    to the LLM provider, which rejected it. ``_materialize_blocks_for_llm``
    only covers blocks coming OUT of a tool; this helper covers the
    INBOUND messages list before the LLM call.
    """

    @pytest.mark.asyncio
    async def test_text_only_messages_pass_through(self):
        from tank_backend.llm.llm import _materialize_messages_for_llm

        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        store = MagicMock()
        out = await _materialize_messages_for_llm(
            messages, media_store=store, session_id="s1",
        )
        assert out == messages
        store.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_message_with_http_image_unchanged(self):
        """``image_url.url`` that's already an http(s) URL passes
        through untouched. Only ``media://`` triggers materialization."""
        from tank_backend.llm.llm import _materialize_messages_for_llm

        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "look:"},
                {"type": "image_url", "image_url": {"url": "https://x/y.png"}},
            ],
        }]
        store = MagicMock()
        out = await _materialize_messages_for_llm(
            messages, media_store=store, session_id="s1",
        )
        assert out[0] is messages[0]
        store.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_media_uri_rewritten_to_data_url(self):
        """The headline regression: a persisted message with a
        ``media://`` ``image_url.url`` gets rewritten to a data URL the
        LLM provider accepts. ``detail`` field is preserved on the
        rewrite — some images explicitly request high-detail processing."""
        from tank_backend.llm.llm import _materialize_messages_for_llm

        store = MagicMock()
        store.get = AsyncMock(return_value=(b"\x89PNG_fake_bytes", "image/png"))

        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "Here's the chart:"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "media://s1/abc.png",
                        "detail": "high",
                    },
                },
            ],
        }]
        out = await _materialize_messages_for_llm(
            messages, media_store=store, session_id="s1",
        )

        # Original messages list is not mutated; new shape returned.
        assert messages[0]["content"][1]["image_url"]["url"] == "media://s1/abc.png"

        # New message has the resolved data URL.
        new_part = out[0]["content"][1]
        assert new_part["type"] == "image_url"
        assert new_part["image_url"]["url"].startswith("data:image/png;base64,")
        # ``detail`` survives the rewrite.
        assert new_part["image_url"]["detail"] == "high"
        # Text part unaffected.
        assert out[0]["content"][0] == {"type": "text", "text": "Here's the chart:"}
        # session_id was forwarded so cross-session reads are blocked
        # by MediaStore.
        store.get.assert_awaited_once_with("media://s1/abc.png", session_id="s1")

    @pytest.mark.asyncio
    async def test_repeated_uri_cached_within_one_call(self):
        """A single message containing the same ``media://`` URI twice
        (rare but possible) reads from MediaStore once. The cache
        scopes to one ``_materialize_messages_for_llm`` call so it
        doesn't grow without bound across turns."""
        from tank_backend.llm.llm import _materialize_messages_for_llm

        store = MagicMock()
        store.get = AsyncMock(return_value=(b"X", "image/png"))

        messages = [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "media://s/x.png"}},
                {"type": "image_url", "image_url": {"url": "media://s/x.png"}},
            ],
        }]
        await _materialize_messages_for_llm(
            messages, media_store=store, session_id="s",
        )
        store.get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_failure_falls_back_to_original_url(self):
        """When ``MediaStore.get`` raises, leave the URL alone. The
        LLM call may 400 on that turn but the user already saw the
        chart on their connector. Better than dropping the whole turn
        on a transient storage failure."""
        from tank_backend.llm.llm import _materialize_messages_for_llm

        store = MagicMock()
        store.get = AsyncMock(side_effect=RuntimeError("storage offline"))

        messages = [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "media://s/x.png"}},
            ],
        }]
        out = await _materialize_messages_for_llm(
            messages, media_store=store, session_id="s",
        )
        # Original URI preserved (degraded but doesn't break tests
        # downstream).
        assert out[0]["content"][0]["image_url"]["url"] == "media://s/x.png"


# ---------------------------------------------------------------------------
# Phase 19 follow-up: per-iteration materialization
# ---------------------------------------------------------------------------


class TestPerIterationMaterialization:
    """Phase 19 dropped outbound block materialization so persisted
    history keeps ``media://`` URIs. The inbound ``_materialize_messages_for_llm``
    walker is now the only seam where rewrite happens. It MUST run on
    every chat-loop iteration, not just at entry — the Phase 19
    refactor created mid-loop ``tool_follow_up`` appends with raw
    URIs that the *next* iteration would otherwise hand to the LLM
    provider as ``media://...``, which Azure rejects.

    These tests pin the contract: walker is idempotent on
    already-rewritten URLs (so re-walking is cheap) and rewrites any
    URLs that newly appeared since the last walk.
    """

    @pytest.mark.asyncio
    async def test_walker_is_idempotent_on_already_rewritten(self):
        """A walker that ran once and rewrote ``media://x`` to a data
        URL must not double-rewrite if invoked again. The check that
        gates rewriting on ``url.startswith('media://')`` makes this
        natural — but pin it so a future refactor doesn't regress."""
        from tank_backend.llm.llm import _materialize_messages_for_llm

        store = MagicMock()
        store.get = AsyncMock(return_value=(b"\x89PNG_fake", "image/png"))

        messages = [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "media://s/x.png"}},
            ],
        }]
        first = await _materialize_messages_for_llm(
            messages, media_store=store, session_id="s",
        )
        # First walk rewrites; second walk leaves the data URL alone.
        second = await _materialize_messages_for_llm(
            first, media_store=store, session_id="s",
        )

        # Walker called MediaStore.get exactly once across both runs:
        # the second walk had no media:// to resolve.
        assert store.get.await_count == 1
        # Output unchanged on the second pass.
        assert second[0]["content"][0]["image_url"]["url"] == \
            first[0]["content"][0]["image_url"]["url"]

    @pytest.mark.asyncio
    async def test_walker_rewrites_newly_appended_message(self):
        """The mid-loop scenario: walker ran once on the inbound list;
        a tool_follow_up gets appended after a tool ran; walker runs
        again on the next iteration and rewrites the new entry. Pinned
        because losing this guarantee was the Phase 19 follow-up bug
        (chart turns 400'd on the next iteration with raw media://).
        """
        from tank_backend.llm.llm import _materialize_messages_for_llm

        store = MagicMock()
        store.get = AsyncMock(return_value=(b"\x89PNG_fake", "image/png"))

        # Iteration 1: clean inbound, no images.
        messages = [
            {"role": "user", "content": "plot Q1-Q4"},
        ]
        walked = await _materialize_messages_for_llm(
            messages, media_store=store, session_id="s",
        )
        assert store.get.await_count == 0  # no images yet

        # Mid-loop: tool runs, follow-up appended with raw media://.
        walked.append({
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "media://s/c.png"}},
            ],
            "metadata": {"tool_follow_up": True, "tool_call_id": "tc_1"},
        })

        # Iteration 2: walker re-runs, rewrites the new entry.
        walked2 = await _materialize_messages_for_llm(
            walked, media_store=store, session_id="s",
        )
        assert store.get.await_count == 1
        assert walked2[1]["content"][0]["image_url"]["url"].startswith(
            "data:image/png;base64,",
        )
