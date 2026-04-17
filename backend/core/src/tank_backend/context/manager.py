"""ContextManager — owns conversation history, conversation lifecycle, and prompt assembly."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import tiktoken

from .config import ContextConfig
from .conversation import ConversationData, Summarizer
from .store import create_store

logger = logging.getLogger(__name__)


class ContextManager:
    """Central owner of conversation context.

    Owns: conversation lifecycle, message history, prompt assembly,
    memory recall/store, token counting, compaction, persistence.

    Brain interacts through :meth:`prepare_turn`, :meth:`finish_turn`,
    :meth:`recall_memory`, and :meth:`maybe_compact`.
    """

    def __init__(
        self,
        app_config: Any,
        bus: Any = None,
        config: ContextConfig | None = None,
        skill_provider: Any = None,
    ) -> None:
        self._app_config = app_config
        self._config = config or ContextConfig()
        self._bus = bus
        self._conversation: ConversationData | None = None
        self._memory_context: str = ""
        self._encoder = tiktoken.get_encoding("cl100k_base")

        # Create dependencies
        self._store = self._create_store()
        self._memory_service = self._create_memory_service()
        self._summarizer = self._create_summarizer()

        # PromptAssembler lives here
        from ..prompts.assembler import PromptAssembler

        self._prompt_assembler = PromptAssembler(bus=bus, skill_provider=skill_provider)

    # ------------------------------------------------------------------
    # Dependency factories
    # ------------------------------------------------------------------

    def _create_store(self) -> Any:
        return create_store(self._config.store_type, self._config.store_path)

    def _create_memory_service(self) -> Any:
        """Create MemoryService from config, or ``None`` if disabled."""
        from ..memory import MemoryConfig, MemoryService

        memory_raw = self._app_config.get_section("memory", {"enabled": False})
        memory_config = MemoryConfig.from_dict(memory_raw)
        if not memory_config.enabled:
            return None

        profile = self._app_config.get_llm_profile("default")
        resolved = MemoryConfig(
            enabled=True,
            db_path=memory_config.db_path,
            llm_api_key=memory_config.llm_api_key or profile.api_key,
            llm_base_url=memory_config.llm_base_url or profile.base_url,
            llm_model=memory_config.llm_model or "",
            search_limit=memory_config.search_limit,
        )
        try:
            svc = MemoryService(resolved)
            logger.info("Memory service initialised (db_path=%s)", resolved.db_path)
            return svc
        except Exception:
            logger.warning("Failed to init memory service", exc_info=True)
            return None

    def _create_summarizer(self) -> Summarizer | None:
        """Create LLMSummarizer using 'summarization' profile, fallback to 'default'."""
        from ..llm.profile import create_llm_from_profile
        from .summarizer import LLMSummarizer

        try:
            profile = self._app_config.get_llm_profile("summarization")
        except (KeyError, ValueError):
            try:
                profile = self._app_config.get_llm_profile("default")
            except (KeyError, ValueError):
                return None
        llm = create_llm_from_profile(profile)
        return LLMSummarizer(llm, self._config)

    # ------------------------------------------------------------------
    # Conversation lifecycle
    # ------------------------------------------------------------------

    def new_conversation(self) -> str:
        """Create a fresh conversation with assembled system prompt. Persists immediately."""
        system_prompt = self._prompt_assembler.assemble()
        self._conversation = ConversationData.new(system_prompt)
        self._persist()
        logger.info("New conversation created: %s", self._conversation.id)
        return self._conversation.id

    def resume_or_new(self) -> str:
        """Resume latest same-day conversation, or create new.

        This is the main entry point called from Brain.__init__.
        """
        if self._store is not None:
            latest = self._store.find_latest()
            if latest is not None:
                today = datetime.now(timezone.utc).date()
                if latest.start_time.date() == today:
                    self._conversation = latest
                    # Update system prompt to current assembled version
                    system_prompt = self._prompt_assembler.assemble()
                    if (
                        self._conversation.messages
                        and self._conversation.messages[0].get("role") == "system"
                    ):
                        self._conversation.messages[0]["content"] = system_prompt
                    logger.info(
                        "Resumed conversation %s (%d messages)",
                        latest.id,
                        len(latest.messages),
                    )
                    return self._conversation.id
        return self.new_conversation()

    def clear(self) -> str:
        """Clear context — old conversation stays persisted, creates new conversation."""
        return self.new_conversation()

    def resume_conversation(self, conversation_id: str) -> bool:
        """Resume a specific conversation by ID. Returns ``False`` if not found."""
        if self._store is None:
            return False
        conversation = self._store.load(conversation_id)
        if conversation is None:
            return False
        self._conversation = conversation
        return True

    # ------------------------------------------------------------------
    # Turn preparation — the key API for Brain
    # ------------------------------------------------------------------

    async def recall_memory(self, user: str, text: str) -> None:
        """Pre-fetch memory for the upcoming turn."""
        self._memory_context = ""
        if self._memory_service is None or not user or user == "Unknown":
            return
        try:
            memories = await self._memory_service.recall(user, text)
            if memories:
                self._memory_context = "\n".join(f"- {m}" for m in memories)
        except Exception:
            logger.warning("Memory recall failed for user %s", user, exc_info=True)

    def prepare_turn(
        self,
        user: str,
        text: str,
    ) -> list[dict[str, Any]]:
        """Prepare messages for an LLM call.

        1. Add user message to history (persists)
        2. Rebuild system prompt if needed
        3. Return a **copy** with augmented system prompt (memory)

        The augmented prompt is NOT persisted — stored messages keep the base prompt.
        """
        self.add_message("user", text, name=user)

        # Rebuild system prompt if prompt assembler has new discoveries
        if self._prompt_assembler.needs_rebuild():
            new_prompt = self._prompt_assembler.assemble()
            self._conversation.messages[0] = {"role": "system", "content": new_prompt}
            self._persist()

        # Build augmented system prompt (temporary, not persisted)
        base_system = self._conversation.messages[0]["content"]
        augmented = base_system

        if self._memory_context:
            augmented += f"\n\nKNOWN FACTS ABOUT {user}:\n{self._memory_context}"

        # Return copy with augmented prompt
        messages = list(self._conversation.messages)
        messages[0] = {"role": "system", "content": augmented}
        return messages

    def finish_turn(self, assistant_response: str) -> None:
        """Record assistant response. Persists immediately."""
        self.add_message("assistant", assistant_response)

    def schedule_memory_store(
        self, user: str, user_text: str, assistant_response: str
    ) -> None:
        """Fire-and-forget: extract and store facts from the turn."""
        if (
            self._memory_service is None
            or not user
            or user == "Unknown"
            or not user_text
        ):
            return
        asyncio.create_task(
            self._store_memory_safe(user, user_text, assistant_response)
        )

    async def _store_memory_safe(
        self, user_id: str, user_msg: str, assistant_msg: str
    ) -> None:
        """Store memory with retry — never crashes the pipeline."""
        for attempt in range(1, 4):
            try:
                await self._memory_service.store_turn(user_id, user_msg, assistant_msg)
                return
            except Exception:
                if attempt == 3:
                    logger.warning(
                        "Memory storage failed for user %s after %d attempts",
                        user_id,
                        attempt,
                        exc_info=True,
                    )
                else:
                    await asyncio.sleep(1.0 * attempt)

    # ------------------------------------------------------------------
    # Message management
    # ------------------------------------------------------------------

    @property
    def messages(self) -> list[dict[str, Any]]:
        """Current conversation messages."""
        if self._conversation is None:
            return []
        return self._conversation.messages

    def add_message(
        self, role: str, content: str, *, name: str | None = None
    ) -> None:
        """Append a message and persist immediately."""
        msg: dict[str, str] = {"role": role, "content": content}
        if name:
            msg["name"] = name
        self._conversation.messages.append(msg)
        self._persist()

    # ------------------------------------------------------------------
    # Compaction
    # ------------------------------------------------------------------

    async def maybe_compact(self) -> None:
        """Compact if token count exceeds budget.

        Strategy: summarize first (preserves context), fall back to
        truncation (drops oldest messages) if summarization fails.
        """
        total = self.count_tokens()
        budget = self._config.max_history_tokens
        if total <= budget:
            return

        system_msg = self._conversation.messages[0]
        rest = self._conversation.messages[1:]
        keep_n = self._config.keep_recent_messages

        if len(rest) <= keep_n:
            self._truncate(budget)
            self._persist()
            return

        to_summarize = rest[:-keep_n]
        to_keep = rest[-keep_n:]

        # Try summarization first
        if self._summarizer is not None:
            try:
                summary_text = await self._summarizer.summarize(to_summarize)
                summary_msg: dict[str, str] = {
                    "role": "system",
                    "content": f"Previous conversation summary: {summary_text}",
                }
                self._conversation.messages = [system_msg, summary_msg] + to_keep
                self._persist()
                logger.info(
                    "Context summarized: %d messages → summary + %d recent",
                    len(to_summarize),
                    keep_n,
                )
                return
            except Exception:
                logger.warning(
                    "Summarization failed, falling back to truncation",
                    exc_info=True,
                )

        self._truncate(budget)
        self._persist()

    def _truncate(self, budget: int) -> None:
        """Drop oldest non-system messages to fit within token budget."""
        total_tokens = self.count_tokens()
        if total_tokens <= budget:
            return

        system_msg = self._conversation.messages[0]
        rest = self._conversation.messages[1:]

        system_tokens = self.count_tokens([system_msg])
        remaining_budget = budget - system_tokens
        keep_from = len(rest)
        running = 0
        for i in range(len(rest) - 1, -1, -1):
            msg_tokens = self.count_tokens([rest[i]])
            if running + msg_tokens > remaining_budget:
                break
            running += msg_tokens
            keep_from = i

        self._conversation.messages = [system_msg] + rest[keep_from:]
        new_tokens = self.count_tokens()
        logger.info(
            "History truncated: %d → %d tokens (%d messages kept)",
            total_tokens,
            new_tokens,
            len(self._conversation.messages),
        )

    # ------------------------------------------------------------------
    # Token counting
    # ------------------------------------------------------------------

    def count_tokens(self, messages: list[dict[str, Any]] | None = None) -> int:
        """Estimate token count for messages (defaults to current conversation)."""
        msgs = messages if messages is not None else self.messages
        total = 0
        for msg in msgs:
            total += 4  # ~4 tokens overhead per message
            content = msg.get("content") or ""
            if isinstance(content, str):
                total += len(self._encoder.encode(content))
        return total

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self) -> None:
        """Save current conversation to store. Called after every mutation."""
        if self._store is None or self._conversation is None:
            return
        try:
            self._store.save(self._conversation)
        except Exception:
            logger.error(
                "Failed to persist conversation %s",
                self._conversation.id,
                exc_info=True,
            )

    def close(self) -> None:
        """Cleanup — close store connection."""
        if self._store is not None:
            self._store.close()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def conversation_id(self) -> str | None:
        """Current conversation ID, or ``None`` if no conversation active."""
        return self._conversation.id if self._conversation else None

    @property
    def prompt_assembler(self) -> Any:
        """Expose assembler for sub-agent prompt building (AgentRunner)."""
        return self._prompt_assembler
