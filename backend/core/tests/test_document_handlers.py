"""Tests for the DocumentHandler seam and OCP demonstration.

Three layers under test:

1. :class:`DocumentHandlerRegistry` — pure lookup/register mechanics.
2. Handler contract — both shipped handlers (PDF, Office) implement
   the protocol in the way the store relies on.
3. OCP demonstration — a custom handler for a new MIME type plugs in
   via ``MediaStore(handlers=...)`` with no store-level code changes.

The OCP test is the one worth reading if you're evaluating the
refactor: if that test needed to touch ``store.py``, the seam would
be leaking. The fact that a completely fictional MIME type works via
pure registration proves the abstraction.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tank_backend.core.content import DocumentBlock
from tank_backend.media import MediaStore
from tank_backend.media.handlers import (
    DocumentHandler,
    DocumentHandlerRegistry,
    OfficeHandler,
    PdfHandler,
    default_registry,
)

# ---------------------------------------------------------------------------
# Registry mechanics
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_register_and_lookup(self):
        reg = DocumentHandlerRegistry()
        reg.register(PdfHandler())
        hit = reg.lookup("application/pdf")
        assert hit is not None
        assert isinstance(hit, PdfHandler)

    def test_unknown_mime_returns_none(self):
        reg = DocumentHandlerRegistry()
        assert reg.lookup("application/x-unknown") is None

    def test_later_registration_overrides_earlier(self):
        """A second register() call for the same MIME replaces the first.

        Important for user-side customisation: you can't extend an
        installed handler without re-registering, and that's the
        explicit, auditable way to do it.
        """
        reg = DocumentHandlerRegistry()
        first = PdfHandler()
        reg.register(first)

        # A stub that also claims application/pdf.
        class StubPdfHandler(DocumentHandler):
            mime_types = frozenset({"application/pdf"})

            def supports_native(self) -> bool:
                return False

            async def materialize(
                self, path, *, capabilities, sidecar_dir,
                source_uri, mime_type,
            ):
                return DocumentBlock(
                    source=source_uri, mime_type=mime_type,
                    extracted_text="stub",
                )

        second = StubPdfHandler()
        reg.register(second)
        assert reg.lookup("application/pdf") is second

    def test_mime_types_aggregate(self):
        """``mime_types()`` returns every registered MIME."""
        reg = DocumentHandlerRegistry()
        reg.register(PdfHandler())
        reg.register(OfficeHandler())
        mimes = reg.mime_types()
        assert "application/pdf" in mimes
        assert "application/vnd.openxmlformats-officedocument." \
               "wordprocessingml.document" in mimes

    def test_handler_covering_multiple_mimes_registers_each(self):
        """OfficeHandler declares 3 MIMEs — all lookup to the same instance."""
        reg = DocumentHandlerRegistry()
        h = OfficeHandler()
        reg.register(h)
        for mime in h.mime_types:
            assert reg.lookup(mime) is h


# ---------------------------------------------------------------------------
# Shipped handlers match the Protocol
# ---------------------------------------------------------------------------


class TestShippedHandlers:
    @pytest.mark.parametrize(
        "handler_cls",
        [PdfHandler, OfficeHandler],
    )
    def test_shipped_handlers_implement_protocol(self, handler_cls):
        h = handler_cls()
        # runtime_checkable: isinstance matches structural shape.
        assert isinstance(h, DocumentHandler)

    def test_default_registry_has_expected_mimes(self):
        """Default registry wires up PDF and Office out of the box.

        This is the contract the UI / /api/upload relies on; if a
        future edit silently drops a handler, this test fails.
        """
        mimes = default_registry.mime_types()
        assert "application/pdf" in mimes
        office = "application/vnd.openxmlformats-officedocument."
        assert f"{office}wordprocessingml.document" in mimes
        assert f"{office}spreadsheetml.sheet" in mimes
        assert f"{office}presentationml.presentation" in mimes

    def test_pdf_supports_native_true(self):
        assert PdfHandler().supports_native() is True

    def test_office_supports_native_false(self):
        """Office isn't accepted natively by any provider today."""
        assert OfficeHandler().supports_native() is False


