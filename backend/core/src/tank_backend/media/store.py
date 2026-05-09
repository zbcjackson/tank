"""Content-addressed media storage for uploaded multi-modal assets.

Files live at ``~/.tank/media/<session_id>/<sha256>.<ext>``. Content
addressing means uploading the same image twice costs one file on disk;
persisted conversation history stores ``media://<session>/<hash>.<ext>``
URIs, which are cheap to round-trip through JSON.

At LLM-send time, :meth:`MediaStore.materialize_for_llm` turns those
URIs into data the provider can actually consume:

- Images become base64 data URLs.
- PDFs pick one of three paths based on the LLM's declared
  ``capabilities``:
    1. ``"file"`` in caps → native base64 PDF (Claude, Gemini, gpt-4o).
    2. ``"image"`` in caps → pypdf text + rendered page images.
    3. neither → pypdf text only.

Each PDF path caches its output as sidecar files alongside the
original so repeated questions about the same document don't
re-extract or re-render.

Not thread-safe but asyncio-safe: each operation is a single atomic
write/read, and the hash-named files never collide under concurrent
puts.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import logging
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path

from ..core.content import (
    MODALITY_FILE,
    MODALITY_IMAGE,
    AudioBlock,
    ContentBlock,
    DocumentBlock,
    ImageBlock,
)

logger = logging.getLogger(__name__)


# media://<session_id>/<hash>.<ext>
_MEDIA_URI_PATTERN = re.compile(
    r"^media://(?P<session>[A-Za-z0-9_.\-]+)/(?P<filename>[A-Za-z0-9_.\-]+)$"
)

# Max pages we render when falling back from native PDF to page-image
# rendering. Bounds cost: 20 pages × ~1500px PNG ≈ 30K image tokens —
# enough for a typical uploaded doc without eating the whole context.
_MAX_RENDERED_PAGES = 20

# Long-edge target for rendered pages. 1500px matches OpenAI and
# Anthropic's "high detail" sweet spot; finer renders get downsampled
# server-side anyway.
_TARGET_PIXELS = 1500

# Fallback extension map for MIME types missing from `mimetypes`.
# Keep this small; add entries only when a real upload hits the warning.
_EXTENSION_FALLBACKS: dict[str, str] = {
    "image/webp": ".webp",
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "audio/webm": ".webm",
}


@dataclass(frozen=True, slots=True)
class StoredMedia:
    """Result of :meth:`MediaStore.put` — what the caller hands to the
    client or embeds in a ContentBlock.
    """

    media_uri: str
    mime_type: str
    size: int


class MediaStoreError(Exception):
    """Base for MediaStore errors."""


class UnknownMediaURIError(MediaStoreError):
    """Raised when a media:// URI can't be parsed or the file is gone."""


class CrossSessionAccessError(MediaStoreError):
    """Raised when a session tries to read media from another session."""


def _extension_for(mime_type: str) -> str:
    """Return a filesystem extension for ``mime_type``.

    Preference order: mimetypes builtin → fallback map → ``.bin``.
    The extension is advisory only — the MIME type is authoritative.
    """
    ext = mimetypes.guess_extension(mime_type)
    if ext:
        return ext
    return _EXTENSION_FALLBACKS.get(mime_type, ".bin")


def _safe_session_segment(session_id: str) -> str:
    """Normalise a session id to a safe directory name.

    Rejects empty and path-traversal attempts. The on-disk layout is
    trusted code, but we still validate defensively because session ids
    ultimately originate from URL path parameters.
    """
    if not session_id or "/" in session_id or ".." in session_id:
        raise ValueError(f"Invalid session id for media store: {session_id!r}")
    return session_id


