"""PreferenceLearner — background LLM extraction of user preferences from turns."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...llm.llm import LLM
    from .store import PreferenceStore

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """\
Analyze this conversation turn and extract any user preferences expressed or implied.

User: {user_text}
Assistant: {assistant_text}

Extract preferences like:
- Communication style (verbose/concise, language preference)
- Topic interests (weather units, news topics)
- Interaction patterns (greeting style, humor preference)
- Corrections ("don't do X", "I prefer Y instead")

Return ONLY a JSON array of short preference strings, or [] if none found.
Example: ["Prefers weather in Celsius", "Likes brief greetings"]

JSON array:"""

_MAX_RETRIES = 3


class PreferenceLearner:
    """Extracts user preferences from conversation turns via background LLM analysis.

    Follows the same fire-and-forget pattern as MemoryService:
    - Called via ``asyncio.ensure_future()`` from ContextManager
    - 3 retry attempts with exponential backoff
    - Never crashes the pipeline
    """

    def __init__(self, store: PreferenceStore, llm: LLM) -> None:
        self._store = store
        self._llm = llm

    async def analyze_turn(
        self, user: str, user_text: str, assistant_text: str,
    ) -> None:
        """Extract preferences from a conversation turn.

        Skips trivial turns (short text, unknown speaker).
        Retries up to 3 times with exponential backoff.
        """
        if len(user_text) < 15 or user == "Unknown":
            return

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                extracted = await self._extract(user_text, assistant_text)
                for pref in extracted:
                    self._store.add_if_new(user, pref, source="inferred")
                return
            except Exception:
                if attempt == _MAX_RETRIES:
                    logger.warning(
                        "Preference extraction failed for %s after %d attempts",
                        user,
                        attempt,
                        exc_info=True,
                    )
                else:
                    await asyncio.sleep(1.0 * attempt)

    async def _extract(
        self, user_text: str, assistant_text: str,
    ) -> list[str]:
        """Call LLM to extract preferences. Returns list of preference strings."""
        prompt = _EXTRACTION_PROMPT.format(
            user_text=user_text,
            assistant_text=assistant_text,
        )
        messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]
        response = await self._llm.complete(
            messages,
            temperature=0.3,
            max_tokens=200,
        )
        return _parse_json_list(response)


def _parse_json_list(text: str) -> list[str]:
    """Parse a JSON array of strings from LLM output.

    Tolerates markdown fences and leading/trailing whitespace.
    Returns empty list on any parse failure.
    """
    cleaned = text.strip()
    # Strip markdown code fences if present
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = [line for line in lines if not line.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return [p.strip() for p in parsed if isinstance(p, str) and p.strip()]
    except (json.JSONDecodeError, ValueError):
        logger.debug("Failed to parse preference extraction response: %s", text)
    return []
