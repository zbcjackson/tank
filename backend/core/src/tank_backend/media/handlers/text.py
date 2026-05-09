"""Text handler — plain-text uploads (``txt``, ``md``, ``csv``, code).

Every text file goes to the LLM as an ``extracted_text`` field on a
:class:`DocumentBlock`, wrapped in a light Markdown fence when a
sensible language hint is available. That gives the model a clear
"this is user-uploaded content" signal separate from the prose in the
surrounding conversation.

Design choices:

- **UTF-8 first, latin-1 fallback.** Nearly all modern text is UTF-8;
  the fallback catches pasted Windows-encoded files (CSVs especially)
  without guessing — latin-1 is the only one-byte encoding that
  decodes any byte sequence without raising.
- **Size-bounded** at :data:`_MAX_CHARS` so a giant log file can't
  eat the context window. Truncation marker tells the LLM there's
  more.
- **Sidecar caching** at ``<name>.txt`` like the other handlers, so
  repeated questions about the same file don't re-read + re-wrap.
  Yes, even for already-text files — the sidecar holds the *wrapped*
  form with fence + size marker, not just the raw bytes.

What this handler DOESN'T do: CSV-to-Markdown-table, HTML-to-text,
syntax-aware code chunking. Those are nice-to-have enhancements that
would layer on cleanly — the LLM handles raw versions of all three
well enough today.
"""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path

from ...core.content import DocumentBlock
from .base import DocumentHandler

logger = logging.getLogger(__name__)


# Supported text MIME types. Unknown ``text/*`` MIMEs still route here
# at the modality layer, but the handler accepts them too (the class
# method check is looser than the registry lookup for safety).
TEXT_MIME_TYPES: frozenset[str] = frozenset({
    "text/plain",
    "text/markdown",
    "text/csv",
    "text/tab-separated-values",
    "text/html",
    "text/xml",
    "application/xml",
    "application/json",
    "text/x-python",
    "text/x-java",
    "text/x-c",
    "text/x-c++",
    "text/x-go",
    "text/x-rust",
    "text/javascript",
    "text/typescript",
    "text/x-shellscript",
    "text/yaml",
    "application/x-yaml",
    "application/toml",
})

# Hard cap on the text we hand to the LLM. Same budget as Office
# extraction — roughly 20K tokens at 4 chars/token.
_MAX_CHARS = 80_000

# MIME → fenced-code-block language hint. Missing entries get no
# fence; the LLM still reads plain text fine, but the hint is cheap
# to include and helps code-aware formatting downstream.
_LANGUAGE_HINTS: dict[str, str] = {
    "text/markdown": "markdown",
    "text/csv": "csv",
    "text/tab-separated-values": "tsv",
    "text/html": "html",
    "text/xml": "xml",
    "application/xml": "xml",
    "application/json": "json",
    "text/x-python": "python",
    "text/x-java": "java",
    "text/x-c": "c",
    "text/x-c++": "cpp",
    "text/x-go": "go",
    "text/x-rust": "rust",
    "text/javascript": "javascript",
    "text/typescript": "typescript",
    "text/x-shellscript": "bash",
    "text/yaml": "yaml",
    "application/x-yaml": "yaml",
    "application/toml": "toml",
}


class TextHandler(DocumentHandler):
    """Handler for plain-text uploads (and close cousins)."""

    mime_types: frozenset[str] = TEXT_MIME_TYPES

    def supports_native(self) -> bool:
        # No provider has a native "text file" part type — everything
        # goes inline as ``extracted_text``.
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
        # capabilities is unused today — text always goes inline.
        del capabilities, sidecar_dir

        text = _read_text_cached(path, mime_type)
        return DocumentBlock(
            source=source_uri,
            mime_type=mime_type,
            extracted_text=text or "[File was empty.]",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_text_cached(path: Path, mime_type: str) -> str:
    """Read ``path`` as text, wrap for the LLM, cache the result.

    Cache file at ``<name>.txt`` in the same directory. The cache
    stores the wrapped form (with fence + truncation marker) so a
    cache hit needs no post-processing.
    """
    sidecar = path.with_suffix(path.suffix + ".txt")
    if sidecar.exists():
        return sidecar.read_text(encoding="utf-8")

    raw = _read_bytes_as_text(path)
    wrapped = _wrap(raw, mime_type, path.name)

    with contextlib.suppress(OSError):
        sidecar.write_text(wrapped, encoding="utf-8")
    return wrapped


def _read_bytes_as_text(path: Path) -> str:
    """Decode a file as UTF-8, falling back to latin-1.

    latin-1 is the safe fallback because every byte is a valid code
    point — it never raises, so a file with mixed or unknown encoding
    still comes through, possibly with mojibake but never as an
    exception. The alternative (binary mode + ``ignore`` errors) loses
    bytes silently, which is worse.
    """
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        logger.info(
            "Text file %s is not UTF-8; decoding as latin-1", path.name,
        )
        return data.decode("latin-1")


def _wrap(raw: str, mime_type: str, filename: str) -> str:
    """Bound size + wrap in a fenced code block for the LLM.

    The fence carries a language hint when we have one. ``filename``
    is embedded in a leading line so the model knows which file it's
    looking at when multiple are attached in one turn.
    """
    if len(raw) > _MAX_CHARS:
        raw = (
            raw[:_MAX_CHARS]
            + f"\n\n[... truncated after {_MAX_CHARS} characters; "
            "upload a narrower selection to see the rest.]"
        )

    language = _LANGUAGE_HINTS.get(mime_type, "")
    # Header line identifies the file — helps when several attachments
    # arrive together. Markdown code fence lets the model skim the
    # structure without us pre-parsing it.
    return f"File: {filename}\n```{language}\n{raw}\n```"
