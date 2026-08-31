"""Append-only stabilization of streaming ASR partial transcripts.

A streaming recognizer revises its hypothesis as audio arrives, so the raw
partial makes the UI text flicker: earlier words get re-scored and the tail
changes on every update. Mirroring s2s's ``_stable_transcript_words``
(docs/s2s-comparison-and-improvement-plan.md §P2), a word is displayed only
once two consecutive hypotheses agree on it, and the newest agreeing word is
held back — it sat at the speculative edge of the previous hypothesis and may
still be revised.

Tokenization is bilingual: each CJK character is its own token (the natural
stable unit for Chinese), while latin runs are whitespace-delimited words
compared case-folded with edge punctuation stripped. The display text is
always a raw prefix of the live hypothesis, so spacing and punctuation
survive exactly.

Unlike s2s's Realtime delta protocol (which must withhold a revised word
forever), tank's UI replaces the partial wholesale by msg_id — so the rare
LM re-score that revises an already-shown word is displayed as a correction.
"""

from __future__ import annotations

from dataclasses import dataclass
from unicodedata import category


@dataclass(frozen=True, slots=True)
class _Token:
    """One stability unit: a cut offset into the hypothesis + comparison form."""

    end: int         # exclusive end offset of the token in the hypothesis
    comparison: str  # normalized form used for cross-hypothesis comparison


def _is_cjk_char(ch: str) -> bool:
    """CJK unified ideographs, incl. Extension A and compatibility forms."""
    return "㐀" <= ch <= "鿿" or "豈" <= ch <= "﫿"


def _strip_edge_punctuation(token: str) -> str:
    start, end = 0, len(token)
    while start < end and category(token[start]).startswith("P"):
        start += 1
    while end > start and category(token[end - 1]).startswith("P"):
        end -= 1
    return token[start:end]


def _tokenize(text: str) -> list[_Token]:
    """Split a hypothesis into stability tokens.

    Each CJK character is its own token; every other run of non-space
    characters is one token whose comparison form drops edge punctuation
    and case. Pure-punctuation runs are dropped entirely.
    """
    tokens: list[_Token] = []
    i, n = 0, len(text)
    while i < n:
        if _is_cjk_char(text[i]):
            tokens.append(_Token(end=i + 1, comparison=text[i].casefold()))
            i += 1
            continue
        if text[i].isspace():
            i += 1
            continue
        j = i + 1
        while j < n and not text[j].isspace() and not _is_cjk_char(text[j]):
            j += 1
        comparison = _strip_edge_punctuation(text[i:j]).casefold()
        if comparison:
            tokens.append(_Token(end=j, comparison=comparison))
        i = j
    return tokens


class PartialTranscriptStabilizer:
    """Turns raw streaming hypotheses into an append-only display prefix."""

    def __init__(self) -> None:
        self._previous: list[_Token] = []
        self._last_display = ""

    def reset(self) -> None:
        """Forget the previous utterance's hypotheses."""
        self._previous = []
        self._last_display = ""

    def feed(self, hypothesis: str) -> str | None:
        """Stabilize one cumulative hypothesis.

        Returns the display text — a prefix of ``hypothesis`` covering the
        words confirmed by this and the previous hypothesis, minus the newest
        edge word — or ``None`` when the confirmed prefix is unchanged since
        the last feed (the caller should not re-post an identical partial).
        """
        tokens = _tokenize(hypothesis)
        previous, self._previous = self._previous, tokens
        common = 0
        for old, new in zip(previous, tokens, strict=False):
            if old.comparison != new.comparison:
                break
            common += 1
        display = hypothesis[: tokens[common - 2].end] if common >= 2 else ""
        if display == self._last_display:
            return None
        self._last_display = display
        return display
