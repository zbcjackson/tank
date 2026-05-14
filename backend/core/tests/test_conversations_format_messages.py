"""Regression for the conversation-resume crash on image follow-up
messages.

The Phase 18 follow-up bug: when a chart had been rendered earlier
in a conversation, the LLM loop persisted the follow-up user-role
message that carries the ImageBlock back to the next turn (see
``llm._build_follow_up_user_message``). That message has
``content`` shaped as a *list of OpenAI parts*, not a string. On
resume, ``GET /api/conversations/{id}/messages`` returned the array
straight through. The frontend's react-markdown renderer crashed on
``[object Object]`` content with::

    Uncaught Assertion: Unexpected value `[object Object],[object
    Object]` for `children` prop, expected `string`.

The fix lives in :func:`_format_messages`: skip ``tool_follow_up``
entries (LLM-loop scaffolding the user already saw via the tool
card) and defensively coerce any other non-string ``content`` to
``""`` so a future code path can't reintroduce the same shape.

Tests here pin both fixes so the bug can't recur.
"""

from __future__ import annotations

from tank_backend.api.conversations import _format_messages


class TestFormatMessages:
    def test_skips_system_messages(self) -> None:
        out = _format_messages([
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "hi"},
        ])
        assert len(out) == 1
        assert out[0]["role"] == "user"

    def test_preserves_text_user_and_assistant_messages(self) -> None:
        out = _format_messages([
            {"role": "user", "content": "what's 2+2?"},
            {"role": "assistant", "content": "4"},
        ])
        assert [m["role"] for m in out] == ["user", "assistant"]
        assert out[0]["content"] == "what's 2+2?"
        assert out[1]["content"] == "4"
        # msg_id is synthesised per-message — index-based scheme
        # keeps history positions stable.
        assert out[0]["msg_id"] == "history_0"
        assert out[1]["msg_id"] == "history_1"

    def test_preserves_tool_calls_on_assistant(self) -> None:
        """The frontend rebuilds tool cards from these on resume."""
        tool_calls = [
            {
                "id": "tc_1",
                "type": "function",
                "function": {"name": "render_chart", "arguments": "{}"},
            },
        ]
        out = _format_messages([
            {
                "role": "assistant",
                "content": "",
                "tool_calls": tool_calls,
            },
        ])
        assert out[0]["tool_calls"] == tool_calls

    def test_preserves_tool_call_id_on_tool_result(self) -> None:
        out = _format_messages([
            {
                "role": "tool",
                "content": "<image content sent>",
                "tool_call_id": "tc_1",
                "name": "render_chart",
            },
        ])
        assert out[0]["tool_call_id"] == "tc_1"
        assert out[0]["name"] == "render_chart"

    def test_skips_tool_follow_up_messages(self) -> None:
        """The headline regression. After Phase 18 ``ChartTool`` ran,
        the LLM loop persisted a user-role message like::

            {
              "role": "user",
              "content": [
                  {"type": "text", "text": "[image attached]"},
                  {"type": "image_url", "image_url": {"url": "media://..."}},
              ],
              "metadata": {"tool_follow_up": True, "tool_call_id": "tc_1"},
            }

        Returning that array unchanged broke the frontend's Markdown
        renderer. Drop these on the way out — the user-visible image
        is already represented by the corresponding ``tool_call`` +
        tool-result pair.
        """
        out = _format_messages([
            {"role": "user", "content": "draw me a chart"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "tc_1",
                    "type": "function",
                    "function": {
                        "name": "render_chart", "arguments": "{}",
                    },
                }],
            },
            {
                "role": "tool",
                "content": "[chart sent]",
                "tool_call_id": "tc_1",
                "name": "render_chart",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "[image attached]"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "media://s/x.png"},
                    },
                ],
                "metadata": {
                    "tool_follow_up": True,
                    "tool_call_id": "tc_1",
                },
            },
            {
                "role": "assistant",
                "content": "Here's the chart you asked for.",
            },
        ])

        # Five inputs → four outputs (the tool_follow_up message is
        # filtered out entirely).
        assert len(out) == 4

        # No remaining message has list-shaped content.
        for m in out:
            assert isinstance(m["content"], str), (
                f"non-string content survived: {m['content']!r}"
            )

        # The tool_calls and tool-result entries are still present so
        # the frontend can rebuild the tool card.
        roles = [m["role"] for m in out]
        assert roles == ["user", "assistant", "tool", "assistant"]

    def test_non_string_content_coerced_to_empty(self) -> None:
        """Defensive guard: any non-string content that *isn't*
        flagged ``tool_follow_up`` (a future code path that persists
        rich content without setting the flag) gets coerced to ``""``
        rather than crashing the frontend. Better to lose the content
        on a single message than to break the whole conversation
        view."""
        out = _format_messages([
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "rogue list content"},
                ],
                # NOTE: no metadata.tool_follow_up — this message
                # would have been the bug shape if not for the
                # defensive coerce.
            },
        ])
        assert len(out) == 1
        assert out[0]["content"] == ""
        assert out[0]["role"] == "user"

    def test_dict_content_coerced_to_empty(self) -> None:
        """Same defence-in-depth as the list case but for dict
        content (no current code path produces this shape, but the
        guard is cheap)."""
        out = _format_messages([
            {"role": "assistant", "content": {"weird": "shape"}},
        ])
        assert out[0]["content"] == ""

    def test_none_content_coerced_to_empty(self) -> None:
        """OpenAI tool-call assistant messages have ``content: None``
        — the original code handled this via ``or ""``. The new
        defensive check should preserve that."""
        out = _format_messages([
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "tc_1",
                    "type": "function",
                    "function": {"name": "x", "arguments": "{}"},
                }],
            },
        ])
        assert out[0]["content"] == ""
        # tool_calls survive the empty-content path so the frontend
        # can still render the tool card.
        assert "tool_calls" in out[0]
