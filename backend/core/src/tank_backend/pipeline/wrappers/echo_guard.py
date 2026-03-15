"""Echo guard — semantic self-echo detection and VAD threshold adjustment.

Layer 1: VAD energy threshold — during TTS playback, raise the VAD speech_threshold
         so only loud/close speech triggers detection (filters echo at signal level).
Layer 2: Self-echo text detection — compare ASR output against recent TTS text using
         token overlap; discard transcripts that are too similar to what was just spoken.
"""

from __future__ import annotations

import logging
import re
import time
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class _TTSEntry:
    """A recent TTS utterance with its timestamp."""

    tokens: set[str]
    timestamp: float


@dataclass
class EchoGuardConfig:
    """Configuration for the echo guard system."""

    enabled: bool = True
    # Layer 1: VAD threshold during playback
    vad_threshold_during_playback: float = 0.85
    # Layer 2: self-echo text detection
    similarity_threshold: float = 0.6
    window_seconds: float = 10.0


_PUNCTUATION_RE = re.compile(r"[^\w\s]", re.UNICODE)


def _tokenize(text: str) -> set[str]:
    """Tokenize text into a set of lowercase words, stripping punctuation."""
    cleaned = _PUNCTUATION_RE.sub("", text.lower())
    return {w for w in cleaned.split() if w}


class SelfEchoDetector:
    """Detects when ASR transcribes the assistant's own TTS output.

    Maintains a sliding window of recent TTS text. When ASR produces a
    transcript, computes token overlap against the window. If overlap
    exceeds the threshold, the transcript is flagged as self-echo.
    """

    def __init__(self, config: EchoGuardConfig | None = None) -> None:
        self._config = config or EchoGuardConfig()
        self._recent_tts: deque[_TTSEntry] = deque()

    def record_tts(self, text: str) -> None:
        """Record text that was sent to TTS for playback."""
        tokens = _tokenize(text)
        if tokens:
            self._recent_tts.append(_TTSEntry(tokens=tokens, timestamp=time.time()))

    def is_echo(self, transcript: str) -> bool:
        """Check if a transcript is likely an echo of recent TTS output.

        Returns True if the transcript's token overlap with recent TTS
        text exceeds the configured threshold.
        """
        if not self._config.enabled:
            return False

        self._evict_old_entries()

        transcript_tokens = _tokenize(transcript)
        if not transcript_tokens:
            return False

        # Build combined token set from all recent TTS entries
        tts_tokens: set[str] = set()
        for entry in self._recent_tts:
            tts_tokens |= entry.tokens

        if not tts_tokens:
            return False

        # Token overlap: what fraction of the transcript's tokens appear in TTS?
        overlap = transcript_tokens & tts_tokens
        ratio = len(overlap) / len(transcript_tokens)

        if ratio >= self._config.similarity_threshold:
            logger.info(
                "Self-echo detected: %.0f%% overlap (%d/%d tokens). "
                "Transcript: '%s'",
                ratio * 100,
                len(overlap),
                len(transcript_tokens),
                transcript[:80],
            )
            return True

        return False

    def _evict_old_entries(self) -> None:
        """Remove TTS entries older than the configured window."""
        cutoff = time.time() - self._config.window_seconds
        while self._recent_tts and self._recent_tts[0].timestamp < cutoff:
            self._recent_tts.popleft()

    def clear(self) -> None:
        """Clear all recorded TTS text."""
        self._recent_tts.clear()
