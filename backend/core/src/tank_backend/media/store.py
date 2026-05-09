"""Content-addressed media storage for uploaded multi-modal assets.

Files live at ``~/.tank/media/<session_id>/<sha256>.<ext>``. Content
addressing means uploading the same image twice costs one file on disk;
persisted conversation history stores ``media://<session>/<hash>.<ext>``
URIs, which are cheap to round-trip through JSON.

At LLM-send time, :meth:`MediaStore.materialize_for_llm` turns those
URIs into data the provider can actually consume:

- Images become base64 data URLs.
- Documents dispatch to a :class:`DocumentHandler` keyed by MIME type.
  The handler owns the format-specific strategy (native vs image vs
  text) — this module is intentionally ignorant of PDF, DOCX, or any
  other format's internals.

Adding support for a new document type is "implement a handler and
register it" — no changes here. See
:mod:`tank_backend.media.handlers` for the default registry.

Not thread-safe but asyncio-safe: each operation is a single atomic
write/read, and the hash-named files never collide under concurrent
puts.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import logging
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path

from ..core.content import (
    AudioBlock,
    ContentBlock,
    DocumentBlock,
    ImageBlock,
)
from .handlers import DocumentHandlerRegistry, default_registry

logger = logging.getLogger(__name__)


# media://<session_id>/<hash>.<ext>
_MEDIA_URI_PATTERN = re.compile(
    r"^media://(?P<session>[A-Za-z0-9_.\-]+)/(?P<filename>[A-Za-z0-9_.\-]+)$"
)

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

    def __init__(
        self,
        root: Path,
        *,
        handlers: DocumentHandlerRegistry | None = None,
    ) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        # Injectable registry so tests can register stub handlers without
        # mutating the process-wide default. Falls back to the default
        # registry wired at import in ``.handlers``.
        self._handlers = handlers or default_registry

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
        """Dispatch to the registered :class:`DocumentHandler` for the MIME.

        Blocks that already carry text, page images, or a native-file
        marker pass through — they came from persisted history or an
        upstream producer that already did the work. Unknown MIMEs
        (no registered handler) get a descriptive placeholder so the
        LLM isn't handed an opaque ``media://`` URL it can't open.

        The handler does all the format-specific work; this method
        only owns dispatch + the "already materialized" shortcut.
        """
        # Shortcut 1 — already materialized upstream. Respect it and
        # only re-resolve any media:// URIs on the page images.
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

        handler = self._handlers.lookup(block.mime_type)
        if handler is None:
            return DocumentBlock(
                source=block.source,
                mime_type=block.mime_type,
                extracted_text=(
                    f"[Attached {block.mime_type} document: extraction "
                    f"not supported for this format.]"
                ),
            )

        if not block.source.startswith("media://"):
            # Handlers work on files; without a media:// URI we can't
            # resolve the bytes. This path covers data-URL or
            # absolute-path sources from tool outputs — leave as-is.
            return block

        # Resolve the media URI to a filesystem path. Session scoping
        # lives here (one place), so handlers stay storage-agnostic.
        session, filename = self._parse_uri(block.source)
        if session_id is not None and session != session_id:
            raise CrossSessionAccessError(
                f"Session {session_id!r} may not read media from {session!r}"
            )
        path = self._root / session / filename
        if not path.exists():
            raise UnknownMediaURIError(f"No file for {block.source}")

        return await handler.materialize(
            path,
            capabilities=capabilities,
            sidecar_dir=path.parent,
            source_uri=block.source,
            mime_type=block.mime_type,
        )

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
