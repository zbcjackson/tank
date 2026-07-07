"""Language detection utility — lingua-backed, cached, with confidence fallback."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from lingua import IsoCode639_1, Language, LanguageDetector, LanguageDetectorBuilder


@dataclass(frozen=True)
class LanguageDetection:
    """Detection result: ISO 639-1 language code + confidence (0.0–1.0)."""

    language: str
    confidence: float


def _iso_code(code: str) -> IsoCode639_1:
    """Convert a 2-letter ISO 639-1 string to the lingua enum."""
    return getattr(IsoCode639_1, code.upper())


@lru_cache(maxsize=8)
def _build_detector(languages: tuple[str, ...]) -> LanguageDetector:
    """Build and cache a lingua detector for the given candidate set."""
    langs = [Language.from_iso_code_639_1(_iso_code(c)) for c in languages]
    return LanguageDetectorBuilder.from_languages(*langs).build()


def detect_language(
    text: str,
    *,
    candidates: tuple[str, ...] = ("zh", "en"),
    preferred: str = "zh",
    threshold: float = 0.55,
) -> LanguageDetection:
    """Detect language from text, constrained to ``candidates``.

    Uses lingua for high-accuracy detection including Chinese-English
    code-switching (e.g. "今天weather很好" → zh).

    When the top confidence is below ``threshold`` or the text has no
    meaningful alphabetic/CJK content, falls back to ``preferred``.

    Args:
        text: The text to analyze.
        candidates: Tuple of ISO 639-1 codes to consider.
        preferred: Fallback language when confidence is low.
        threshold: Minimum confidence to accept a detection result.

    Returns:
        LanguageDetection with the detected language and confidence.
    """
    # Strip and check for meaningful content
    stripped = text.strip()
    if not stripped or not any(c.isalpha() for c in stripped):
        return LanguageDetection(language=preferred, confidence=0.0)

    if len(candidates) < 2:
        # lingua needs ≥2 languages; if only 1 or none, return preferred
        return LanguageDetection(language=preferred, confidence=1.0)

    detector = _build_detector(candidates)
    values = detector.compute_language_confidence_values(stripped)

    if not values:
        return LanguageDetection(language=preferred, confidence=0.0)

    top = values[0]
    confidence = top.value
    language = top.language.iso_code_639_1.name.lower()

    if confidence < threshold:
        return LanguageDetection(language=preferred, confidence=confidence)

    return LanguageDetection(language=language, confidence=confidence)
