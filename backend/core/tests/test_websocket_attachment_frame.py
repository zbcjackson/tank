"""Unit tests for Phase 17: WebSocket attachment-frame conversion.

The :func:`tank_backend.api.router._attachment_payload_to_ws_msg`
helper converts an ``outbound_attachment`` bus payload into the
:class:`WebsocketMessage` the frontend consumes. It's pure (no I/O,
no side effects), so we exercise it directly rather than spinning up
a real WebSocket session.

Behaviour we pin here:

- ``media://<session>/<file>`` URIs are rewritten to
  ``/api/media/<session>/<file>`` so the browser can fetch them via
  ``<img src>``.
- ``http(s)://`` URIs pass through unchanged (e.g. ``echo_image``
  produces these).
- Non-image blocks are skipped.
- Empty/all-non-image payloads return ``None`` so the WS endpoint
  doesn't emit a frame with no attachments.
- ``caption`` rides on the converted frame's ``content`` field AND
  on each attachment, so clients that ignore the ``attachments``
  array still see the text.
- ``msg_id`` is forwarded so the frontend reducer can group images
  with surrounding text in the same conversation turn.
"""

from __future__ import annotations

from tank_backend.api.router import _attachment_payload_to_ws_msg
from tank_backend.api.schemas import MessageType
from tank_backend.core.content import DocumentBlock, ImageBlock, TextBlock


class TestMediaUriRewrite:
    def test_media_uri_rewritten_to_public_path(self) -> None:
        """``media://s1/abc.jpg`` becomes ``/api/media/s1/abc.jpg`` so
        the browser hits the Phase-17 ``GET /api/media/...`` endpoint
        we ship for serving stored bytes."""
        payload = {
            "msg_id": "m-42",
            "blocks": [
                ImageBlock(source="media://s1/abc.jpg", mime_type="image/jpeg"),
            ],
            "caption": "Look here:",
        }
        ws_msg = _attachment_payload_to_ws_msg(payload, session_id="s1")

        assert ws_msg is not None
        assert ws_msg.type is MessageType.ATTACHMENT
        assert len(ws_msg.attachments) == 1
        att = ws_msg.attachments[0]
        assert att.url == "/api/media/s1/abc.jpg"
        assert att.mime_type == "image/jpeg"
        assert att.caption == "Look here:"
        # Caption also rides on the top-level content for clients that
        # ignore the ``attachments`` array.
        assert ws_msg.content == "Look here:"
        assert ws_msg.msg_id == "m-42"
        assert ws_msg.session_id == "s1"
        assert ws_msg.is_user is False
        # Attachment frames are always final — there's no streaming
        # an image one byte at a time.
        assert ws_msg.is_final is True

    def test_http_url_passes_through_unchanged(self) -> None:
        """``echo_image`` produces ``http(s)://`` URLs that already
        point at public hosts; rewriting them would break things.
        Pin the pass-through so a future refactor doesn't accidentally
        prefix ``/api/media/`` to URLs it shouldn't."""
        payload = {
            "blocks": [
                ImageBlock(
                    source="https://example.com/cat.jpg",
                    mime_type="image/jpeg",
                ),
            ],
            "caption": None,
        }
        ws_msg = _attachment_payload_to_ws_msg(payload, session_id="s1")

        assert ws_msg is not None
        att = ws_msg.attachments[0]
        assert att.url == "https://example.com/cat.jpg"
        # Caption was None — translates to empty string at the top
        # level (Pydantic default) and ``None`` on the attachment.
        assert ws_msg.content == ""
        assert att.caption is None


