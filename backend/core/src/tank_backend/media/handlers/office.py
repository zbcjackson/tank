"""Office handler — DOCX, XLSX, PPTX text extraction.

Wraps the format-specific extractors in :mod:`tank_backend.media.office`
behind the :class:`DocumentHandler` protocol. Owns the sidecar-cache
policy that used to live on the store.

Office formats are text-only at the wire layer today — no provider
takes a raw ``.docx`` as a native ``file`` part. A vision-model path
(DOCX → PDF → pages) is intentionally deferred: it needs LibreOffice
(~300MB binary) or Word COM (Mac/Windows only), and the text-only
path covers most of the real value.
"""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path

from ...core.content import DocumentBlock
from ..office import OFFICE_MIME_TYPES, extract_office_document
from .base import DocumentHandler

logger = logging.getLogger(__name__)


class OfficeHandler(DocumentHandler):
    """Handler for DOCX / XLSX / PPTX."""

    mime_types: frozenset[str] = OFFICE_MIME_TYPES

    def supports_native(self) -> bool:
        # No mainstream provider accepts raw Office files today.
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
        # ``capabilities`` is currently ignored — Office goes text-only
        # regardless of what the model accepts. Kept in the signature
        # so the protocol is uniform and a future LibreOffice-backed
        # page-render path can gate on ``image`` without a breaking
        # API change.
        del capabilities

        text = _extract_office_cached(path, mime_type)
        return DocumentBlock(
            source=source_uri,
            mime_type=mime_type,
            extracted_text=text or (
                "[Document contained no extractable text.]"
            ),
        )


def _extract_office_cached(path: Path, mime_type: str) -> str:
    """Dispatch to the right extractor with a sidecar text cache.

    Cache file at ``<name>.txt`` in the same directory as the source.
    Extraction failures surface as a diagnostic string, not an
    exception — a corrupt DOCX shouldn't kill the turn.
    """
    sidecar = path.with_suffix(path.suffix + ".txt")
    if sidecar.exists():
        return sidecar.read_text(encoding="utf-8")

    try:
        result = extract_office_document(path, mime_type)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("Office extraction failed (%s): %s", mime_type, exc)
        return f"[Office extraction failed: {exc}]"
    text = result or ""

    # Write-through cache; best-effort.
    with contextlib.suppress(OSError):
        sidecar.write_text(text, encoding="utf-8")
    return text
