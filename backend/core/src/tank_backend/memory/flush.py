"""MemoryFlusher — best-effort fact extraction before compaction destroys detail.

Run as a silent intermediate step inside :meth:`ContextManager.compact`,
*after* the tail has been selected but *before* the summarizer compresses
the discarded messages. Pulls out durable facts, preference reinforcements,
and decisions from the soon-to-be-summarized window, then routes them to
:class:`MemoryService` and :class:`PreferenceStore`.

Failure is non-fatal — the flush is a backstop, not a hard dependency.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..users import is_guest

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam

    from ..llm.llm import LLM
    from ..preferences.store import PreferenceStore
    from .service import MemoryService

logger = logging.getLogger(__name__)


_FLUSH_PROMPT = """\
The following messages are about to be summarized and lose detail.
Extract anything worth persisting before that happens.

Be terse. Skip filler. Skip duplicates.

Categories:
- facts_to_remember: durable user truths the assistant should know later
  (e.g. "Lives in Berlin", "Owns a Tesla Model 3", "Manages the API team").
  Skip transient context like the topic of this conversation.
- preferences_to_reinforce: preferences already known and confirmed by this
  exchange. Phrased as user-facing rules ("Prefers metric units").
- decisions: decisions made in this window, with their rationale.

Return strictly this JSON shape, no markdown fences, no commentary:
{{
  "facts_to_remember": ["..."],
  "preferences_to_reinforce": ["..."],
  "decisions": [{{"what": "...", "why": "..."}}]
}}

Use empty arrays when a category has nothing.

Messages:
{messages}

JSON:"""


@dataclass(frozen=True)
class FlushDecision:
    what: str
    why: str


@dataclass(frozen=True)
class FlushResult:
    facts_to_remember: list[str] = field(default_factory=list)
    preferences_to_reinforce: list[str] = field(default_factory=list)
    decisions: list[FlushDecision] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return (
            not self.facts_to_remember
            and not self.preferences_to_reinforce
            and not self.decisions
        )


class MemoryFlusher:
    """Pre-compaction extractor of facts/preferences/decisions.

    Stateless — one instance per :class:`ContextManager` is fine. The
    ``flush`` method is the only public surface; it returns an empty
    :class:`FlushResult` on any failure and never raises.
    """

    def __init__(
        self,
        *,
        llm: LLM,
        memory: MemoryService | None,
        preferences: PreferenceStore | None,
        timeout_seconds: float = 8.0,
        max_messages: int = 40,
    ) -> None:
        self._llm = llm
        self._memory = memory
        self._preferences = preferences
        self._timeout_seconds = timeout_seconds
        self._max_messages = max_messages

    async def flush(
        self,
        *,
        user: str,
        messages: list[dict[str, Any]],
    ) -> FlushResult:
        """Run one LLM extraction over ``messages`` and route the writes.

        ``messages`` should be the slice that :meth:`ContextManager.compact`
        is about to hand to the summarizer (everything between system prompt
        and tail). Guests and empty windows short-circuit immediately.
        """
        if is_guest(user) or not user or not messages:
            return FlushResult()

        try:
            result = await asyncio.wait_for(
                self._extract(messages), timeout=self._timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.debug("MemoryFlusher: LLM call timed out after %.1fs",
                         self._timeout_seconds)
            return FlushResult()
        except Exception:
            logger.warning("MemoryFlusher: LLM call failed", exc_info=True)
            return FlushResult()

        await self._apply(user, result)
        return result

    async def _extract(self, messages: list[dict[str, Any]]) -> FlushResult:
        rendered = _render_messages(messages, limit=self._max_messages)
        prompt = _FLUSH_PROMPT.format(messages=rendered)
        chat_messages: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": prompt}
        ]
        response = await self._llm.complete(
            chat_messages,
            temperature=0.2,
            max_tokens=600,
        )
        return _parse_flush_response(response)

    async def _apply(self, user: str, result: FlushResult) -> None:
        """Route the extraction outputs to memory and preferences.

        Each write is fire-and-forget: a single failure doesn't poison the
        others, and nothing blocks the caller's compaction path.
        """
        if self._memory is not None:
            for fact in result.facts_to_remember:
                asyncio.create_task(self._store_memory(user, fact))
            for decision in result.decisions:
                text = f"{decision.what} — because {decision.why}".strip(" —")
                asyncio.create_task(self._store_memory(user, text))

        if self._preferences is not None:
            for pref in result.preferences_to_reinforce:
                try:
                    self._preferences.reinforce(user, pref)
                except Exception:
                    logger.debug(
                        "MemoryFlusher: reinforce failed for %r",
                        pref,
                        exc_info=True,
                    )

    async def _store_memory(self, user: str, text: str) -> None:
        if self._memory is None or not text:
            return
        try:
            await self._memory.store_turn(user, text, "")
        except Exception:
            logger.debug("MemoryFlusher: memory store failed", exc_info=True)


def _render_messages(
    messages: list[dict[str, Any]], *, limit: int,
) -> str:
    """Render messages as plain text, truncating tool noise."""
    lines: list[str] = []
    for msg in messages[-limit:]:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        if not content:
            continue
        # Light-truncate giant blobs (tool results) so we don't blow the
        # prompt budget on JSON dumps.
        if len(content) > 800:
            content = content[:800] + "…"
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _parse_flush_response(text: str) -> FlushResult:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = [line for line in lines if not line.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    try:
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        logger.debug("MemoryFlusher: failed to parse JSON output: %s", text)
        return FlushResult()

    if not isinstance(parsed, dict):
        return FlushResult()

    facts = _string_list(parsed.get("facts_to_remember"))
    prefs = _string_list(parsed.get("preferences_to_reinforce"))
    decisions = _decision_list(parsed.get("decisions"))

    return FlushResult(
        facts_to_remember=facts,
        preferences_to_reinforce=prefs,
        decisions=decisions,
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        item.strip() for item in value
        if isinstance(item, str) and item.strip()
    ]


def _decision_list(value: Any) -> list[FlushDecision]:
    if not isinstance(value, list):
        return []
    out: list[FlushDecision] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        what = item.get("what")
        why = item.get("why")
        if isinstance(what, str) and isinstance(why, str) \
                and what.strip() and why.strip():
            out.append(FlushDecision(what=what.strip(), why=why.strip()))
    return out