class TestNonImageHandling:
    def test_text_blocks_silently_skipped(self) -> None:
        """The bus payload may carry mixed blocks (TextBlock describing
        the image, then the ImageBlock). The WS frame is image-only —
        the surrounding text rides on the ``caption`` field, not as a
        separate block, so TextBlock entries are dropped here."""
        payload = {
            "blocks": [
                TextBlock(text="Here you go:"),
                ImageBlock(
                    source="https://example.com/x.png", mime_type="image/png",
                ),
                TextBlock(text="(generated 1ms ago)"),
            ],
            "caption": "Result",
        }
        ws_msg = _attachment_payload_to_ws_msg(payload, session_id="s1")
        assert ws_msg is not None
        assert len(ws_msg.attachments) == 1

    def test_document_blocks_skipped(self) -> None:
        """Future tools may emit DocumentBlock; until the frontend
        learns to render them, the WS endpoint drops them rather than
        sending a half-supported payload."""
        payload = {
            "blocks": [
                DocumentBlock(source="https://x/a.pdf", mime_type="application/pdf"),
                ImageBlock(source="https://x/a.png", mime_type="image/png"),
            ],
            "caption": "doc + image",
        }
        ws_msg = _attachment_payload_to_ws_msg(payload, session_id="s1")
        assert ws_msg is not None
        # Only the image block survived.
        assert len(ws_msg.attachments) == 1
        assert ws_msg.attachments[0].url == "https://x/a.png"

    def test_empty_blocks_returns_none(self) -> None:
        """No images → no frame. Returning ``None`` lets the WS
        endpoint short-circuit instead of sending an ATTACHMENT frame
        with an empty attachments array (the frontend would render an
        empty bubble, which is worse than dropping silently)."""
        assert _attachment_payload_to_ws_msg(
            {"blocks": [], "caption": "x"}, session_id="s1",
        ) is None

    def test_only_non_image_blocks_returns_none(self) -> None:
        payload = {
            "blocks": [TextBlock(text="hi")],
            "caption": "x",
        }
        assert _attachment_payload_to_ws_msg(payload, session_id="s1") is None


class TestMultipleAttachments:
    def test_each_image_becomes_its_own_attachment(self) -> None:
        """Phase 15 shipped caption-only-on-first-attachment via the
        connector dispatcher; the WS path mirrors that semantically.
        The caption on the bus payload is one string for the whole
        batch — every WebsocketAttachment gets a copy on the wire,
        and the frontend reducer is the one that decides to only
        display the caption above the first image."""
        payload = {
            "blocks": [
                ImageBlock(source="media://s1/a.jpg", mime_type="image/jpeg"),
                ImageBlock(source="media://s1/b.jpg", mime_type="image/jpeg"),
            ],
            "caption": "Two views:",
        }
        ws_msg = _attachment_payload_to_ws_msg(payload, session_id="s1")

        assert ws_msg is not None
        assert len(ws_msg.attachments) == 2
        assert [a.url for a in ws_msg.attachments] == [
            "/api/media/s1/a.jpg",
            "/api/media/s1/b.jpg",
        ]
        # Both carry the caption; reducer dedupes on the frontend.
        assert all(a.caption == "Two views:" for a in ws_msg.attachments)


class TestEdgeCases:
    def test_missing_caption_key_treated_as_none(self) -> None:
        """Older callers (or a future code path that doesn't pass
        captions) may omit the key entirely. The converter must not
        ``KeyError`` — the caption goes to ``None``."""
        payload = {
            "blocks": [
                ImageBlock(source="https://x/a.png", mime_type="image/png"),
            ],
        }
        ws_msg = _attachment_payload_to_ws_msg(payload, session_id="s1")
        assert ws_msg is not None
        assert ws_msg.attachments[0].caption is None

    def test_block_without_mime_type_uses_default(self) -> None:
        """``ImageBlock.mime_type`` is optional; the WS shape requires
        a string. Falls back to ``image/jpeg`` so the frontend's
        ``<img>`` tag has something coherent to send in any future
        ``Accept`` headers."""
        # Construct via positional arg only — Phase 17 ImageBlock has
        # mime_type defaulting; the test pins behaviour even if the
        # dataclass default changes.
        block = ImageBlock(source="https://x/y.jpg", mime_type="")
        ws_msg = _attachment_payload_to_ws_msg(
            {"blocks": [block]}, session_id="s1",
        )
        assert ws_msg is not None
        assert ws_msg.attachments[0].mime_type == "image/jpeg"
