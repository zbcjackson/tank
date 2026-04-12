"""Pre-TTS text normalizer — converts LLM markdown output to speakable text."""

from __future__ import annotations

import re

# ── Fenced code blocks (```...```) ──────────────────────────────────────────
_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)

# ── Inline code (`...`) ─────────────────────────────────────────────────────
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")

# ── Images ![alt](url) — must come before links ─────────────────────────────
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")

# ── Links [text](url) ───────────────────────────────────────────────────────
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")

# ── Headers (# ... at line start) ───────────────────────────────────────────
_HEADER_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)

# ── Bold/italic (order: bold-italic first, then bold, then italic) ───────────
_BOLD_ITALIC_RE = re.compile(r"\*{3}(.+?)\*{3}|_{3}(.+?)_{3}")
_BOLD_RE = re.compile(r"\*{2}(.+?)\*{2}|_{2}(.+?)_{2}")
_ITALIC_RE = re.compile(r"(?<!\w)\*(.+?)\*(?!\w)|(?<!\w)_(.+?)_(?!\w)")

# ── Strikethrough ~~text~~ ───────────────────────────────────────────────────
_STRIKETHROUGH_RE = re.compile(r"~~(.+?)~~")

# ── Blockquotes (> at line start) ────────────────────────────────────────────
_BLOCKQUOTE_RE = re.compile(r"^>\s?", re.MULTILINE)

# ── Horizontal rules (---, ***, ___) ─────────────────────────────────────────
_HR_RE = re.compile(r"^[-*_]{3,}\s*$", re.MULTILINE)

# ── Unordered list markers (-, *, +) ─────────────────────────────────────────
_UL_RE = re.compile(r"^[\t ]*[-*+]\s+", re.MULTILINE)

# ── Ordered list markers (1. 2. etc.) ────────────────────────────────────────
_OL_RE = re.compile(r"^[\t ]*\d+\.\s+", re.MULTILINE)

# ── Emoji (Unicode ranges covering most emoji) ──────────────────────────────
_EMOJI_RE = re.compile(
    "["
    "\U0001f600-\U0001f64f"  # emoticons
    "\U0001f300-\U0001f5ff"  # symbols & pictographs
    "\U0001f680-\U0001f6ff"  # transport & map
    "\U0001f1e0-\U0001f1ff"  # flags
    "\U0001f900-\U0001f9ff"  # supplemental symbols
    "\U0001fa00-\U0001fa6f"  # chess symbols
    "\U0001fa70-\U0001faff"  # symbols extended-A
    "\U00002702-\U000027b0"  # dingbats
    "\U0000fe00-\U0000fe0f"  # variation selectors
    "\U0000200d"             # zero-width joiner
    "\U000020e3"             # combining enclosing keycap
    "\U00002600-\U000026ff"  # misc symbols
    "\U00002300-\U000023ff"  # misc technical
    "]+",
    re.UNICODE,
)

# ── Special characters ──────────────────────────────────────────────────────
_SPECIAL_CHARS = str.maketrans({
    "\u2014": ", ",   # em dash
    "\u2013": ", ",   # en dash
    "\u2026": "...",  # ellipsis character → three dots (TTS handles these)
    "\u201c": '"',    # left double smart quote
    "\u201d": '"',    # right double smart quote
    "\u2018": "'",    # left single smart quote
    "\u2019": "'",    # right single smart quote
    "\u2022": "",     # bullet •
    "\u25aa": "",     # small black square ▪
    "\u25ab": "",     # small white square ▫
    "\u25cf": "",     # black circle ●
    "\u25cb": "",     # white circle ○
})

# ── Whitespace collapse ─────────────────────────────────────────────────────
_MULTI_SPACE_RE = re.compile(r"[ \t]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{2,}")


def normalize_for_tts(text: str) -> str:
    """Normalize LLM output into clean, speakable text for TTS engines.

    Strips markdown formatting, removes emoji, normalizes special characters,
    and collapses whitespace. Preserves natural speech punctuation.
    """
    if not text:
        return ""

    # 1. Remove fenced code blocks entirely
    text = _CODE_BLOCK_RE.sub("", text)

    # 2. Inline code → just the content
    text = _INLINE_CODE_RE.sub(r"\1", text)

    # 3. Images → alt text
    text = _IMAGE_RE.sub(r"\1", text)

    # 4. Links → link text
    text = _LINK_RE.sub(r"\1", text)

    # 5. Horizontal rules → nothing
    text = _HR_RE.sub("", text)

    # 6. Headers → just the text
    text = _HEADER_RE.sub("", text)

    # 7. Blockquotes → just the text
    text = _BLOCKQUOTE_RE.sub("", text)

    # 8. Bold/italic (order matters: bold-italic → bold → italic)
    text = _BOLD_ITALIC_RE.sub(lambda m: m.group(1) or m.group(2), text)
    text = _BOLD_RE.sub(lambda m: m.group(1) or m.group(2), text)
    text = _ITALIC_RE.sub(lambda m: m.group(1) or m.group(2), text)

    # 9. Strikethrough
    text = _STRIKETHROUGH_RE.sub(r"\1", text)

    # 10. List markers
    text = _UL_RE.sub("", text)
    text = _OL_RE.sub("", text)

    # 11. Emoji
    text = _EMOJI_RE.sub("", text)

    # 12. Special characters
    text = text.translate(_SPECIAL_CHARS)

    # 13. Collapse whitespace: newlines → space, multi-space → single
    text = _MULTI_NEWLINE_RE.sub(" ", text)
    text = text.replace("\n", " ")
    text = _MULTI_SPACE_RE.sub(" ", text)

    return text.strip()
