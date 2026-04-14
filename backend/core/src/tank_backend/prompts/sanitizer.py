"""ContentSanitizer — security scanning for loaded prompt files."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

MAX_CONTENT_BYTES = 20 * 1024  # 20 KB per file

# YAML frontmatter: ---\n...\n---\n
_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)

# HTML comments: <!-- ... -->
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# Invisible Unicode characters that could hide injections
_INVISIBLE_CHARS: frozenset[str] = frozenset(
    {
        "\u200b",  # zero-width space
        "\u200c",  # zero-width non-joiner
        "\u200d",  # zero-width joiner
        "\u200e",  # left-to-right mark
        "\u200f",  # right-to-left mark
        "\u202a",  # left-to-right embedding
        "\u202b",  # right-to-left embedding
        "\u202c",  # pop directional formatting
        "\u202d",  # left-to-right override
        "\u202e",  # right-to-left override
        "\u2060",  # word joiner
        "\u2061",  # function application
        "\u2062",  # invisible times
        "\u2063",  # invisible separator
        "\u2064",  # invisible plus
        "\ufeff",  # BOM / zero-width no-break space
        "\ufff9",  # interlinear annotation anchor
        "\ufffa",  # interlinear annotation separator
        "\ufffb",  # interlinear annotation terminator
    }
)

# Prompt injection patterns (heuristic — warn, don't block)
_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:a|an)\s+", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\|(?:im_start|im_end|system|endoftext)\|>", re.IGNORECASE),
    re.compile(r"\[INST\]", re.IGNORECASE),
    re.compile(r"disregard\s+(all|previous|above)", re.IGNORECASE),
)


def sanitize(content: str, source_path: str = "<unknown>") -> str:
    """Sanitize loaded prompt content.

    Steps (in order):
    1. Truncate to ``MAX_CONTENT_BYTES``
    2. Strip YAML frontmatter
    3. Strip HTML comments
    4. Remove invisible Unicode characters
    5. Detect prompt injection patterns (warn only — content is NOT removed)

    Returns the sanitized string.
    """
    # 1. Truncate
    if len(content.encode("utf-8")) > MAX_CONTENT_BYTES:
        content = content[:MAX_CONTENT_BYTES]
        logger.warning(
            "Prompt file %s truncated to %d bytes",
            source_path,
            MAX_CONTENT_BYTES,
        )

    # 2. Strip YAML frontmatter
    content = _FRONTMATTER_RE.sub("", content)

    # 3. Strip HTML comments
    content = _HTML_COMMENT_RE.sub("", content)

    # 4. Remove invisible Unicode
    invisible_found: set[str] = set()
    cleaned: list[str] = []
    for ch in content:
        if ch in _INVISIBLE_CHARS:
            invisible_found.add(repr(ch))
        else:
            cleaned.append(ch)
    if invisible_found:
        logger.warning(
            "Removed invisible Unicode from %s: %s",
            source_path,
            ", ".join(sorted(invisible_found)),
        )
    content = "".join(cleaned)

    # 5. Detect injection patterns (warn, don't remove)
    for pattern in _INJECTION_PATTERNS:
        match = pattern.search(content)
        if match:
            logger.warning(
                "Possible prompt injection in %s: %r",
                source_path,
                match.group()[:80],
            )

    return content.strip()
