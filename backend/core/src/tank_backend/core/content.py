"""Multi-modal content block types.

Tank-native representation of message content that can hold text alongside
images, documents, and audio. Sits between tools, the LLM transport, and
persistence: tools produce blocks, persistence stores them as plain JSON,
``llm.py`` adapts them to the provider wire format at send time.

The `source` field is a URI-ish string:
- ``media://<session>/<hash>.<ext>`` — reference to MediaStore (phase 2+)
- ``data:<mime>;base64,<payload>`` — inline data URL
- Absolute filesystem path — when the block was produced by a local tool

``mime_type`` is authoritative; ``source`` extension is advisory only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class TextBlock:
    """Plain text content."""

    text: str
    type: Literal["text"] = "text"


@dataclass(frozen=True, slots=True)
class ImageBlock:
    """An image reachable via ``source``.

    ``detail`` follows the OpenAI vision convention (``low`` / ``high`` /
    ``auto``). Providers that don't use this field ignore it.
    """

    source: str
    mime_type: str
    detail: Literal["low", "high", "auto"] = "auto"
    type: Literal["image"] = "image"


@dataclass(frozen=True, slots=True)
class DocumentBlock:
    """A document (PDF, DOCX, etc.).

    When the document has extractable text, ``extracted_text`` is populated
    so providers that can't take the raw file still get useful input.
    When the document is primarily visual (scanned PDF), ``page_images``
    carries rendered pages as images.
    """

    source: str
    mime_type: str
    extracted_text: str | None = None
    page_images: tuple[ImageBlock, ...] = ()
    type: Literal["document"] = "document"


@dataclass(frozen=True, slots=True)
class AudioBlock:
    """An audio clip reachable via ``source``.

    ``transcript`` is populated when ASR has already run on the clip.
    Providers with native audio input consume ``source`` directly;
    providers without it fall back to ``transcript``.
    """

    source: str
    mime_type: str
    transcript: str | None = None
    type: Literal["audio"] = "audio"


ContentBlock = TextBlock | ImageBlock | DocumentBlock | AudioBlock
ContentBlocks = list[ContentBlock]


# ---------------------------------------------------------------------------
# Modality classification
# ---------------------------------------------------------------------------

# Canonical modality names. The CapabilityRegistry uses the same vocabulary.
MODALITY_TEXT = "text"
MODALITY_IMAGE = "image"
MODALITY_FILE = "file"
MODALITY_AUDIO = "audio"
MODALITY_VIDEO = "video"


def block_modality(block: ContentBlock) -> str:
    """Return the modality name required to send this block to an LLM."""
    if block.type == "text":
        return MODALITY_TEXT
    if block.type == "image":
        return MODALITY_IMAGE
    if block.type == "document":
        return MODALITY_FILE
    if block.type == "audio":
        return MODALITY_AUDIO
    # exhaustive over the union; unreachable under type-checking
    raise ValueError(f"Unknown block type: {block!r}")


def modality_for_mime(mime_type: str) -> str | None:
    """Return the modality name for a MIME type, or ``None`` if unknown.

    The canonical classification is by MIME top-level type:
    ``image/*`` → image, ``audio/*`` → audio, ``video/*`` → video.
    Specific application types (PDF, common office docs) are routed to
    ``file``. Everything else is unknown to us at the ingestion boundary
    — the upload endpoint rejects them by returning HTTP 415.
    """
    if not mime_type:
        return None
    lower = mime_type.lower().split(";", 1)[0].strip()
    if lower.startswith("image/"):
        return MODALITY_IMAGE
    if lower.startswith("audio/"):
        return MODALITY_AUDIO
    if lower.startswith("video/"):
        return MODALITY_VIDEO
    if lower.startswith("text/"):
        return MODALITY_TEXT
    if lower in _DOCUMENT_MIME_TYPES:
        return MODALITY_FILE
    return None


# MIME types treated as documents. Kept narrow on purpose: only
# whitelist formats we can actually do something useful with.
_DOCUMENT_MIME_TYPES: frozenset[str] = frozenset({
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
})


def blocks_modalities(blocks: ContentBlocks) -> frozenset[str]:
    """Return the set of modalities present in a block list."""
    return frozenset(block_modality(b) for b in blocks)


# ---------------------------------------------------------------------------
# Serialization (for persistence + wire)
# ---------------------------------------------------------------------------


def block_to_dict(block: ContentBlock) -> dict:
    """Serialize a block to a plain dict (JSON-safe).

    Persistence can round-trip this via :func:`block_from_dict`.
    """
    if block.type == "text":
        return {"type": "text", "text": block.text}
    if block.type == "image":
        return {
            "type": "image",
            "source": block.source,
            "mime_type": block.mime_type,
            "detail": block.detail,
        }
    if block.type == "document":
        return {
            "type": "document",
            "source": block.source,
            "mime_type": block.mime_type,
            "extracted_text": block.extracted_text,
            "page_images": [block_to_dict(img) for img in block.page_images],
        }
    if block.type == "audio":
        return {
            "type": "audio",
            "source": block.source,
            "mime_type": block.mime_type,
            "transcript": block.transcript,
        }
    raise ValueError(f"Unknown block type: {block!r}")


def block_from_dict(data: dict) -> ContentBlock:
    """Inverse of :func:`block_to_dict`. Raises ValueError on unknown types."""
    kind = data.get("type")
    if kind == "text":
        return TextBlock(text=data["text"])
    if kind == "image":
        return ImageBlock(
            source=data["source"],
            mime_type=data["mime_type"],
            detail=data.get("detail", "auto"),
        )
    if kind == "document":
        raw_pages = data.get("page_images") or []
        pages: tuple[ImageBlock, ...] = tuple(
            ImageBlock(
                source=p["source"],
                mime_type=p["mime_type"],
                detail=p.get("detail", "auto"),
            )
            for p in raw_pages
        )
        return DocumentBlock(
            source=data["source"],
            mime_type=data["mime_type"],
            extracted_text=data.get("extracted_text"),
            page_images=pages,
        )
    if kind == "audio":
        return AudioBlock(
            source=data["source"],
            mime_type=data["mime_type"],
            transcript=data.get("transcript"),
        )
    raise ValueError(f"Unknown content block type: {kind!r}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def normalize_content(
    content: str | ContentBlocks,
) -> ContentBlocks:
    """Coerce a tool return value to a block list.

    ``str`` wraps to a single ``TextBlock``. An existing block list is
    returned as-is (defensive copy).
    """
    if isinstance(content, str):
        return [TextBlock(text=content)]
    return list(content)


def blocks_to_text(blocks: ContentBlocks) -> str:
    """Flatten a block list to a plain-text summary.

    Used when the receiving surface cannot represent non-text blocks
    (e.g. OpenAI's ``tool`` role, legacy persistence readers, or a
    capability-downgrade path). Non-text blocks collapse to a short
    description so the LLM still knows something was returned.
    """
    parts: list[str] = []
    for b in blocks:
        if b.type == "text":
            parts.append(b.text)
        elif b.type == "image":
            parts.append(f"[image: {b.mime_type} @ {b.source}]")
        elif b.type == "document":
            if b.extracted_text:
                parts.append(b.extracted_text)
            else:
                parts.append(f"[document: {b.mime_type} @ {b.source}]")
        elif b.type == "audio":
            if b.transcript:
                parts.append(b.transcript)
            else:
                parts.append(f"[audio: {b.mime_type} @ {b.source}]")
    return "\n".join(parts)


def blocks_to_openai_parts(blocks: ContentBlocks) -> list[dict]:
    """Convert a block list to OpenAI ``content`` parts.

    Text blocks collapse into ``{"type": "text", "text": ...}``. Images
    render as ``{"type": "image_url", "image_url": {"url", "detail"}}``.
    Documents with extracted text emit a text part; their page images
    emit image parts. Audio without native wire support falls back to
    its transcript as text.

    Consecutive text blocks are merged into a single text part so the
    LLM sees one contiguous prefix rather than fragmented snippets.
    """
    parts: list[dict] = []
    pending_text: list[str] = []

    def _flush() -> None:
        if not pending_text:
            return
        parts.append({"type": "text", "text": "\n".join(pending_text)})
        pending_text.clear()

    for block in blocks:
        if block.type == "text":
            if block.text:
                pending_text.append(block.text)
        elif block.type == "image":
            _flush()
            parts.append({
                "type": "image_url",
                "image_url": {"url": block.source, "detail": block.detail},
            })
        elif block.type == "document":
            if block.extracted_text:
                pending_text.append(block.extracted_text)
            for img in block.page_images:
                _flush()
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": img.source, "detail": img.detail},
                })
            if not block.extracted_text and not block.page_images:
                pending_text.append(
                    f"[document: {block.mime_type} @ {block.source}]"
                )
        elif block.type == "audio":
            if block.transcript:
                pending_text.append(block.transcript)
            else:
                pending_text.append(
                    f"[audio: {block.mime_type} @ {block.source}]"
                )

    _flush()
    return parts


# Explicit public surface — keep imports stable across phases.
__all__ = [
    "MODALITY_AUDIO",
    "MODALITY_FILE",
    "MODALITY_IMAGE",
    "MODALITY_TEXT",
    "MODALITY_VIDEO",
    "AudioBlock",
    "ContentBlock",
    "ContentBlocks",
    "DocumentBlock",
    "ImageBlock",
    "TextBlock",
    "block_from_dict",
    "block_modality",
    "block_to_dict",
    "blocks_modalities",
    "blocks_to_openai_parts",
    "blocks_to_text",
    "modality_for_mime",
    "normalize_content",
]