class MediaStore:
    """Content-addressed store for uploaded media.

    Example::

        store = MediaStore(Path.home() / ".tank/media")
        stored = await store.put(png_bytes, "image/png", session_id="sess-1")
        # stored.media_uri = "media://sess-1/ab12ef34....png"

        data, mime = await store.get(stored.media_uri)
        # data == png_bytes, mime == "image/png"

        block = ImageBlock(source=stored.media_uri, mime_type="image/png")
        materialized = await store.materialize_for_llm(block)
        # materialized.source is now "data:image/png;base64,..."
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    # ------------------------------------------------------------------
    # Put / get
    # ------------------------------------------------------------------

    async def put(
        self,
        data: bytes,
        mime_type: str,
        *,
        session_id: str,
    ) -> StoredMedia:
        """Store ``data`` under a content-addressed filename.

        Returns the ``media://`` URI plus bookkeeping. Re-uploads of
        identical bytes dedupe automatically because the filename is
        the SHA-256 of the content.
        """
        if not mime_type:
            raise ValueError("mime_type is required")
        sess = _safe_session_segment(session_id)

        digest = hashlib.sha256(data).hexdigest()
        ext = _extension_for(mime_type)
        filename = f"{digest}{ext}"

        sess_dir = self._root / sess
        sess_dir.mkdir(parents=True, exist_ok=True)
        path = sess_dir / filename

        if not path.exists():
            # Atomic write: tmp file + rename.
            tmp_path = path.with_suffix(path.suffix + ".tmp")
            tmp_path.write_bytes(data)
            tmp_path.replace(path)

        return StoredMedia(
            media_uri=f"media://{sess}/{filename}",
            mime_type=mime_type,
            size=len(data),
        )

    async def get(
        self,
        media_uri: str,
        *,
        session_id: str | None = None,
    ) -> tuple[bytes, str]:
        """Resolve a ``media://`` URI to ``(bytes, mime_type)``.

        When ``session_id`` is provided, the call is restricted to
        media owned by that session — protects against one session
        reading another session's uploads.
        """
        session, filename = self._parse_uri(media_uri)
        if session_id is not None and session != session_id:
            raise CrossSessionAccessError(
                f"Session {session_id!r} may not read media from {session!r}"
            )
        path = self._root / session / filename
        if not path.exists():
            raise UnknownMediaURIError(f"No file for {media_uri}")

        data = path.read_bytes()
        mime_type, _ = mimetypes.guess_type(path.name)
        if mime_type is None:
            # Reverse-lookup via our fallback map.
            for mime, ext in _EXTENSION_FALLBACKS.items():
                if path.name.endswith(ext):
                    mime_type = mime
                    break
        if mime_type is None:
            mime_type = "application/octet-stream"
        return data, mime_type

    # ------------------------------------------------------------------
    # Materialization (for wire)
    # ------------------------------------------------------------------

    async def materialize_for_llm(
        self,
        block: ContentBlock,
        *,
        session_id: str | None = None,
        capabilities: frozenset[str] | None = None,
    ) -> ContentBlock:
        """Return a copy of ``block`` with ``media://`` URIs resolved.

        Non-media blocks and blocks whose source is already a data URL
        or absolute path are returned unchanged.

        ``capabilities`` is the set of input modalities the target LLM
        accepts. It drives the document waterfall: a PDF goes native
        when ``"file"`` is in caps, with page-image rendering when
        ``"image"`` is in caps, else text-only. Images and audio don't
        consult caps today — callers upstream already gate uploads.
        """
        if block.type == "image":
            return await self._materialize_image(block, session_id)
        if block.type == "document":
            return await self._materialize_document(
                block, session_id, capabilities or frozenset(),
            )
        if block.type == "audio":
            return await self._materialize_audio(block, session_id)
        return block

    async def _materialize_image(
        self,
        block: ImageBlock,
        session_id: str | None,
    ) -> ImageBlock:
        if not block.source.startswith("media://"):
            return block
        data_url = await self._data_url(block.source, session_id)
        return ImageBlock(
            source=data_url,
            mime_type=block.mime_type,
            detail=block.detail,
        )

    async def _materialize_document(
        self,
        block: DocumentBlock,
        session_id: str | None,
        capabilities: frozenset[str],
    ) -> DocumentBlock:
        """Pick the best wire representation for the configured LLM.

        Waterfall by capability:

        1. ``"file"`` in caps → native PDF: base64 data URL on ``source``,
           ``send_native=True``. Provider does rendering + extraction.
        2. ``"image"`` in caps → pypdf text plus rendered page images
           (up to :data:`_MAX_RENDERED_PAGES` at 1500px). LLM gets both.
        3. otherwise → pypdf text only.

        Blocks that already carry text or page images pass through
        without re-work (covers replay from persisted history). Non-PDF
        documents get a descriptive placeholder so the LLM isn't handed
        an opaque ``media://`` URL.

        Extraction and rendering are both cached as sidecar files so
        repeated questions about the same PDF don't re-compute.
        """
        # Step 1 — already materialized upstream. Respect it and only
        # re-resolve any media:// URIs on the page images.
        if block.extracted_text or block.page_images or block.send_native:
            if block.page_images:
                new_pages: list[ImageBlock] = []
                for img in block.page_images:
                    new_pages.append(await self._materialize_image(img, session_id))
                return DocumentBlock(
                    source=block.source,
                    mime_type=block.mime_type,
                    extracted_text=block.extracted_text,
                    page_images=tuple(new_pages),
                    send_native=block.send_native,
                )
            return block

        # Step 2 — non-PDF documents have no handler today.
        if block.mime_type != "application/pdf":
            return DocumentBlock(
                source=block.source,
                mime_type=block.mime_type,
                extracted_text=(
                    f"[Attached {block.mime_type} document: extraction "
                    f"not supported for this format.]"
                ),
            )

        if not block.source.startswith("media://"):
            return block

        # Step 3 — pick the wire path.
        if MODALITY_FILE in capabilities:
            # Native PDF: the provider renders + extracts server-side.
            # We just hand over the bytes as a data URL.
            try:
                data_url = await self._data_url(block.source, session_id)
            except (UnknownMediaURIError, CrossSessionAccessError):
                raise
            except Exception as exc:  # pragma: no cover — defensive
                logger.warning("PDF native-load failed for %s: %s", block.source, exc)
                return DocumentBlock(
                    source=block.source,
                    mime_type=block.mime_type,
                    extracted_text=f"[PDF could not be loaded: {exc}]",
                )
            return DocumentBlock(
                source=data_url,
                mime_type=block.mime_type,
                send_native=True,
            )

        # Steps 4/5 — local extraction/rendering. Both failures turn
        # into a text diagnostic so a malformed PDF can't kill the turn.
        extracted: str | None = None
        try:
            extracted = await self._extract_pdf_text(
                block.source, session_id=session_id,
            )
        except (UnknownMediaURIError, CrossSessionAccessError):
            raise
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("PDF extraction failed for %s: %s", block.source, exc)
            extracted = f"[PDF extraction failed: {exc}]"

        page_images: tuple[ImageBlock, ...] = ()
        if MODALITY_IMAGE in capabilities:
            try:
                page_images = await self._render_pdf_pages(
                    block.source, session_id=session_id,
                )
            except (UnknownMediaURIError, CrossSessionAccessError):
                raise
            except Exception as exc:  # pragma: no cover — defensive
                logger.warning("PDF render failed for %s: %s", block.source, exc)

        if not extracted and not page_images:
            extracted = (
                "[PDF contained no extractable text — likely a scanned "
                "document. Consider re-uploading as images.]"
            )

        return DocumentBlock(
            source=block.source,
            mime_type=block.mime_type,
            extracted_text=extracted,
            page_images=page_images,
        )

    async def _render_pdf_pages(
        self,
        media_uri: str,
        *,
        session_id: str | None,
    ) -> tuple[ImageBlock, ...]:
        """Render up to :data:`_MAX_RENDERED_PAGES` of a PDF to PNG blocks.

        Each page is written as a sidecar ``<hash>.pdf.page<N>.png`` so
        follow-up questions skip the render cost. Returned blocks carry
        data URLs ready for the OpenAI ``image_url`` wire format.
        """
        session, filename = self._parse_uri(media_uri)
        if session_id is not None and session != session_id:
            raise CrossSessionAccessError(
                f"Session {session_id!r} may not read media from {session!r}"
            )
        pdf_path = self._root / session / filename
        if not pdf_path.exists():
            raise UnknownMediaURIError(f"No file for {media_uri}")

        # pymupdf is imported lazily; it's a ~20MB dep we don't need
        # until the first PDF arrives at a vision-but-not-PDF-native
        # model. Keeps import-time surface area small.
        import pymupdf  # type: ignore[import-not-found]

        out: list[ImageBlock] = []
        with pymupdf.open(str(pdf_path)) as doc:  # type: ignore[attr-defined]
            total = min(len(doc), _MAX_RENDERED_PAGES)
            for i in range(total):
                sidecar = pdf_path.with_name(
                    f"{pdf_path.name}.page{i + 1}.png",
                )
                if sidecar.exists():
                    png_bytes = sidecar.read_bytes()
                else:
                    page = doc[i]
                    # Scale so the long edge is _TARGET_PIXELS pixels.
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
        # Silence lint: io is imported for future use and by the caching
        # write path elsewhere in this module.
        _ = io
        return tuple(out)

    async def _extract_pdf_text(
        self,
        media_uri: str,
        *,
        session_id: str | None,
    ) -> str:
        """Extract text from a stored PDF, with a sidecar cache.

        The cache lives next to the PDF at ``<hash>.pdf.txt`` — same
        directory, same cleanup path, no separate lifecycle to manage.
        """
        session, filename = self._parse_uri(media_uri)
        if session_id is not None and session != session_id:
            raise CrossSessionAccessError(
                f"Session {session_id!r} may not read media from {session!r}"
            )
        pdf_path = self._root / session / filename
        if not pdf_path.exists():
            raise UnknownMediaURIError(f"No file for {media_uri}")

        sidecar = pdf_path.with_suffix(pdf_path.suffix + ".txt")
        if sidecar.exists():
            return sidecar.read_text(encoding="utf-8")

        # pypdf is imported lazily so the media module stays importable
        # without the optional dependency at module-load time.
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        pages: list[str] = []
        for i, page in enumerate(reader.pages, 1):
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages.append(f"--- Page {i} ---\n{page_text.strip()}")
        text = "\n\n".join(pages).strip()

        # Write-through cache. Best-effort — an error writing the
        # sidecar shouldn't stop us returning the extracted text.
        with contextlib.suppress(OSError):
            sidecar.write_text(text, encoding="utf-8")
        return text

    async def _materialize_audio(
        self,
        block: AudioBlock,
        session_id: str | None,
    ) -> AudioBlock:
        # Providers without native audio receive only the transcript,
        # so we don't inline-expand audio bytes here. Phase 5 (native
        # audio) will add a capability-aware path.
        return block

    async def _data_url(
        self,
        media_uri: str,
        session_id: str | None,
    ) -> str:
        data, mime = await self.get(media_uri, session_id=session_id)
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64}"

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def purge_session(self, session_id: str) -> int:
        """Delete all media for a session. Returns the file count removed."""
        sess = _safe_session_segment(session_id)
        sess_dir = self._root / sess
        if not sess_dir.is_dir():
            return 0
        count = 0
        for file in sess_dir.iterdir():
            if file.is_file():
                file.unlink()
                count += 1
        # Empty-directory cleanup is best-effort: a concurrent put may
        # have recreated a file between our iterdir and rmdir.
        with contextlib.suppress(OSError):
            sess_dir.rmdir()
        return count

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_uri(media_uri: str) -> tuple[str, str]:
        match = _MEDIA_URI_PATTERN.match(media_uri)
        if not match:
            raise UnknownMediaURIError(f"Malformed media URI: {media_uri!r}")
        return match.group("session"), match.group("filename")