# ---------------------------------------------------------------------------
# OCP demonstration — new format via registration only
# ---------------------------------------------------------------------------


class _MarkdownHandler(DocumentHandler):
    """Toy handler for ``text/markdown``.

    Exists only for this test suite. Demonstrates that adding a new
    document format requires zero changes to ``store.py`` — implement
    the protocol, register, done.
    """

    mime_types: frozenset[str] = frozenset({"text/markdown"})

    def supports_native(self) -> bool:
        return False

    async def materialize(
        self,
        path: Path,
        *,
        capabilities: frozenset[str],
        sidecar_dir: Path,
        source_uri: str,
        mime_type: str,
    ) -> DocumentBlock:
        text = path.read_text(encoding="utf-8")
        return DocumentBlock(
            source=source_uri,
            mime_type=mime_type,
            extracted_text=f"# Rendered markdown\n\n{text}",
        )


class TestOpenClosedPrinciple:
    """A new handler plugs in via MediaStore(handlers=...) with no store edits."""

    @pytest.fixture()
    def store_with_markdown(self, tmp_path):
        """MediaStore injected with a custom registry that includes markdown."""
        reg = DocumentHandlerRegistry()
        reg.register(PdfHandler())
        reg.register(OfficeHandler())
        reg.register(_MarkdownHandler())
        return MediaStore(tmp_path / "media", handlers=reg)

    @pytest.mark.asyncio()
    async def test_custom_markdown_handler_dispatched(
        self, store_with_markdown,
    ):
        md_body = textwrap.dedent(
            """
            hello world
            some prose here
            """
        ).strip()
        stored = await store_with_markdown.put(
            md_body.encode("utf-8"),
            "text/markdown",
            session_id="s",
        )

        block = DocumentBlock(
            source=stored.media_uri,
            mime_type="text/markdown",
        )
        result = await store_with_markdown.materialize_for_llm(block)

        # The toy handler prefixed a header — proves it ran.
        assert result.extracted_text is not None
        assert "# Rendered markdown" in result.extracted_text
        assert "hello world" in result.extracted_text
        # Source URI preserved so persistence is replayable.
        assert result.source == stored.media_uri

    @pytest.mark.asyncio()
    async def test_default_store_rejects_unknown_mime(self, tmp_path):
        """Default registry doesn't know markdown → placeholder."""
        store = MediaStore(tmp_path / "media")  # default_registry
        await store.put(b"# hi", "text/markdown", session_id="s")

        block = DocumentBlock(
            source="media://s/ignored.md",  # path doesn't matter here
            mime_type="text/markdown",
        )
        # Force the lookup miss path by using a block whose source
        # happens to match a real stored file in a different dir.
        result = await store.materialize_for_llm(
            DocumentBlock(
                source=block.source,
                mime_type="text/markdown",
            ),
        )
        assert result.extracted_text is not None
        assert "extraction not supported" in result.extracted_text

    @pytest.mark.asyncio()
    async def test_handler_receives_capabilities(self, tmp_path):
        """The handler gets the LLM caps so format-specific waterfalls work."""
        seen: dict[str, frozenset[str]] = {}

        class RecordingHandler(DocumentHandler):
            mime_types = frozenset({"application/x-test"})

            def supports_native(self) -> bool:
                return False

            async def materialize(
                self, path, *, capabilities, sidecar_dir,
                source_uri, mime_type,
            ):
                seen["caps"] = capabilities
                return DocumentBlock(
                    source=source_uri, mime_type=mime_type,
                    extracted_text="ok",
                )

        reg = DocumentHandlerRegistry()
        reg.register(RecordingHandler())
        store = MediaStore(tmp_path / "media", handlers=reg)

        await store.put(b"bytes", "application/x-test", session_id="s")
        # Need a real file at the materialized path for the store to
        # resolve the URI — upload path put() produced one.
        # Find the real media URI via a fresh put and reuse it.
        stored = await store.put(b"bytes", "application/x-test", session_id="s")
        block = DocumentBlock(
            source=stored.media_uri,
            mime_type="application/x-test",
        )
        await store.materialize_for_llm(
            block,
            capabilities=frozenset({"text", "image", "file"}),
        )
        assert seen["caps"] == frozenset({"text", "image", "file"})

    @pytest.mark.asyncio()
    async def test_handler_can_override_default(self, tmp_path):
        """Registering PDF in a custom registry replaces the default.

        This is the legitimate extensibility path: a downstream project
        swaps in its own PdfHandler variant (say, one that pre-OCRs
        scanned docs) by building a registry and injecting it into
        MediaStore.
        """

        class AuditingPdfHandler(DocumentHandler):
            mime_types = frozenset({"application/pdf"})

            def supports_native(self) -> bool:
                return True

            async def materialize(
                self, path, *, capabilities, sidecar_dir,
                source_uri, mime_type,
            ):
                return DocumentBlock(
                    source=source_uri, mime_type=mime_type,
                    extracted_text="[AUDIT-HANDLER-RAN]",
                )

        reg = DocumentHandlerRegistry()
        reg.register(AuditingPdfHandler())  # overrides the default PDF handler
        store = MediaStore(tmp_path / "media", handlers=reg)

        stored = await store.put(
            b"%PDF-fake", "application/pdf", session_id="s",
        )
        block = DocumentBlock(
            source=stored.media_uri,
            mime_type="application/pdf",
        )
        result = await store.materialize_for_llm(block)
        assert result.extracted_text == "[AUDIT-HANDLER-RAN]"


