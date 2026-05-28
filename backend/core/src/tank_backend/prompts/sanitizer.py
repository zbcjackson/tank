"""ContentSanitizer — security scanning for loaded prompt content.

Two distinct mechanisms protect against prompt injection:

* **Pattern scanning** (this module). A regex list catches known injection
  phrasings (``ignore previous instructions``, jailbreak prompts, exfil
  curls, etc.) plus invisible Unicode sneaks. ``sanitize`` runs the patterns
  and either logs a warning (default) or hard-blocks the content.
* **Untrusted-content fencing** (``_fence_untrusted`` in ``tools/web_fetch``).
  External content fetched at runtime is wrapped in
  ``<untrusted-data source="...">`` so the LLM treats it as data, not
  instructions.

Use :func:`sanitize` with ``block=True`` for content that comes from
user-editable surfaces (USER.md, AGENTS.md under ``~/.tank/``, the
per-user ``preferences.md`` file).  Use ``block=False`` for shipped
defaults — the warning log helps debug a misbehaving template without
hard-failing the assistant.

For programmatic threat enumeration (auditing, UI surfacing) call
:func:`scan_for_injection` directly; it never mutates content.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MAX_CONTENT_BYTES = 20 * 1024  # 20 KB per file

# YAML frontmatter: ---\n...\n---\n
_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)

# HTML comments: <!-- ... -->
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _tag_chars() -> frozenset[str]:
    """U+E0000–U+E007F — invisible Tag block used for ASCII smuggling."""
    return frozenset(chr(c) for c in range(0xE0000, 0xE0080))


# Invisible Unicode characters that could hide injections.
_INVISIBLE_CHARS: frozenset[str] = frozenset({
    "​",  # zero-width space
    "‌",  # zero-width non-joiner
    "‍",  # zero-width joiner
    "‎",  # left-to-right mark
    "‏",  # right-to-left mark
    "‪",  # left-to-right embedding
    "‫",  # right-to-left embedding
    "‬",  # pop directional formatting
    "‭",  # left-to-right override
    "‮",  # right-to-left override
    "⁠",  # word joiner
    "⁡",  # function application
    "⁢",  # invisible times
    "⁣",  # invisible separator
    "⁤",  # invisible plus
    "﻿",  # BOM / zero-width no-break space
    "￹",  # interlinear annotation anchor
    "￺",  # interlinear annotation separator
    "￻",  # interlinear annotation terminator
}) | _tag_chars()


# Named injection patterns.  Each entry is (name, compiled_regex).
# When adding a new pattern, prefer narrow matches — false positives on
# a hand-written user file are worse than a missed obscure variant.
_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ignore_instructions",
        re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.IGNORECASE),
    ),
    (
        "role_hijack",
        re.compile(r"you\s+are\s+now\s+(?:a|an)\s+", re.IGNORECASE),
    ),
    (
        "system_role_marker",
        re.compile(r"(?:^|\n)\s*system\s*:\s*", re.IGNORECASE),
    ),
    (
        "chatml_tokens",
        re.compile(r"<\|(?:im_start|im_end|system|endoftext)\|>", re.IGNORECASE),
    ),
    (
        "inst_tag",
        re.compile(r"\[INST\]", re.IGNORECASE),
    ),
    (
        "disregard",
        re.compile(r"disregard\s+(?:all|previous|above)", re.IGNORECASE),
    ),
    # New categories below.
    (
        "deception",
        re.compile(
            r"\bpretend\s+(?:to\s+be|you\s+are)|\bact\s+as\s+(?:a|an|the)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "restriction_bypass",
        re.compile(
            r"\b(?:jailbreak|developer\s+mode|DAN\s+mode|unlock(?:ed)?\s+mode)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "exfiltration",
        re.compile(
            r"reveal\s+(?:your|the)\s+system\s+prompt"
            r"|print\s+(?:your|the)\s+(?:prompt|instructions)"
            r"|what\s+(?:are|were)\s+your\s+(?:original\s+)?instructions",
            re.IGNORECASE,
        ),
    ),
    (
        "translate_execute",
        re.compile(
            r"translate[^.\n]{0,80}\band\s+(?:execute|run|eval)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "fake_role_markers",
        re.compile(
            r"(?:^|\n)\s*(?:assistant|user|tool)\s*:\s*",
            re.IGNORECASE,
        ),
    ),
    (
        "exfil_curl",
        re.compile(
            r"curl\s[^\n]*\$\{?\w*(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)",
            re.IGNORECASE,
        ),
    ),
    (
        "secret_file_read",
        re.compile(
            r"\bcat\s+[^\n]*(?:\.env|\.netrc|\.pgpass|credentials)\b",
            re.IGNORECASE,
        ),
    ),
)


@dataclass(frozen=True)
class Threat:
    """One detected injection pattern occurrence."""

    pattern_name: str
    matched_text: str  # truncated to 80 chars
    line_number: int   # 1-indexed; 0 when unknown


def scan_for_injection(text: str, source: str = "<unknown>") -> list[Threat]:
    """Return every injection pattern that matches ``text``.

    Pure scan — does not mutate, does not log.  Each :class:`Threat`
    carries the offending pattern name plus the matched substring (truncated
    to 80 chars) and a 1-indexed line number.

    ``source`` is accepted for API symmetry with :func:`sanitize` but is
    not used by the scan itself — callers should include it in their own
    log lines / blocked-content placeholders.
    """
    del source  # kept for API symmetry; callers log it themselves.
    threats: list[Threat] = []
    for name, pattern in _INJECTION_PATTERNS:
        for match in pattern.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            threats.append(Threat(
                pattern_name=name,
                matched_text=match.group()[:80],
                line_number=line_number,
            ))
    return threats


def sanitize(
    content: str,
    source_path: str = "<unknown>",
    *,
    block: bool = False,
) -> str:
    """Sanitize loaded prompt content.

    Steps (in order):
        1. Truncate to ``MAX_CONTENT_BYTES``
        2. Strip YAML frontmatter
        3. Strip HTML comments
        4. Remove invisible Unicode characters
        5. Detect prompt injection patterns

    When ``block=True`` and any injection pattern matches, the entire
    content is replaced with ``[BLOCKED: injection detected in
    {source_path} ({pattern_name})]``.  This is the right setting for
    user-editable surfaces (USER.md, AGENTS.md under ``~/.tank/``,
    preferences.md, future DB-backed instruction rows).

    When ``block=False`` (default) the matches are logged as warnings but
    the content is returned unchanged — appropriate for shipped defaults
    where a misfire shouldn't break the assistant.
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

    # 5. Detect injection patterns
    threats = scan_for_injection(content, source_path)
    if threats:
        first = threats[0]
        if block:
            logger.warning(
                "BLOCKED prompt injection in %s (%s): %r",
                source_path,
                first.pattern_name,
                first.matched_text,
            )
            return (
                f"[BLOCKED: injection detected in {source_path} "
                f"({first.pattern_name})]"
            )
        for threat in threats:
            logger.warning(
                "Possible prompt injection in %s (%s, line %d): %r",
                source_path,
                threat.pattern_name,
                threat.line_number,
                threat.matched_text,
            )

    return content.strip()
