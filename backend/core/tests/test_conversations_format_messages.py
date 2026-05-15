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
        renderer.

        Phase 19 update: the follow-up is no longer dropped — it's
        transformed into a clean ``image`` shape so the chart renders
        inline on resume. The user-visible representation now mirrors
        what Phase 17 produces for live messages.
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

        # Five inputs → five outputs (Phase 19: the tool_follow_up
        # message is now *transformed* to an image entry rather than
        # dropped, so the count matches).
        assert len(out) == 5

        # No remaining message has list-shaped content. Image entries
        # carry their data in ``attachments``, not ``content``.
        for m in out:
            content = m.get("content", "")
            assert isinstance(content, str), (
                f"non-string content survived: {content!r}"
            )

        # The role/shape sequence: user message, assistant tool_call,
        # tool result, image (Phase 19), final assistant text.
        roles = [m["role"] for m in out]
        assert roles == ["user", "assistant", "tool", "assistant", "assistant"]

        # The image entry carries the resolved URL, the tool_call_id
        # for pairing with the tool card, and a kind discriminator.
        image = out[3]
        assert image["kind"] == "image"
        assert image["tool_call_id"] == "tc_1"
        assert len(image["attachments"]) == 1
        assert image["attachments"][0]["url"] == "/api/media/s/x.png"
        assert image["attachments"][0]["mime_type"] == "image/png"

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


class TestImageFollowUpTransform:
    """Phase 19: tool_follow_up entries with image content surface as
    a frontend-friendly ``image`` shape rather than being dropped.
    These tests pin the wire shape so the frontend's
    ``resumeConversation`` renderer can rely on it.
    """

    def test_media_uri_rewritten_to_public_path(self) -> None:
        """``media://session/file`` becomes ``/api/media/session/file``
        — the same rewrite the WebSocket attachment frame applies for
        live messages. Keeps live and resume paths visually identical."""
        out = _format_messages([
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": "media://abc123/cat.png"},
                    },
                ],
                "metadata": {
                    "tool_follow_up": True,
                    "tool_call_id": "tc_42",
                },
            },
        ])
        assert len(out) == 1
        att = out[0]["attachments"][0]
        assert att["url"] == "/api/media/abc123/cat.png"
        assert att["kind"] == "image"
        # tool_call_id flows through so the frontend can pair with
        # the originating tool card.
        assert out[0]["tool_call_id"] == "tc_42"
        # ``kind: image`` is the discriminator.
        assert out[0]["kind"] == "image"
        # Role becomes assistant so the message groups under the
        # same turn as the tool_call.
        assert out[0]["role"] == "assistant"

    def test_http_url_passes_through_unchanged(self) -> None:
        """``echo_image`` produces public ``http(s)://`` URLs that
        already point at fetchable hosts; rewriting would break them.
        Same pass-through logic the WebSocket frame uses."""
        out = _format_messages([
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.com/cat.png"},
                    },
                ],
                "metadata": {
                    "tool_follow_up": True,
                    "tool_call_id": "tc_1",
                },
            },
        ])
        assert out[0]["attachments"][0]["url"] == "https://example.com/cat.png"

    def test_data_url_passes_through_unchanged(self) -> None:
        """A pre-Phase-19 conversation may have stored a data: URL in
        history (the LLM-side materialization wrote one in before we
        stripped it). Those still resolve client-side, so pass them
        through rather than mangling the prefix."""
        out = _format_messages([
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,XYZ"},
                    },
                ],
                "metadata": {
                    "tool_follow_up": True,
                    "tool_call_id": "tc_1",
                },
            },
        ])
        assert out[0]["attachments"][0]["url"] == "data:image/png;base64,XYZ"

    def test_multiple_images_in_one_follow_up(self) -> None:
        """A future tool may emit multiple images in one ToolResult.
        Each ``image_url`` part becomes its own attachment entry in
        the output; the frontend reducer handles caption-once
        semantics if needed."""
        out = _format_messages([
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "two views:"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "media://s/a.png"},
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": "media://s/b.png"},
                    },
                ],
                "metadata": {
                    "tool_follow_up": True,
                    "tool_call_id": "tc_1",
                },
            },
        ])
        assert len(out) == 1
        assert len(out[0]["attachments"]) == 2
        assert out[0]["attachments"][0]["url"] == "/api/media/s/a.png"
        assert out[0]["attachments"][1]["url"] == "/api/media/s/b.png"

    def test_text_only_follow_up_dropped(self) -> None:
        """A future ``tool_follow_up`` carrying only text (no images)
        gets dropped entirely — text follow-ups were always invisible
        to the user, and the tool card already represents the LLM's
        view of the result."""
        out = _format_messages([
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "ok"},
                ],
                "metadata": {
                    "tool_follow_up": True,
                    "tool_call_id": "tc_1",
                },
            },
            {"role": "assistant", "content": "Here you go."},
        ])
        # Only the assistant message survives.
        assert len(out) == 1
        assert out[0]["role"] == "assistant"
        assert out[0]["content"] == "Here you go."

    def test_follow_up_with_string_content_dropped(self) -> None:
        """Defensive: a tool_follow_up message with string content
        (shouldn't happen in practice; the LLM loop always emits a
        list) doesn't crash. Falls through to the
        text-follow-up-dropped path."""
        out = _format_messages([
            {
                "role": "user",
                "content": "ok",
                "metadata": {
                    "tool_follow_up": True,
                    "tool_call_id": "tc_1",
                },
            },
        ])
        assert out == []

    def test_follow_up_without_tool_call_id(self) -> None:
        """``tool_call_id`` is preserved when present but optional —
        a future image-emit code path that doesn't carry one
        (e.g. inline markdown image extraction) still produces a
        valid image entry."""
        out = _format_messages([
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": "media://s/x.png"},
                    },
                ],
                "metadata": {"tool_follow_up": True},  # no tool_call_id
            },
        ])
        assert len(out) == 1
        assert out[0]["kind"] == "image"
        assert "tool_call_id" not in out[0]