# ---------------------------------------------------------------------------
# Passthrough semantics — store delegates, doesn't re-process
# ---------------------------------------------------------------------------


class TestPassthroughBypassesHandlers:
    """Already-materialized blocks skip the handler layer entirely.

    This matters for replay from persisted history: a stored block
    that already has extracted_text shouldn't re-run extraction the
    next turn.
    """

    @pytest.mark.asyncio()
    async def test_block_with_text_skips_handler(self, tmp_path):
        """A DocumentBlock with extracted_text comes back unchanged."""
        calls: list[str] = []

        class ForbiddenHandler(DocumentHandler):
            mime_types = frozenset({"application/pdf"})

            def supports_native(self) -> bool:
                return False

            async def materialize(
                self, path, *, capabilities, sidecar_dir,
                source_uri, mime_type,
            ):
                calls.append("materialize")
                return DocumentBlock(
                    source=source_uri, mime_type=mime_type,
                    extracted_text="should not be called",
                )

        reg = DocumentHandlerRegistry()
        reg.register(ForbiddenHandler())
        store = MediaStore(tmp_path / "media", handlers=reg)

        block = DocumentBlock(
            source="media://s/whatever.pdf",
            mime_type="application/pdf",
            extracted_text="already done",
        )
        result = await store.materialize_for_llm(block)
        assert result.extracted_text == "already done"
        assert calls == []

    @pytest.mark.asyncio()
    async def test_block_with_send_native_skips_handler(self, tmp_path):
        """A pre-built native block passes through unchanged."""
        reg = DocumentHandlerRegistry()
        reg.register(PdfHandler())
        store = MediaStore(tmp_path / "media", handlers=reg)

        block = DocumentBlock(
            source="data:application/pdf;base64,JVBERi0xLjQ=",
            mime_type="application/pdf",
            send_native=True,
        )
        result = await store.materialize_for_llm(block)
        # Passthrough preserves the native marker.
        assert result.send_native is True
        assert result.source == block.source
