"""TitleGenerator — produce a short conversation title via the LLM.

Called fire-and-forget after the first assistant turn completes
(see ``Brain._maybe_request_title``) and synchronously by
``POST /api/conversations/{id}/title/regenerate``. Both paths share
this single implementation so a manual regenerate uses the same prompt
as the automatic first-turn run.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .store import ConversationStore

if TYPE_CHECKING:
    from ..llm.llm import LLM

logger = logging.getLogger(__name__)


_TITLE_SYSTEM_PROMPT = (
    "You write extremely short conversation titles — like an email subject "
    "line. Reply with just the title in plain text. No quotes, no punctuation "
    "at the end, no prefixes like 'Title:'. Match the language of the "
    "conversation. 2 to 6 words is ideal; 60 characters is the absolute max."
)

_TITLE_USER_TEMPLATE = (
    "Give this conversation a short, descriptive title.\n\n"
    "USER:\n{user}\n\n"
    "ASSISTANT:\n{assistant}\n"
)

# Cap each side of the prompt so a long first turn doesn't blow the
# context window. The LLM only needs the gist to pick a title.
_MAX_USER_CHARS = 800
_MAX_ASSISTANT_CHARS = 800
_MAX_TITLE_CHARS = 80
_MAX_TITLE_TOKENS = 32


class TitleGenerator:
    """Generate and persist short conversation titles."""

    def __init__(self, llm: LLM, store: ConversationStore) -> None:
        self._llm = llm
        self._store = store

    async def generate(self, conversation_id: str) -> str | None:
        """Build a title for ``conversation_id`` and save it. Returns the title.

        Returns ``None`` when the conversation is missing, the LLM produces
        empty output, or any error occurs — callers treat ``None`` as a
        no-op (the conversation keeps whatever title it already had).
        """
        conversation = self._store.load(conversation_id)
        if conversation is None:
            logger.debug("Title generation skipped: %s not found", conversation_id)
            return None

        user_text, assistant_text = _extract_first_exchange(conversation.messages)
        if not user_text and not assistant_text:
            logger.debug(
                "Title generation skipped: %s has no user/assistant content",
                conversation_id,
            )
            return None

        prompt = _TITLE_USER_TEMPLATE.format(
            user=_truncate(user_text, _MAX_USER_CHARS),
            assistant=_truncate(assistant_text, _MAX_ASSISTANT_CHARS),
        )

        try:
            raw = await self._llm.complete(
                messages=[
                    {"role": "system", "content": _TITLE_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=_MAX_TITLE_TOKENS,
            )
        except Exception:
            logger.warning(
                "Title LLM call failed for %s", conversation_id, exc_info=True,
            )
            return None

        title = _clean_title(raw)
        if not title:
            return None

        # Re-load before saving so we don't clobber concurrent edits
        # (e.g. user renamed the conversation while the LLM was running).
        latest = self._store.load(conversation_id)
        if latest is None:
            return None
        latest.title = title
        self._store.save(latest)
        logger.info("Generated title for %s: %r", conversation_id, title)
        return title


def _extract_first_exchange(messages: list[dict[str, Any]]) -> tuple[str, str]:
    """Pull the first user message and the first assistant reply as plain text."""
    user_text = ""
    assistant_text = ""
    for msg in messages:
        role = msg.get("role")
        if role == "user" and not user_text:
            user_text = _content_to_str(msg.get("content"))
        elif role == "assistant" and user_text and not assistant_text:
            text = _content_to_str(msg.get("content"))
            if text:
                assistant_text = text
        if user_text and assistant_text:
            break
    return user_text, assistant_text


def _content_to_str(content: Any) -> str:
    """Coerce OpenAI-style content (string or parts list) into plain text."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return " ".join(parts).strip()
    return ""


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _clean_title(raw: str) -> str:
    """Strip whitespace, surrounding quotes, and 'Title:' prefixes."""
    title = raw.strip()
    # The model occasionally wraps the title in quotes; peel one layer.
    for opener, closer in (('"', '"'), ("'", "'"), ("“", "”"), ("「", "」")):
        if title.startswith(opener) and title.endswith(closer) and len(title) >= 2:
            title = title[1:-1].strip()
            break
    lowered = title.lower()
    for prefix in ("title:", "subject:"):
        if lowered.startswith(prefix):
            title = title[len(prefix):].strip()
            break
    # Collapse any newlines the model might emit and hard-cap length.
    title = " ".join(title.split())
    if len(title) > _MAX_TITLE_CHARS:
        title = title[:_MAX_TITLE_CHARS].rstrip()
    return title
