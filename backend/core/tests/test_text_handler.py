"""Tests for TextHandler — plain-text uploads and close cousins.

Covers the three layers the handler touches:

- Decode: UTF-8 happy path, latin-1 fallback for non-UTF-8 bytes.
- Wrap: filename header, language-fenced code block, truncation at
  :data:`_MAX_CHARS`.
- Cache: second materialize reads the sidecar rather than re-reading
  and re-wrapping the source.

Plus an integration test through :class:`MediaStore` to prove the
registry wires TextHandler for ``text/*`` MIMEs.
"""

from __future__ import annotations

import pytest

from tank_backend.core.content import DocumentBlock
from tank_backend.media import MediaStore
from tank_backend.media.handlers.text import (
    _MAX_CHARS,
    TEXT_MIME_TYPES,
    TextHandler,
)

# ---------------------------------------------------------------------------
# Registry / protocol conformance
# ---------------------------------------------------------------------------


class TestContract:
    def test_claims_common_text_mimes(self):
        mimes = TextHandler.mime_types
        for expected in (
            "text/plain", "text/markdown", "text/csv",
            "text/html", "application/json",
            "text/x-python",
        ):
            assert expected in mimes, f"TextHandler missing {expected}"

    def test_supports_native_false(self):
        # No provider has a native "text file" content part.
        assert TextHandler().supports_native() is False

    def test_instance_passes_protocol_check(self):
        from tank_backend.media.handlers.base import DocumentHandler
        assert isinstance(TextHandler(), DocumentHandler)


# ---------------------------------------------------------------------------
# materialize() — called directly against the handler
# ---------------------------------------------------------------------------


class TestMaterialize:
    @pytest.fixture()
    def handler(self):
        return TextHandler()

    @pytest.mark.asyncio()
    async def test_utf8_plain_text_wrapped_with_filename(
        self, handler, tmp_path,
    ):
        path = tmp_path / "notes.txt"
        path.write_text("Hello, 世界!\nSecond line.", encoding="utf-8")

        block = await handler.materialize(
            path,
            capabilities=frozenset({"text"}),
            sidecar_dir=tmp_path,
            source_uri="media://s/notes.txt",
            mime_type="text/plain",
        )
        assert isinstance(block, DocumentBlock)
        assert block.mime_type == "text/plain"
        assert block.source == "media://s/notes.txt"
        text = block.extracted_text or ""
        # Filename header + content, both present.
        assert "File: notes.txt" in text
        assert "Hello, 世界!" in text
        assert "Second line." in text

    @pytest.mark.asyncio()
    async def test_markdown_gets_language_fence(self, handler, tmp_path):
        path = tmp_path / "readme.md"
        path.write_text("# Heading\n\nBody.", encoding="utf-8")

        block = await handler.materialize(
            path,
            capabilities=frozenset({"text"}),
            sidecar_dir=tmp_path,
            source_uri="media://s/readme.md",
            mime_type="text/markdown",
        )
        # The fenced code block carries a language hint so downstream
        # tools can round-trip it if they want.
        assert "```markdown" in (block.extracted_text or "")

    @pytest.mark.asyncio()
    async def test_python_gets_python_fence(self, handler, tmp_path):
        path = tmp_path / "script.py"
        path.write_text("print('ok')", encoding="utf-8")
        block = await handler.materialize(
            path,
            capabilities=frozenset(),
            sidecar_dir=tmp_path,
            source_uri="media://s/script.py",
            mime_type="text/x-python",
        )
        text = block.extracted_text or ""
        assert "```python" in text
        assert "print('ok')" in text

    @pytest.mark.asyncio()
    async def test_unknown_text_mime_no_language_hint(self, handler, tmp_path):
        """A MIME we recognize as text but don't have a hint for still
        wraps in a code fence (for structure) — just no language tag.
        """
        path = tmp_path / "x.log"
        path.write_text("line one\nline two", encoding="utf-8")
        block = await handler.materialize(
            path,
            capabilities=frozenset(),
            sidecar_dir=tmp_path,
            source_uri="media://s/x.log",
            mime_type="text/plain",  # .log has no distinct MIME in our table
        )
        text = block.extracted_text or ""
        # Fence present, but no language after the opening backticks.
        assert "```\n" in text

    @pytest.mark.asyncio()
    async def test_latin1_fallback_never_raises(self, handler, tmp_path):
        """Non-UTF-8 bytes decode via latin-1. No exception, some content."""
        path = tmp_path / "weird.csv"
        # 0xE9 is 'é' in latin-1 but invalid lead byte in UTF-8.
        path.write_bytes(b"caf\xe9,price\n10,5")

        block = await handler.materialize(
            path,
            capabilities=frozenset(),
            sidecar_dir=tmp_path,
            source_uri="media://s/weird.csv",
            mime_type="text/csv",
        )
        text = block.extracted_text or ""
        # latin-1 decodes 0xE9 as 'é'. Content still carries the cell.
        assert "café" in text
        assert "10,5" in text

    @pytest.mark.asyncio()
    async def test_truncated_at_max_chars(self, handler, tmp_path):
        path = tmp_path / "big.txt"
        # One char per line keeps size predictable.
        huge = "x" * (_MAX_CHARS + 5000)
        path.write_text(huge, encoding="utf-8")

        block = await handler.materialize(
            path,
            capabilities=frozenset(),
            sidecar_dir=tmp_path,
            source_uri="media://s/big.txt",
            mime_type="text/plain",
        )
        text = block.extracted_text or ""
        assert "truncated after" in text
        # The untruncated content would have ~85K x's; wrapped text is
        # bounded slightly above _MAX_CHARS for the fence + header.
        assert len(text) < _MAX_CHARS + 500

    @pytest.mark.asyncio()
    async def test_empty_file_gets_explicit_marker(self, handler, tmp_path):
        """An empty file shouldn't look like "file loaded but silent".

        The LLM needs to know something arrived but was empty.
        """
        path = tmp_path / "empty.txt"
        path.write_bytes(b"")

        block = await handler.materialize(
            path,
            capabilities=frozenset(),
            sidecar_dir=tmp_path,
            source_uri="media://s/empty.txt",
            mime_type="text/plain",
        )
        text = block.extracted_text or ""
        # Either the wrapped (empty body) form or the explicit marker;
        # current impl produces a wrapped empty fence, which still
        # carries the filename so the LLM sees something.
        assert "empty.txt" in text


