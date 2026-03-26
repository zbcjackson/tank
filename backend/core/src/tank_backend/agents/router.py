"""Router — classifies user intent and yields a HANDOFF to the appropriate agent."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .base import Agent, AgentOutput, AgentOutputType, AgentState

if TYPE_CHECKING:
    from ..llm.llm import LLM

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Route:
    """A single routing rule mapping intent to an agent."""

    name: str
    agent_name: str
    keywords: list[str] = field(default_factory=list)
    description: str = ""


class Router(Agent):
    """Intent classifier that yields a single HANDOFF output.

    Resolution order:
    1. Fast-path: regex keyword match against configured routes
    2. Slow-path: single LLM call with routes as function schema
    3. Fallback: default agent (typically "chat")
    """

    def __init__(
        self,
        routes: list[Route],
        default_agent: str = "chat",
        llm: LLM | None = None,
    ) -> None:
        super().__init__("router")
        self._routes = routes
        self._default_agent = default_agent
        self._llm = llm

        # Public read-only accessors for logging / introspection
        self.routes = routes
        self.default_agent = default_agent

        # Pre-compile keyword patterns for fast-path
        # CJK keywords use plain substring match (no word boundaries in Chinese).
        # Latin keywords use \b word boundaries to avoid partial matches.
        self._patterns: list[tuple[Route, re.Pattern[str]]] = []
        for route in routes:
            if route.keywords:
                parts: list[str] = []
                for kw in route.keywords:
                    escaped = re.escape(kw)
                    if _is_cjk_keyword(kw):
                        parts.append(escaped)  # substring match
                    else:
                        parts.append(r"\b" + escaped + r"\b")  # word-boundary match
                pattern = re.compile(
                    "(?:" + "|".join(parts) + ")",
                    re.IGNORECASE,
                )
                self._patterns.append((route, pattern))

    async def run(self, state: AgentState) -> AsyncIterator[AgentOutput]:
        """Classify the latest user message and yield a HANDOFF."""
        text = self._extract_user_text(state)
        if not text:
            yield AgentOutput(
                type=AgentOutputType.HANDOFF,
                target_agent=self._default_agent,
            )
            return

        # 1. Fast-path: keyword match
        target = self._fast_path(text)
        if target is not None:
            logger.info("Router fast-path matched: %s → %s", text[:60], target)
            yield AgentOutput(type=AgentOutputType.HANDOFF, target_agent=target)
            return

        # 2. Slow-path: LLM classification (if LLM available)
        if self._llm is not None:
            target = await self._slow_path(text)
            if target is not None:
                logger.info("Router slow-path classified: %s → %s", text[:60], target)
                yield AgentOutput(type=AgentOutputType.HANDOFF, target_agent=target)
                return

        # 3. Fallback
        logger.info("Router no match for: %s → fallback %s", text[:60], self._default_agent)
        yield AgentOutput(
            type=AgentOutputType.HANDOFF,
            target_agent=self._default_agent,
        )

    def _extract_user_text(self, state: AgentState) -> str:
        """Get the last user message text from state."""
        for msg in reversed(state.messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                return content if isinstance(content, str) else ""
        return ""

    def _fast_path(self, text: str) -> str | None:
        """Try regex keyword match against routes. Returns agent name or None."""
        for route, pattern in self._patterns:
            if pattern.search(text):
                return route.agent_name
        return None

    async def _slow_path(self, text: str) -> str | None:
        """Use LLM to classify intent. Returns agent name or None."""
        if not self._routes:
            return None

        route_descriptions = "\n".join(
            f"- {r.name}: {r.description} (agent: {r.agent_name})"
            for r in self._routes
        )

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are an intent classifier. Given a user message, "
                    "determine which agent should handle it.\n\n"
                    f"Available routes:\n{route_descriptions}\n\n"
                    f"Default: {self._default_agent}\n\n"
                    "Respond with ONLY the agent name, nothing else."
                ),
            },
            {"role": "user", "content": text},
        ]

        try:
            response = await self._llm.chat_completion_async(
                messages=messages,
                temperature=0.0,
                max_tokens=20,
            )
            agent_name = self._default_agent
            content = response["choices"][0]["message"]["content"]
            if content is not None:
                agent_name = content.strip().lower()

            # Validate against known agents
            valid_agents = {r.agent_name for r in self._routes}
            valid_agents.add(self._default_agent)
            if agent_name in valid_agents:
                return agent_name
            logger.warning("Router LLM returned unknown agent: %s", agent_name)

        except Exception:
            logger.error("Router slow-path LLM call failed", exc_info=True)

        return None


# CJK Unicode ranges (Chinese, Japanese, Korean)
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u30ff\uac00-\ud7af]")


def _is_cjk_keyword(keyword: str) -> bool:
    """Return True if the keyword contains any CJK characters."""
    return bool(_CJK_RE.search(keyword))
