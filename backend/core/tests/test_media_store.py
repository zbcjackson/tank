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
