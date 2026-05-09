"""Document handler strategy + registry.

Each supported document format (PDF, DOCX, XLSX, PPTX, …) is owned by
one :class:`DocumentHandler` implementation. The :class:`MediaStore`
is a thin dispatcher: it finds the handler for the block's MIME type
and delegates materialization. Adding a new format is "implement
the protocol and register it" — no store.py changes, no touching the
capability waterfall.

The protocol is intentionally narrow. Every handler sees:

- the absolute ``path`` to the stored file,
- the LLM's ``capabilities`` (so the handler can pick the best wire
  path it supports — native file vs images vs text),
- a ``sidecar_dir`` for caching extraction output,
- the ``source_uri`` it should embed on the resulting
  :class:`DocumentBlock` (so persisted history keeps the media:// URI
  rather than a data URL that can't be replayed).

What the handler DOESN'T see: the :class:`MediaStore`, session ids,
or anything about the on-disk layout. That keeps handlers pure and
unit-testable without pretending to own storage concerns.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from ...core.content import DocumentBlock


@runtime_checkable
class DocumentHandler(Protocol):
    """Strategy for materializing one family of document formats.

    The handler declares the MIME types it covers via :attr:`mime_types`
    and implements :meth:`materialize`. Implementations must never
    raise for content-level problems (corrupt files, empty documents);
    surface those as a :class:`DocumentBlock` with a diagnostic
    ``extracted_text``. They may raise for storage-level problems
    (missing file, I/O error) — those bubble up to the caller.
    """

    #: MIME types this handler accepts. Registered under each value.
    mime_types: frozenset[str]

    def supports_native(self) -> bool:
        """Can this handler produce a native-file block?

        Used by the registry/UX to surface "this model supports the
        file natively" versus "we'll extract text from it for you".
        Informational only today; the waterfall inside
        :meth:`materialize` still makes the real decision.
        """
        ...

    async def materialize(
        self,
        path: Path,
        *,
        capabilities: frozenset[str],
        sidecar_dir: Path,
        source_uri: str,
        mime_type: str,
    ) -> DocumentBlock:
        """Return the DocumentBlock to hand to the LLM.

        Implementations should:

        - Pick the richest wire form the LLM's ``capabilities`` allow.
        - Cache intermediate artifacts (extracted text, rendered
          images, …) in ``sidecar_dir`` so repeat questions don't
          re-compute.
        - Embed ``source_uri`` on the returned block's ``source``
          unless the block is meant to travel natively as a data URL.
        """
        ...


class DocumentHandlerRegistry:
    """MIME → handler lookup.

    Built at module import in :mod:`tank_backend.media.handlers`. Tests
    may create ephemeral registries to swap in stub handlers without
    touching the default one.
    """

    def __init__(self) -> None:
        self._by_mime: dict[str, DocumentHandler] = {}

    def register(self, handler: DocumentHandler) -> None:
        """Register ``handler`` for every MIME in its ``mime_types``.

        Later registrations for the same MIME replace earlier ones —
        callers can override the default handler for a format by
        registering after module load.
        """
        for mime in handler.mime_types:
            self._by_mime[mime] = handler

    def lookup(self, mime_type: str) -> DocumentHandler | None:
        return self._by_mime.get(mime_type)

    def mime_types(self) -> frozenset[str]:
        return frozenset(self._by_mime)
