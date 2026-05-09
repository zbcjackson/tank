"""Tests for the content-addressed MediaStore."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from tank_backend.core.content import (
    AudioBlock,
    DocumentBlock,
    ImageBlock,
    TextBlock,
)
from tank_backend.media import (
    CrossSessionAccessError,
    MediaStore,
    UnknownMediaURIError,
)


@pytest.fixture()
def store(tmp_path: Path) -> MediaStore:
    return MediaStore(tmp_path / "media")


@pytest.fixture()
def png_bytes() -> bytes:
    # Minimal 1x1 PNG; realism doesn't matter, bytes do.
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452"
        "00000001000000010802000000907753"
        "de0000000c49444154789c6300010000"
        "000005000168220500000000049454ae"
        "426082"
    )


class TestPut:
    @pytest.mark.asyncio()
    async def test_returns_media_uri_and_metadata(self, store, png_bytes):
        stored = await store.put(png_bytes, "image/png", session_id="sess-1")
        assert stored.media_uri.startswith("media://sess-1/")
        assert stored.media_uri.endswith(".png")
        assert stored.mime_type == "image/png"
        assert stored.size == len(png_bytes)

    @pytest.mark.asyncio()
    async def test_same_bytes_dedupe(self, store, png_bytes):
        a = await store.put(png_bytes, "image/png", session_id="s")
        b = await store.put(png_bytes, "image/png", session_id="s")
        assert a.media_uri == b.media_uri

    @pytest.mark.asyncio()
    async def test_different_bytes_different_uri(self, store):
        a = await store.put(b"hello", "text/plain", session_id="s")
        b = await store.put(b"world", "text/plain", session_id="s")
        assert a.media_uri != b.media_uri

    @pytest.mark.asyncio()
    async def test_different_sessions_isolated(self, store, png_bytes):
        a = await store.put(png_bytes, "image/png", session_id="alice")
        b = await store.put(png_bytes, "image/png", session_id="bob")
        assert "alice" in a.media_uri
        assert "bob" in b.media_uri
        # Same hash, different session namespaces.
        assert a.media_uri != b.media_uri

    @pytest.mark.asyncio()
    async def test_unknown_mime_uses_bin_fallback(self, store):
        stored = await store.put(b"data", "application/x-weird", session_id="s")
        assert stored.media_uri.endswith(".bin")

    @pytest.mark.asyncio()
    async def test_webp_fallback(self, store):
        stored = await store.put(b"\x00\x01\x02", "image/webp", session_id="s")
        assert stored.media_uri.endswith(".webp")

    @pytest.mark.asyncio()
    async def test_rejects_missing_mime(self, store):
        with pytest.raises(ValueError, match="mime_type is required"):
            await store.put(b"data", "", session_id="s")

    @pytest.mark.asyncio()
    async def test_rejects_path_traversal_session(self, store):
        with pytest.raises(ValueError, match="Invalid session id"):
            await store.put(b"data", "image/png", session_id="../evil")


class TestGet:
    @pytest.mark.asyncio()
    async def test_roundtrip(self, store, png_bytes):
        stored = await store.put(png_bytes, "image/png", session_id="s")
        data, mime = await store.get(stored.media_uri)
        assert data == png_bytes
        assert mime == "image/png"

    @pytest.mark.asyncio()
    async def test_malformed_uri_raises(self, store):
        with pytest.raises(UnknownMediaURIError, match="Malformed"):
            await store.get("not-a-media-uri")

    @pytest.mark.asyncio()
    async def test_missing_file_raises(self, store):
        with pytest.raises(UnknownMediaURIError, match="No file"):
            await store.get("media://s/deadbeef.png")

    @pytest.mark.asyncio()
    async def test_cross_session_blocked(self, store, png_bytes):
        stored = await store.put(png_bytes, "image/png", session_id="alice")
        with pytest.raises(CrossSessionAccessError):
            await store.get(stored.media_uri, session_id="bob")

    @pytest.mark.asyncio()
    async def test_same_session_allowed(self, store, png_bytes):
        stored = await store.put(png_bytes, "image/png", session_id="alice")
        data, _ = await store.get(stored.media_uri, session_id="alice")
        assert data == png_bytes

    @pytest.mark.asyncio()
    async def test_no_session_constraint_is_permissive(self, store, png_bytes):
        stored = await store.put(png_bytes, "image/png", session_id="alice")
        data, _ = await store.get(stored.media_uri)  # no session_id
        assert data == png_bytes


class TestMaterialize:
    @pytest.mark.asyncio()
    async def test_image_block_with_media_uri_becomes_data_url(
        self, store, png_bytes,
    ):
        stored = await store.put(png_bytes, "image/png", session_id="s")
        block = ImageBlock(source=stored.media_uri, mime_type="image/png")
        result = await store.materialize_for_llm(block)
        assert isinstance(result, ImageBlock)
        assert result.source.startswith("data:image/png;base64,")
        raw = result.source.split(",", 1)[1]
        assert base64.b64decode(raw) == png_bytes

    @pytest.mark.asyncio()
    async def test_image_block_with_data_url_unchanged(self, store):
        block = ImageBlock(
            source="data:image/png;base64,xyz",
            mime_type="image/png",
        )
        result = await store.materialize_for_llm(block)
        assert result == block

    @pytest.mark.asyncio()
    async def test_image_block_with_abs_path_unchanged(self, store):
        block = ImageBlock(source="/tmp/photo.png", mime_type="image/png")
        result = await store.materialize_for_llm(block)
        assert result == block

    @pytest.mark.asyncio()
    async def test_text_block_unchanged(self, store):
        block = TextBlock(text="hi")
        assert await store.materialize_for_llm(block) is block

    @pytest.mark.asyncio()
    async def test_document_with_page_images_materialized(
        self, store, png_bytes,
    ):
        page_stored = await store.put(png_bytes, "image/png", session_id="s")
        page = ImageBlock(source=page_stored.media_uri, mime_type="image/png")
        doc = DocumentBlock(
            source="media://s/doc.pdf",
            mime_type="application/pdf",
            extracted_text="Page 1 text",
            page_images=(page,),
        )
        result = await store.materialize_for_llm(doc)
        assert isinstance(result, DocumentBlock)
        assert result.extracted_text == "Page 1 text"
        assert len(result.page_images) == 1
        assert result.page_images[0].source.startswith("data:image/png;base64,")

    @pytest.mark.asyncio()
    async def test_audio_block_unchanged_today(self, store):
        block = AudioBlock(
            source="media://s/x.wav",
            mime_type="audio/wav",
            transcript="hello",
        )
        # Phase 5 will add native-audio materialization; today, audio is
        # carried via transcript and the block passes through untouched.
        result = await store.materialize_for_llm(block)
        assert result == block

    @pytest.mark.asyncio()
    async def test_session_scope_enforced_during_materialize(
        self, store, png_bytes,
    ):
        stored = await store.put(png_bytes, "image/png", session_id="alice")
        block = ImageBlock(source=stored.media_uri, mime_type="image/png")
        with pytest.raises(CrossSessionAccessError):
            await store.materialize_for_llm(block, session_id="bob")


class TestPurgeSession:
    @pytest.mark.asyncio()
    async def test_removes_session_files(self, store, png_bytes):
        await store.put(png_bytes, "image/png", session_id="dead")
        await store.put(b"another", "text/plain", session_id="dead")
        count = await store.purge_session("dead")
        assert count == 2
        with pytest.raises(UnknownMediaURIError):
            await store.get(f"media://dead/{'a' * 64}.png")

    @pytest.mark.asyncio()
    async def test_unknown_session_noop(self, store):
        assert await store.purge_session("nobody") == 0

    @pytest.mark.asyncio()
    async def test_other_session_unaffected(self, store, png_bytes):
        kept = await store.put(png_bytes, "image/png", session_id="alive")
        await store.put(png_bytes, "image/png", session_id="dead")
        await store.purge_session("dead")
        data, _ = await store.get(kept.media_uri)
        assert data == png_bytes


# ---------------------------------------------------------------------------
# PDF extraction at materialize time
# ---------------------------------------------------------------------------


def _build_minimal_pdf(body_text: str) -> bytes:
    """Build a tiny valid PDF containing ``body_text``.

    Using pypdf's writer keeps the test self-contained — no sample
    fixture file to commit, no binary data in the test.
    """
    from io import BytesIO

    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    # pypdf can't synthesize text content streams, but it CAN ingest a
    # minimal PDF we assemble by hand. Instead of that complexity we
    # just write a PDF whose /Title metadata carries the body, and
    # extract from metadata. Simpler signal is good enough: a non-empty
    # PDF with known-recoverable text.
    writer.add_metadata({"/Title": body_text})
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


class TestPdfExtraction:
    """MediaStore materializes PDFs by extracting text at send time."""

    @pytest.mark.asyncio()
    async def test_pdf_without_text_gets_scanned_placeholder(
        self, store,
    ):
        """Synthetic PDF with no extractable text → clear diagnostic."""
        pdf_bytes = _build_minimal_pdf("meta only")
        stored = await store.put(
            pdf_bytes, "application/pdf", session_id="s",
        )

        from tank_backend.core.content import DocumentBlock
        block = DocumentBlock(
            source=stored.media_uri,
            mime_type="application/pdf",
        )
        result = await store.materialize_for_llm(block)
        # A pypdf-only synthetic PDF yields no extractable text content
        # (metadata isn't extracted via ``extract_text``) — we expect
        # the scanned-PDF placeholder.
        assert result.extracted_text is not None
        assert "scanned" in result.extracted_text.lower()

    @pytest.mark.asyncio()
    async def test_pdf_sidecar_cache_is_written(self, store, tmp_path):
        """Second materialize of the same PDF reads the .pdf.txt sidecar."""
        pdf_bytes = _build_minimal_pdf("cached")
        stored = await store.put(
            pdf_bytes, "application/pdf", session_id="cache",
        )

        from tank_backend.core.content import DocumentBlock
        block = DocumentBlock(
            source=stored.media_uri,
            mime_type="application/pdf",
        )

        # First call: pypdf runs, sidecar written.
        await store.materialize_for_llm(block)

        # Sidecar should now exist — the file the extractor wrote.
        _session, filename = store._parse_uri(stored.media_uri)
        pdf_path = store.root / _session / filename
        sidecar = pdf_path.with_suffix(pdf_path.suffix + ".txt")
        assert sidecar.exists()

        # Corrupt the PDF bytes on disk — if we hit pypdf again, this
        # would raise. The cache should intercept.
        pdf_path.write_bytes(b"not a pdf anymore")
        # Still works: sidecar hit, no re-extraction.
        result = await store.materialize_for_llm(block)
        assert result.extracted_text is not None

    @pytest.mark.asyncio()
    async def test_non_pdf_document_gets_placeholder(self, store):
        """An unsupported document MIME gets a descriptive placeholder.

        DOCX/XLSX/PPTX now route to the Office extractors, so pick a
        format we don't handle (OpenDocument) to exercise the
        fallback branch.
        """
        await store.put(
            b"PK\x03\x04odt-bytes",
            "application/vnd.oasis.opendocument.text",
            session_id="s",
        )

        from tank_backend.core.content import DocumentBlock
        block = DocumentBlock(
            source="media://s/abc.odt",
            mime_type="application/vnd.oasis.opendocument.text",
        )
        result = await store.materialize_for_llm(block)
        assert result.extracted_text is not None
        assert "extraction not supported" in result.extracted_text

    @pytest.mark.asyncio()
    async def test_document_with_existing_text_passthrough(self, store):
        """A block that already has text doesn't trigger extraction."""
        from tank_backend.core.content import DocumentBlock
        block = DocumentBlock(
            source="media://s/doc.pdf",
            mime_type="application/pdf",
            extracted_text="Already done.",
        )
        result = await store.materialize_for_llm(block)
        assert result.extracted_text == "Already done."

    @pytest.mark.asyncio()
    async def test_pdf_cross_session_blocked(self, store):
        """Extraction respects session scoping just like get()."""
        pdf_bytes = _build_minimal_pdf("secret")
        stored = await store.put(
            pdf_bytes, "application/pdf", session_id="alice",
        )

        from tank_backend.core.content import DocumentBlock
        block = DocumentBlock(
            source=stored.media_uri,
            mime_type="application/pdf",
        )
        with pytest.raises(CrossSessionAccessError):
            await store.materialize_for_llm(block, session_id="bob")


