"""ContextManager — owns conversation context, compaction, and prompt assembly.

Receives a :class:`ResolvedConversation` from the caller (Brain) via
:meth:`set_conversation`. Never queries stores or knows about channels.
Persistence is delegated to the :class:`ConversationResolver`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import tiktoken

from ..config.models import ContextConfig
from ..config.parser import ConfigError
from ..users import is_guest
from .conversation import ConversationData
from .resolver import CompactionMode, ResolvedConversation

logger = logging.getLogger(__name__)


class ContextManager:
    """Pure context engine for a single conversation.

    Architecture:
    - **ConversationData** — single message list, persisted via resolver
    - **PromptAssembler** — builds system prompts from files (cached)
    - **Summarizer** — summarizes old messages during compaction
    - **MemoryService** — recalls/stores user facts

    Brain interacts through :meth:`set_conversation`, :meth:`prepare_turn`,
    :meth:`finish_turn`, :meth:`recall_memory`, and :meth:`compact`.
    """

    def __init__(
        self,
        app_config: Any,
        resolver: Any = None,
        bus: Any = None,
        config: ContextConfig | None = None,
        skill_provider: Any = None,
    ) -> None:
        self._app_config = app_config
        self._config = config or ContextConfig()
        self._bus = bus
        self._resolver = resolver
        self._conversation: ConversationData | None = None
        self._compaction_mode: CompactionMode = CompactionMode.DESTRUCTIVE
        self._channel_context_builder: Any = None
        self._memory_context: str = ""
        self._last_user: str = ""
        self._last_user_text: str = ""
        self._encoder = tiktoken.get_encoding("cl100k_base")

        # Create dependencies
        self._memory_service = self._create_memory_service()
        self._summarizer = self._create_summarizer()
        self._preference_store = self._create_preference_store()
        self._preference_learner = self._create_preference_learner()

        # PromptAssembler lives here
        from ..prompts.assembler import PromptAssembler

        self._prompt_assembler = PromptAssembler(bus=bus, skill_provider=skill_provider)

    # ------------------------------------------------------------------
    # Dependency factories
    # ------------------------------------------------------------------

    def _create_memory_service(self) -> Any:
        """Create MemoryService from config, or ``None`` if disabled."""
        from ..memory import MemoryConfig, MemoryService

        mem_cfg = self._app_config.memory
        if not mem_cfg.enabled:
            return None

        try:
            profile = self._app_config.get_llm_profile("default")
        except (KeyError, ValueError, ConfigError):
            logger.warning("No default LLM profile — memory service disabled")
            return None

        resolved = MemoryConfig(
            enabled=True,
            db_path=mem_cfg.db_path,
            llm_api_key=mem_cfg.llm_api_key or profile.api_key,
            llm_base_url=mem_cfg.llm_base_url or profile.base_url,
            llm_model=mem_cfg.llm_model or "",
            embedding_api_key=mem_cfg.embedding_api_key or "",
            embedding_base_url=mem_cfg.embedding_base_url or "",
            embedding_model=mem_cfg.embedding_model or "",
            search_limit=mem_cfg.search_limit,
        )
        try:
            svc = MemoryService(resolved)
            logger.info("Memory service initialised (db_path=%s)", resolved.db_path)
            return svc
        except Exception:
            logger.warning("Failed to init memory service", exc_info=True)
            return None

    def _create_summarizer(self) -> Any:
        """Create LLMSummarizer using 'summarization' profile, fallback to 'default'."""
        from ..llm.profile import create_llm_from_profile
        from .summarizer import LLMSummarizer

        try:
            profile = self._app_config.get_llm_profile("summarization")
        except (KeyError, ValueError, ConfigError):
            try:
                profile = self._app_config.get_llm_profile("default")
            except (KeyError, ValueError, ConfigError):
                return None
        llm = create_llm_from_profile(profile)
        return LLMSummarizer(llm, self._config)

    def _create_preference_store(self) -> Any:
        """Create PreferenceStore from config, or ``None`` if disabled."""
        from pathlib import Path

        from ..preferences import PreferenceStore

        prefs_cfg = self._app_config.preferences
        if not prefs_cfg.enabled:
            return None

        base_dir = Path(prefs_cfg.base_dir or "~/.tank").expanduser()
        store = PreferenceStore(base_dir, prefs_cfg.max_entries)
        logger.info("Preference store initialised (base_dir=%s)", base_dir)
        return store

    def _create_preference_learner(self) -> Any:
        """Create PreferenceLearner from config, or ``None`` if disabled."""
        if self._preference_store is None:
            return None

        prefs_cfg = self._app_config.preferences
        if not prefs_cfg.auto_learn:
            return None

        from ..llm.profile import create_llm_from_profile
        from ..preferences import PreferenceLearner

        # Try to use "summarization" profile for cheap extraction, fallback to default
        try:
            profile = self._app_config.get_llm_profile("summarization")
        except (KeyError, ValueError, ConfigError):
            try:
                profile = self._app_config.get_llm_profile("default")
            except (KeyError, ValueError, ConfigError):
                return None

        llm = create_llm_from_profile(profile)
        logger.info("Preference learner initialised (model=%s)", profile.model)
        return PreferenceLearner(self._preference_store, llm)

    # ------------------------------------------------------------------
    # Conversation loading
    # ------------------------------------------------------------------

    def set_conversation(self, resolved: ResolvedConversation) -> None:
        """Load a resolved conversation. Sets compaction strategy.

        Called by Brain after ConversationResolver decides which conversation
        to use and what compaction mode applies.
        """
        self._conversation = resolved.conversation
        self._compaction_mode = resolved.compaction_mode
        self._channel_context_builder = None
        self._memory_context = ""

        if resolved.compaction_mode == CompactionMode.NON_DESTRUCTIVE:
            from ..channels.context import ChannelContextBuilder

            self._channel_context_builder = ChannelContextBuilder(
                max_tokens=self._config.max_history_tokens,
                keep_recent=self._config.keep_recent_messages,
                summarizer=self._summarizer,
            )

    def assemble_system_prompt(self) -> str:
        """Assemble the current system prompt. Used by resolver for lifecycle."""
        return self._prompt_assembler.assemble()

    def close(self) -> None:
        """Persist and release resources."""
        if self._conversation is not None:
            self._persist()

    # ------------------------------------------------------------------
    # Turn preparation — the key API for Brain
    # ------------------------------------------------------------------

    async def recall_memory(self, user: str, text: str) -> None:
        """Pre-fetch memory for the upcoming turn."""
        self._memory_context = ""
        if self._memory_service is None or is_guest(user):
            return
        try:
            memories = await self._memory_service.recall(user, text)
            if memories:
                self._memory_context = "\n".join(f"- {m}" for m in memories)
        except Exception:
            logger.warning("Memory recall failed for user %s", user, exc_info=True)

    async def prepare_turn(
        self,
        user: str,
        text: str,
    ) -> list[dict[str, Any]]:
        """Prepare messages for an LLM call.

        1. Add user message to conversation (persists)
        2. Rebuild system prompt in-memory if needed
        3. Augment with memory context (temporary, not persisted)
        4. Return a copy of messages for the LLM
           - For channel conversations: derived context via ChannelContextBuilder
           - For regular conversations: raw conversation messages
        """
        self.add_message("user", text, name=user)

        # Track for preference learning
        self._last_user = user
        self._last_user_text = text

        # Rebuild system prompt if prompt assembler has new discoveries
        if self._prompt_assembler.needs_rebuild():
            new_prompt = self._prompt_assembler.assemble()
            self._conversation.messages[0] = {"role": "system", "content": new_prompt}

        # Build augmented system prompt (memory + preferences)
        messages = list(self._conversation.messages)
        augmented_system = messages[0]["content"] if messages else ""

        if not is_guest(user):
            if self._memory_context:
                augmented_system += (
                    f"\n\nKNOWN FACTS ABOUT {user}:\n{self._memory_context}"
                )
            if self._preference_store:
                prefs = self._preference_store.render_for_user(user)
                if prefs:
                    augmented_system += (
                        f"\n\nUSER PREFERENCES ({user}):\n{prefs}"
                    )

        # Non-destructive compaction: derive context, preserve full history
        if (
            self._compaction_mode == CompactionMode.NON_DESTRUCTIVE
            and self._channel_context_builder is not None
        ):
            conv_messages = self._conversation.messages[1:]
            derived = await self._channel_context_builder.build(
                conv_messages,
                self._conversation.id,
                augmented_system,
            )
            return derived

        # Destructive compaction: return full messages with augmented system prompt
        if augmented_system != messages[0]["content"]:
            messages[0] = {"role": "system", "content": augmented_system}

        return messages

    def get_system_prompt_refresher(self, user: str = "") -> Callable[[], str | None]:
        """Return a callback that refreshes the system prompt during LLM tool loops.

        Returns the fully-augmented prompt (with memory) when rebuild is needed,
        or None when the cached prompt is still valid (O(1) check).
        """

        def _refresh() -> str | None:
            if not self._prompt_assembler.needs_rebuild():
                return None
            new_prompt = self._prompt_assembler.assemble()
            # Update stored system prompt
            if (
                self._conversation
                and self._conversation.messages
                and self._conversation.messages[0].get("role") == "system"
            ):
                self._conversation.messages[0]["content"] = new_prompt
            # Re-apply memory + preference augmentation (skip for guests)
            if not is_guest(user):
                if self._memory_context:
                    new_prompt += (
                        f"\n\nKNOWN FACTS ABOUT {user}:\n{self._memory_context}"
                    )
                if self._preference_store:
                    prefs = self._preference_store.render_for_user(user)
                    if prefs:
                        new_prompt += f"\n\nUSER PREFERENCES ({user}):\n{prefs}"
            return new_prompt

        return _refresh

    def finish_turn(self, turn_messages: list[dict[str, Any]]) -> None:
        """Append turn messages (tool calls, results, final response) and persist."""
        self._conversation.messages.extend(turn_messages)
        self._persist()

        # Schedule preference learning (fire-and-forget, like memory)
        if (
            self._preference_learner
            and self._last_user
            and self._last_user_text
            and not is_guest(self._last_user)
        ):
            assistant_text = ""
            for msg in reversed(turn_messages):
                if msg.get("role") == "assistant" and msg.get("content"):
                    assistant_text = msg["content"]
                    break
            if assistant_text:
                import asyncio

                asyncio.ensure_future(
                    self._preference_learner.analyze_turn(
                        self._last_user, self._last_user_text, assistant_text,
                    )
                )

    async def compact(self) -> None:
        """Compact conversation if over token budget.

        For channel conversations: no-op (history is preserved, context is derived).
        For regular conversations: destructive — modifies messages in place.
        Strategy: summarize first (preserves context), fall back to truncation.
        """
        if self._compaction_mode == CompactionMode.NON_DESTRUCTIVE:
            return

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
                summary_msg: dict[str, Any] = {
                    "role": "system",
                    "content": f"Previous conversation summary: {summary_text}",
                    "metadata": {
                        "type": "compaction_summary",
                        "compacted_count": len(to_summarize),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }
                self._conversation.messages = [system_msg, summary_msg] + to_keep
                self._persist()
                logger.info(
                    "Context compacted: %d messages → summary + %d recent",
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

    def schedule_memory_store(
        self, user: str, user_text: str, assistant_response: str
    ) -> None:
        """Schedule background memory storage (fire-and-forget)."""
        if self._memory_service is None or is_guest(user):
            return
        asyncio.ensure_future(
            self._store_memory_with_retry(user, user_text, assistant_response)
        )

    async def _store_memory_with_retry(
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
            # Count tool calls
            for tc in msg.get("tool_calls", []):
                fn = tc.get("function", {})
                total += len(self._encoder.encode(fn.get("name", "")))
                total += len(self._encoder.encode(fn.get("arguments", "")))
                total += 4  # tool call structure overhead
        return total

    # ------------------------------------------------------------------
    # Compaction helpers
    # ------------------------------------------------------------------

    def _truncate(self, budget: int) -> None:
        """Drop oldest non-system messages to fit within token budget."""
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

        old_count = len(self._conversation.messages)
        self._conversation.messages = [system_msg] + rest[keep_from:]
        logger.info(
            "Context truncated: %d → %d messages",
            old_count,
            len(self._conversation.messages),
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self) -> None:
        """Save current conversation via resolver."""
        if self._resolver is None or self._conversation is None:
            return
        self._resolver.save(self._conversation)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def conversation_id(self) -> str | None:
        return self._conversation.id if self._conversation else None

    @property
    def session_id(self) -> str | None:
        return self.conversation_id

    @property
    def prompt_assembler(self) -> Any:
        return self._prompt_assembler

    @property
    def preference_store(self) -> Any:
        """PreferenceStore instance, or None if disabled."""
        return self._preference_store

    @property
    def pending_approvals(self) -> list[dict[str, Any]] | None:
        """Return persisted pending approvals from the current conversation."""
        if self._conversation is None:
            return None
        return self._conversation.pending_approvals

    @pending_approvals.setter
    def pending_approvals(self, value: list[dict[str, Any]] | None) -> None:
        """Set pending approvals on the current conversation (persisted on next save)."""
        if self._conversation is not None:
            self._conversation.pending_approvals = value