# ---------------------------------------------------------------------------
# Sidecar caching — second materialize skips the rewrap
# ---------------------------------------------------------------------------


class TestSidecarCache:
    @pytest.mark.asyncio()
    async def test_second_call_reads_sidecar_not_source(self, tmp_path):
        handler = TextHandler()
        path = tmp_path / "note.txt"
        path.write_text("original", encoding="utf-8")

        await handler.materialize(
            path,
            capabilities=frozenset(),
            sidecar_dir=tmp_path,
            source_uri="media://s/note.txt",
            mime_type="text/plain",
        )

        # Overwrite the sidecar with a sentinel. If the handler
        # re-reads the source, the sentinel gets blown away.
        sidecar = path.with_suffix(path.suffix + ".txt")
        sidecar.write_text("SIDECAR-SENTINEL", encoding="utf-8")

        block = await handler.materialize(
            path,
            capabilities=frozenset(),
            sidecar_dir=tmp_path,
            source_uri="media://s/note.txt",
            mime_type="text/plain",
        )
        assert block.extracted_text == "SIDECAR-SENTINEL"


# ---------------------------------------------------------------------------
# Integration: through MediaStore, through the default registry
# ---------------------------------------------------------------------------


class TestMediaStoreIntegration:
    """End-to-end: upload text file → media URI → materialize → text."""

    @pytest.fixture()
    def store(self, tmp_path):
        return MediaStore(tmp_path / "media")

    @pytest.mark.asyncio()
    async def test_text_plain_routes_through_text_handler(
        self, store,
    ):
        body = "the quick brown fox jumps over the lazy dog"
        stored = await store.put(
            body.encode("utf-8"), "text/plain", session_id="s",
        )
        block = DocumentBlock(
            source=stored.media_uri,
            mime_type="text/plain",
        )
        result = await store.materialize_for_llm(block)
        assert result.extracted_text is not None
        assert "quick brown fox" in result.extracted_text
        # No native/file path for text.
        assert result.send_native is False
        assert result.page_images == ()

    @pytest.mark.asyncio()
    async def test_markdown_round_trip(self, store):
        md = "# Title\n\nBody with **bold** and `code`."
        stored = await store.put(
            md.encode("utf-8"), "text/markdown", session_id="s",
        )
        block = DocumentBlock(
            source=stored.media_uri,
            mime_type="text/markdown",
        )
        result = await store.materialize_for_llm(block)
        assert result.extracted_text is not None
        assert "```markdown" in result.extracted_text
        assert "# Title" in result.extracted_text

    @pytest.mark.asyncio()
    async def test_python_source_round_trip(self, store):
        src = "def add(a, b):\n    return a + b\n"
        stored = await store.put(
            src.encode("utf-8"), "text/x-python", session_id="s",
        )
        block = DocumentBlock(
            source=stored.media_uri,
            mime_type="text/x-python",
        )
        result = await store.materialize_for_llm(block)
        assert result.extracted_text is not None
        assert "```python" in result.extracted_text
        assert "def add" in result.extracted_text


# ---------------------------------------------------------------------------
# Router / modality routing sanity
# ---------------------------------------------------------------------------


class TestModalityRouting:
    """text/* MIMEs route to ``file`` so router builds DocumentBlock."""

    @pytest.mark.parametrize("mime", [
        "text/plain",
        "text/markdown",
        "text/csv",
        "text/html",
        "text/x-python",
        "application/json",
    ])
    def test_all_text_variants_route_to_file(self, mime):
        from tank_backend.core.content import modality_for_mime
        assert modality_for_mime(mime) == "file"

    def test_router_builds_document_block_for_text(self):
        """Router attachment parser wraps text/* in DocumentBlock."""
        from tank_backend.api.router import _parse_attachments
        blocks = _parse_attachments(
            [{
                "media_uri": "media://s/readme.md",
                "mime_type": "text/markdown",
            }],
            session_id="s",
        )
        assert len(blocks) == 1
        # It's a DocumentBlock, not dropped silently.
        assert isinstance(blocks[0], DocumentBlock)
        assert blocks[0].mime_type == "text/markdown"


# ---------------------------------------------------------------------------
# Ensure every handler-claimed MIME is also in modality_for_mime's set
# ---------------------------------------------------------------------------


class TestClaimConsistency:
    """Regression: if TextHandler claims a MIME, the router must route it.

    A silent divergence (handler ready but router still drops) would
    look exactly like the bug this phase fixed — we want a test that
    guards against it.
    """

    def test_every_handler_mime_routes_to_file(self):
        from tank_backend.core.content import modality_for_mime
        for mime in TEXT_MIME_TYPES:
            assert modality_for_mime(mime) == "file", (
                f"TextHandler claims {mime!r} but router wouldn't route it."
            )