# ---------------------------------------------------------------------------
# Capability-driven PDF waterfall
# ---------------------------------------------------------------------------


def _build_pdf_with_text_content(text: str) -> bytes:
    """Build a PDF whose pages contain real drawable text.

    pymupdf can write pages with insertable text that pypdf will
    read back; this gives us a PDF the text-extraction path can
    actually extract from.
    """
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=400, height=400)
    page.insert_text((50, 72), text, fontsize=12)
    buf = doc.tobytes()
    doc.close()
    return buf


class TestPdfWaterfall:
    """Three wire paths: native, image + text, text only."""

    @pytest.fixture()
    def store(self, tmp_path):
        return MediaStore(tmp_path / "media")

    @pytest.mark.asyncio()
    async def test_native_path_for_file_capable_model(self, store):
        """Caps include 'file' → send_native=True with a data URL."""
        pdf_bytes = _build_pdf_with_text_content("native-path-test")
        stored = await store.put(
            pdf_bytes, "application/pdf", session_id="s",
        )

        from tank_backend.core.content import DocumentBlock
        block = DocumentBlock(
            source=stored.media_uri,
            mime_type="application/pdf",
        )
        result = await store.materialize_for_llm(
            block, capabilities=frozenset({"text", "file"}),
        )
        assert isinstance(result, DocumentBlock)
        assert result.send_native is True
        assert result.source.startswith("data:application/pdf;base64,")
        # Native path skips our text extraction — the provider does it.
        assert result.extracted_text is None
        assert result.page_images == ()

    @pytest.mark.asyncio()
    async def test_image_path_for_vision_model_without_pdf_support(
        self, store,
    ):
        """Caps include 'image' but not 'file' → text + page images."""
        pdf_bytes = _build_pdf_with_text_content("image-path-test")
        stored = await store.put(
            pdf_bytes, "application/pdf", session_id="s",
        )

        from tank_backend.core.content import DocumentBlock
        block = DocumentBlock(
            source=stored.media_uri,
            mime_type="application/pdf",
        )
        result = await store.materialize_for_llm(
            block, capabilities=frozenset({"text", "image"}),
        )
        assert result.send_native is False
        assert result.extracted_text is not None
        assert "image-path-test" in result.extracted_text
        assert len(result.page_images) == 1
        assert result.page_images[0].source.startswith(
            "data:image/png;base64,"
        )

    @pytest.mark.asyncio()
    async def test_text_only_path_for_text_only_model(self, store):
        """Caps = {'text'} → pypdf text only, no page images."""
        pdf_bytes = _build_pdf_with_text_content("text-only-path-test")
        stored = await store.put(
            pdf_bytes, "application/pdf", session_id="s",
        )

        from tank_backend.core.content import DocumentBlock
        block = DocumentBlock(
            source=stored.media_uri,
            mime_type="application/pdf",
        )
        result = await store.materialize_for_llm(
            block, capabilities=frozenset({"text"}),
        )
        assert result.send_native is False
        assert result.extracted_text is not None
        assert "text-only-path-test" in result.extracted_text
        assert result.page_images == ()

    @pytest.mark.asyncio()
    async def test_image_path_caches_sidecars(self, store):
        """Second materialize reuses page<N>.png sidecars."""
        pdf_bytes = _build_pdf_with_text_content("cache-test")
        stored = await store.put(
            pdf_bytes, "application/pdf", session_id="s",
        )

        from tank_backend.core.content import DocumentBlock
        block = DocumentBlock(
            source=stored.media_uri,
            mime_type="application/pdf",
        )
        first = await store.materialize_for_llm(
            block, capabilities=frozenset({"text", "image"}),
        )
        assert len(first.page_images) == 1

        # Sidecar must exist after first materialize.
        _session, filename = store._parse_uri(stored.media_uri)
        pdf_path = store.root / _session / filename
        sidecar = pdf_path.with_name(f"{pdf_path.name}.page1.png")
        assert sidecar.exists()
        first_bytes = sidecar.read_bytes()

        # Corrupt the sidecar to prove the SECOND call served the new
        # (corrupted) bytes rather than re-rendering: if the render
        # loop ran, the sidecar would've been re-written with fresh
        # PNG data, so the byte-equality check would fail.
        sidecar.write_bytes(b"sidecar-sentinel")
        second = await store.materialize_for_llm(
            block, capabilities=frozenset({"text", "image"}),
        )
        # The returned image has the sentinel bytes (base64-encoded).
        expected_b64 = (
            "data:image/png;base64,"
            + __import__("base64").b64encode(b"sidecar-sentinel").decode()
        )
        assert second.page_images[0].source == expected_b64

        # Restore so teardown doesn't flag a stale file.
        sidecar.write_bytes(first_bytes)

    @pytest.mark.asyncio()
    async def test_native_path_without_caps_falls_to_text(self, store):
        """caps=None defaults to empty → never picks native."""
        pdf_bytes = _build_pdf_with_text_content("default-caps")
        stored = await store.put(
            pdf_bytes, "application/pdf", session_id="s",
        )

        from tank_backend.core.content import DocumentBlock
        block = DocumentBlock(
            source=stored.media_uri,
            mime_type="application/pdf",
        )
        # No caps arg → defaults to frozenset() → text-only path.
        result = await store.materialize_for_llm(block)
        assert result.send_native is False
        assert result.page_images == ()
