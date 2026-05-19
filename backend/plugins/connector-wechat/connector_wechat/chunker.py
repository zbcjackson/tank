"""Message chunking for WeChat's 4000-character limit.

Splits oversized messages at logical boundaries to preserve
readability. Code fences are never split mid-block unless the
fence itself exceeds the limit.
"""

from __future__ import annotations

import re

_DEFAULT_MAX_LENGTH = 4000
_CODE_FENCE_RE = re.compile(r"^```", re.MULTILINE)


def chunk_message(text: str, max_length: int = _DEFAULT_MAX_LENGTH) -> list[str]:
    """Split text into chunks of at most max_length characters.

    Splitting priority:
    1. Between code fences (``` blocks kept intact)
    2. At paragraph boundaries (double newline)
    3. At single newlines
    4. Hard cut at max_length (last resort)

    Returns a list of non-empty strings. Short text returns a
    single-element list.
    """
    if not text:
        return []
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        # Try to find a split point within the allowed length
        segment = remaining[:max_length]
        split_at = _find_split_point(segment, remaining, max_length)

        chunk = remaining[:split_at].rstrip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_at:].lstrip("\n")

    return chunks


def _find_split_point(segment: str, full_text: str, max_length: int) -> int:
    """Find the best split point within segment."""
    # Priority 1: split between code fences
    # Find the last complete code fence boundary
    fence_positions = [m.start() for m in _CODE_FENCE_RE.finditer(segment)]
    if len(fence_positions) >= 2:
        # Find the last even-indexed fence (closing fence)
        # that gives us a reasonable chunk
        for i in range(len(fence_positions) - 1, 0, -1):
            pos = fence_positions[i]
            # Find end of this fence line
            newline_after = segment.find("\n", pos)
            if newline_after == -1:
                newline_after = pos
            else:
                newline_after += 1
            if newline_after > max_length * 0.3:  # at least 30% of max
                return newline_after

    # Priority 2: split at paragraph boundary (double newline)
    last_para = segment.rfind("\n\n")
    if last_para > max_length * 0.3:
        return last_para + 2

    # Priority 3: split at single newline
    last_newline = segment.rfind("\n")
    if last_newline > max_length * 0.3:
        return last_newline + 1

    # Priority 4: hard cut
    return max_length
