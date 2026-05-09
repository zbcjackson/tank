"""Document handlers for the multi-modal media pipeline.

Each handler covers one format family (PDF, Office, …) and implements
:class:`DocumentHandler`. The :data:`default_registry` is the
authoritative mapping the :class:`MediaStore` consults at materialize
time.

Adding a new format is:

1. Implement the :class:`DocumentHandler` protocol in a new module.
2. Append it to :data:`_DEFAULTS` below.

No changes required to :mod:`tank_backend.media.store` — that's the
whole point of this seam.
"""

from __future__ import annotations

from .base import DocumentHandler, DocumentHandlerRegistry
from .office import OfficeHandler
from .pdf import PdfHandler

# Instantiated once at import. Tests that need to swap handlers build
# their own :class:`DocumentHandlerRegistry`.
_DEFAULTS: tuple[DocumentHandler, ...] = (
    PdfHandler(),
    OfficeHandler(),
)


def _build_default_registry() -> DocumentHandlerRegistry:
    reg = DocumentHandlerRegistry()
    for handler in _DEFAULTS:
        reg.register(handler)
    return reg


default_registry: DocumentHandlerRegistry = _build_default_registry()


__all__ = [
    "DocumentHandler",
    "DocumentHandlerRegistry",
    "OfficeHandler",
    "PdfHandler",
    "default_registry",
]
