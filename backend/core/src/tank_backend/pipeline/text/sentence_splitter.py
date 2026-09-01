"""Sentence-level buffering of streamed LLM tokens for TTS batching.

Bridges the token stream out of the agent graph to sentence-grouped
batches so speech synthesis can start after the first few sentences
instead of after the whole turn (see
docs/s2s-comparison-and-improvement-plan.md §P0-5).

Splitting rules:

- Chinese sentence-end punctuation (。！？；…) cuts immediately; runs of
  punctuation and trailing closing quotes/brackets stay with the sentence.
- Latin ``.!?`` cuts only when followed by whitespace — which excludes
  decimals (``3.14``), URLs (``example.com``) and filenames for free.
  Common abbreviations (``Mr.``, ``e.g.`` …) are additionally excluded.
- Paragraph breaks (``\\n\\n``) are boundaries.

Withholding rules (things that must never be split or spoken):

- Fenced code blocks (``` … ```) are never cut inside; an unclosed fence
  withholds everything from its opening marker. Code is dropped by the
  TTS normalizer anyway, so holding it costs no latency.
- Complete image markdown (``![alt](url)``) is removed from the speech
  path entirely — images are surfaced to the UI as attachments from the
  full text instead.
"""

from __future__ import annotations

import re

# Complete image markdown — removed (images never reach TTS). Surrounding
# inline horizontal whitespace collapses to one space.
_IMAGE_RE = re.compile(r"[ \t]*!\[[^\]]*\]\([^)]*\)[ \t]*")

# Fenced code block markers.
_FENCE_RE = re.compile(r"```")

# CJK boundary: run of sentence-end punctuation + trailing closers.
_CJK_BOUNDARY_RE = re.compile(r"[。！？；…]+[”』」）)]*")

# Latin boundary: . ! ? with whitespace right after (the lookahead is what
# keeps decimals, URLs and mid-abbreviation dots from cutting).
_LATIN_BOUNDARY_RE = re.compile(r"[.!?](?=\s)")

# Paragraph boundary.
_PARAGRAPH_RE = re.compile(r"\n\n")

# Words that end with "." but do not end a sentence (compared dot-stripped,
# case-insensitively, against the token immediately before a candidate ".").
_ABBREVIATIONS = frozenset({
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
    "eg", "ie", "inc", "ltd", "co", "corp", "no", "nos", "fig", "figs",
    "eq", "eqs", "approx", "ca", "cf", "al", "dept", "univ", "us",
})

# Matches the trailing word characters/dots before a candidate boundary.
_WORD_TAIL_RE = re.compile(r"[A-Za-z.]+$")


class SentenceBuffer:
    """Accumulates streamed tokens and releases sentence-grouped batches.

    Feed token deltas with :meth:`feed`; poll :meth:`drain_ready` for
    complete batches (``min_sentences`` sentences per batch); call
    :meth:`flush` once the stream ends to emit the remainder.
    """

    def __init__(self, min_sentences: int = 5) -> None:
        self._min = max(1, min_sentences)
        self._buf = ""

    def feed(self, token: str) -> None:
        """Append a token delta (any size) to the buffer."""
        if token:
            self._buf += token

    def drain_ready(self) -> list[str]:
        """Return every complete batch currently available (often none)."""
        batches: list[str] = []
        while (batch := self._take_batch()) is not None:
            batches.append(batch)
        return batches

    def flush(self) -> str:
        """Emit and drop the remainder. Unclosed code fences are discarded."""
        self._buf = _IMAGE_RE.sub(" ", self._buf)
        text = self._buf
        self._buf = ""
        fence_starts = [m.start() for m in _FENCE_RE.finditer(text)]
        if len(fence_starts) % 2 == 1:
            text = text[: fence_starts[-1]]
        return text.strip()

    def flush_complete(self) -> str:
        """Emit every complete sentence held so far, keeping the tail.

        Used at turn pauses (the model stops to call a tool): a lone
        sentence must not wait for ``min_sentences`` company while tools
        run — potentially tens of seconds. Unlike :meth:`flush`, any
        incomplete trailing fragment stays buffered so it can join the
        next batch, and an unclosed fence still withholds its content.
        """
        self._buf = _IMAGE_RE.sub(" ", self._buf)
        boundaries = _find_boundaries(self._buf)
        if not boundaries:
            return ""
        cut = boundaries[-1]
        text = self._buf[:cut].strip()
        self._buf = self._buf[cut:]
        return text

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _take_batch(self) -> str | None:
        """Pop one batch of ``min_sentences`` sentences, or None."""
        self._buf = _IMAGE_RE.sub(" ", self._buf)
        boundaries = _find_boundaries(self._buf)
        if len(boundaries) < self._min:
            return None
        cut = boundaries[self._min - 1]
        batch = self._buf[:cut].strip()
        self._buf = self._buf[cut:]
        return batch or None


def _find_boundaries(text: str) -> list[int]:
    """Return sorted cut positions (end of each complete sentence).

    A cut position is safe only outside fenced code blocks — an unclosed
    fence suppresses everything from its opening marker on.
    """
    fence_starts = [m.start() for m in _FENCE_RE.finditer(text)]
    spans: list[tuple[int, int]] = []
    for i in range(0, len(fence_starts) - 1, 2):
        spans.append((fence_starts[i], fence_starts[i + 1] + 3))
    if len(fence_starts) % 2 == 1:
        spans.append((fence_starts[-1], len(text)))

    positions: set[int] = set()
    for m in _CJK_BOUNDARY_RE.finditer(text):
        positions.add(m.end())
    for m in _LATIN_BOUNDARY_RE.finditer(text):
        i = m.start()
        if text[i] == "." and _is_abbreviation(text, i):
            continue
        positions.add(i + 1)
    for m in _PARAGRAPH_RE.finditer(text):
        positions.add(m.end())

    return sorted(
        p for p in positions if not any(s <= p < e for s, e in spans)
    )


def _is_abbreviation(text: str, dot_index: int) -> bool:
    """True when the "." at ``dot_index`` ends a known abbreviation."""
    tail = _WORD_TAIL_RE.search(text[:dot_index])
    if tail is None:
        return False
    word = tail.group(0).replace(".", "").lower()
    return word in _ABBREVIATIONS
