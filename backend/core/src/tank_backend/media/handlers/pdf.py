"""PDF handler — native → image+text → text waterfall.

Encapsulates the entire PDF materialization strategy that used to live
in :class:`MediaStore`. The store now just dispatches; this handler
owns the policy.

Wire paths, selected by the LLM's ``capabilities``:

1. ``"file"`` in caps → hand the raw PDF bytes as a data URL with
   ``send_native=True``. Provider renders + extracts server-side.
   Best fidelity, cheapest tokens.
2. ``"image"`` in caps (without ``"file"``) → pypdf text plus
   pymupdf-rendered page images at :data:`_TARGET_PIXELS` long edge,
   capped at :data:`_MAX_RENDERED_PAGES`.
3. otherwise → pypdf text only. Safe fallback.

Extraction and rendering are cached as sidecar files so repeated
questions about the same PDF don't re-compute:

- ``<filename>.txt`` — extracted text
- ``<filename>.page<N>.png`` — rendered page image
"""

from __future__ import annotations

import base64
import contextlib
import logging
from pathlib import Path

from ...core.content import (
    MODALITY_FILE,
    MODALITY_IMAGE,
    DocumentBlock,
    ImageBlock,
)

logger = logging.getLogger(__name__)

# Max pages we render when falling back from native PDF to page-image
# rendering. Bounds cost: 20 pages × ~1500px PNG ≈ 30K image tokens —
# enough for a typical uploaded doc without eating the whole context.
_MAX_RENDERED_PAGES = 20

# Long-edge target for rendered pages. 1500px matches OpenAI and
# Anthropic's "high detail" sweet spot; finer renders get downsampled
# server-side anyway.
_TARGET_PIXELS = 1500


class PdfHandler:
    """Handler for ``application/pdf``."""

    mime_types: frozenset[str] = frozenset({"application/pdf"})

    def supports_native(self) -> bool:
        return True

    async def materialize(
        self,
        path: Path,
        *,
        capabilities: frozenset[str],
        sidecar_dir: Path,
        source_uri: str,
        mime_type: str,
    ) -> DocumentBlock:
        # Path 1 — native. Provider renders + extracts server-side.
        if MODALITY_FILE in capabilities:
            try:
                data_url = _read_as_data_url(path, mime_type)
            except Exception as exc:  # pragma: no cover — defensive
                logger.warning("PDF native-load failed for %s: %s", source_uri, exc)
                return DocumentBlock(
                    source=source_uri,
                    mime_type=mime_type,
                    extracted_text=f"[PDF could not be loaded: {exc}]",
                )
            return DocumentBlock(
                source=data_url,
                mime_type=mime_type,
                send_native=True,
            )

        # Path 2/3 — text + optional page images.
        extracted: str | None = None
        try:
            extracted = _extract_pdf_text(path)
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("PDF extraction failed for %s: %s", source_uri, exc)
            extracted = f"[PDF extraction failed: {exc}]"

        page_images: tuple[ImageBlock, ...] = ()
        if MODALITY_IMAGE in capabilities:
            try:
                page_images = _render_pdf_pages(path)
            except Exception as exc:  # pragma: no cover — defensive
                logger.warning("PDF render failed for %s: %s", source_uri, exc)

        if not extracted and not page_images:
            extracted = (
                "[PDF contained no extractable text — likely a scanned "
                "document. Consider re-uploading as images.]"
            )

        return DocumentBlock(
            source=source_uri,
            mime_type=mime_type,
            extracted_text=extracted,
            page_images=page_images,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_as_data_url(path: Path, mime_type: str) -> str:
    """Load the file and encode as a base64 data URL."""
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{b64}"


def _extract_pdf_text(path: Path) -> str:
    """Extract text from a PDF with a sidecar cache.

    Cache file lives next to the PDF at ``<name>.txt`` — same directory,
    same cleanup path, no separate lifecycle to manage.
    """
    sidecar = path.with_suffix(path.suffix + ".txt")
    if sidecar.exists():
        return sidecar.read_text(encoding="utf-8")

    # pypdf is imported lazily so this module stays cheap to import
    # for callers that don't actually parse PDFs.
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages: list[str] = []
    for i, page in enumerate(reader.pages, 1):
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(f"--- Page {i} ---\n{page_text.strip()}")
    text = "\n\n".join(pages).strip()

    with contextlib.suppress(OSError):
        sidecar.write_text(text, encoding="utf-8")
    return text


def _render_pdf_pages(path: Path) -> tuple[ImageBlock, ...]:
    """Render up to :data:`_MAX_RENDERED_PAGES` pages as PNG ImageBlocks.

    Each page caches to ``<name>.page<N>.png``. Returned blocks carry
    data URLs ready for the OpenAI ``image_url`` wire format.
    """
    # pymupdf is ~20MB; import lazily.
    import pymupdf  # type: ignore[import-not-found]

    out: list[ImageBlock] = []
    with pymupdf.open(str(path)) as doc:  # type: ignore[attr-defined]
        total = min(len(doc), _MAX_RENDERED_PAGES)
        for i in range(total):
            sidecar = path.with_name(f"{path.name}.page{i + 1}.png")
            if sidecar.exists():
                png_bytes = sidecar.read_bytes()
            else:
                page = doc[i]
                rect = page.rect
                long_edge = max(rect.width, rect.height)
                zoom = _TARGET_PIXELS / long_edge if long_edge else 1.0
                matrix = pymupdf.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                png_bytes = pix.tobytes("png")
                with contextlib.suppress(OSError):
                    sidecar.write_bytes(png_bytes)

            b64 = base64.b64encode(png_bytes).decode("ascii")
            out.append(ImageBlock(
                source=f"data:image/png;base64,{b64}",
                mime_type="image/png",
                detail="high",
            ))
    return tuple(out)
