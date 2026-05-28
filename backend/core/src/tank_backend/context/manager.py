"""ContextManager — owns conversation context, compaction, and prompt assembly.

Receives a :class:`ResolvedConversation` from the caller (Brain) via
:meth:`set_conversation`. Never queries stores or knows about channels.
Persistence is delegated to the :class:`ConversationResolver`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import tiktoken

from ..config.models import ContextConfig
from ..config.parser import ConfigError
from ..users import is_guest
from .budget import ContextBudget, resolve_context_window
from .compaction_store import CompactionStore
from .compactor import Compactor
from .conversation import ConversationData
from .resolver import CompactionMode, ResolvedConversation

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UsageSnapshot:
    """Read-only snapshot of context-budget usage for the /api/context/usage endpoint."""

    tokens_used: int
    budget: int
    context_window: int
    fill_pct: float
    last_compaction_at: str | None
    ineffective_count: int
    compaction_passes: int
    conversation_id: str | None


class ContextManager:
    """Pure context engine for a single conversation.

    Architecture:
    - **ConversationData** — single message list, persisted via resolver
    - **PromptAssembler** — builds system prompts from files (cached)
    - **Summarizer** — summarizes old messages during compaction
    - **MemoryService** — recalls/stores user facts
    - **ContextBudget** — model-aware dynamic token budget

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
        media_store: Any = None,
        llm_capabilities: frozenset[str] | None = None,
        compaction_store: CompactionStore | None = None,
        messages_store: Any = None,
    ) -> None:
        self._app_config = app_config
        self._config = config or ContextConfig()
        self._bus = bus
        self._resolver = resolver
        self._media_store = media_store
        self._llm_capabilities = llm_capabilities or frozenset()
        self._compaction_store = compaction_store
        self._messages_store = messages_store
        self._conversation: ConversationData | None = None
        self._compaction_mode: CompactionMode = CompactionMode.DESTRUCTIVE
        self._channel_context_builder: Any = None
        self._memory_context: str = ""
        self._last_user: str = ""
        self._last_user_text: str = ""
        self._encoder = tiktoken.get_encoding("cl100k_base")

        # Anti-thrashing state
        self._compaction_passes: int = 0
        self._tokens_before_last_compaction: int = 0
        self._ineffective_count: int = 0
        self._last_compaction_at: str | None = None

        self._memory_facts: list[str] = []

        # Resolve dynamic budget from model metadata
        self._budget = self._resolve_budget()

        # Create dependencies
        self._memory_service = self._create_memory_service()
        self._summarizer = self._create_summarizer()
        self._preference_store = self._create_preference_store()
        self._preference_learner = self._create_preference_learner()
        self._flusher = self._create_flusher()
        self._attach_hybrid_search()

        # PromptAssembler lives here
        from ..prompts.assembler import PromptAssembler

        self._prompt_assembler = PromptAssembler(bus=bus, skill_provider=skill_provider)

        # Compactor encapsulates the 5-phase compaction algorithm.
        self._compactor = Compactor(
            budget=self._budget,
            config=self._config,
            encoder=self._encoder,
            compaction_store=self._compaction_store,
        )

    # ------------------------------------------------------------------
    # Budget resolution
    # ------------------------------------------------------------------

    def _resolve_budget(self) -> ContextBudget:
        """Resolve the dynamic token budget from model metadata and config.

        Resolution order:
        1. Explicit config override (``context.context_window``)
        2. Model name pattern matching (``MODEL_CONTEXT_DEFAULTS`` table)
        3. Fallback: 32,000 tokens

        API-based detection (``query_model_context_length``) is called
        asynchronously on first use and cached. The budget is recalculated
        when the API result arrives.
        """
        model = self._get_model_name()
        context_window = resolve_context_window(model, self._config.context_window)
        budget = ContextBudget(
            context_window=context_window,
            history_share=self._config.history_share,
            output_reserve=self._config.output_reserve,
            headroom=self._config.headroom,
        )
        # Apply hard cap if set (backward compat with max_history_tokens)
        budget = budget.with_history_cap(
            self._config.max_history_tokens if self._config.max_history_tokens > 0 else None
        )
        logger.info(
            "Context budget: window=%d, effective_history=%d (model=%s)",
            budget.context_window,
            budget.effective_history_tokens,
            model,
        )
        # Fire-and-forget API query to detect actual context window
        self._try_api_detect(model)
        return budget

    def _try_api_detect(self, model: str) -> None:
        """Background task: query provider API for actual context window."""
        try:
            profile = self._app_config.get_llm_profile("default")
        except (KeyError, ValueError, ConfigError, AttributeError):
            return

        from .budget import query_model_context_length

        async def _detect() -> None:
            result = await query_model_context_length(
                model, profile.base_url, profile.api_key
            )
            if result and result != self._budget.context_window:
                old_window = self._budget.context_window
                self._budget = ContextBudget(
                    context_window=result,
                    history_share=self._config.history_share,
                    output_reserve=self._config.output_reserve,
                    headroom=self._config.headroom,
                ).with_history_cap(
                    self._config.max_history_tokens
                    if self._config.max_history_tokens > 0
                    else None
                )
                # Compactor captured the old budget at construction; rebuild
                # so subsequent compactions use the API-detected one. The
                # attribute may not exist yet during the first synchronous
                # _resolve_budget call (which fires _try_api_detect before
                # the Compactor is built); guard for that.
                if hasattr(self, "_compactor"):
                    self._compactor = Compactor(
                        budget=self._budget,
                        config=self._config,
                        encoder=self._encoder,
                        compaction_store=self._compaction_store,
                    )
                logger.info(
                    "Context budget updated via API: %d→%d, "
                    "effective_history=%d (model=%s)",
                    old_window,
                    result,
                    self._budget.effective_history_tokens,
                    model,
                )

        # Schedule the API-detection coroutine on the running event
        # loop. Wrapped in try/except because ``ContextManager`` is
        # constructed synchronously from many code paths — including
        # test setup that runs between async tests, where the
        # pytest-asyncio loop has already been cleaned up. Without
        # this guard, ``asyncio.ensure_future`` raises ``RuntimeError:
        # no current event loop`` and crashes any test that builds a
        # ContextManager from sync setup. The detection is best-effort
        # anyway (the budget falls back to model-name pattern matching
        # if the API call never lands), so silently dropping the task
        # in no-loop environments is the right semantic.
        try:
            asyncio.ensure_future(_detect())
        except RuntimeError:
            # No running loop (sync init from test setup, CLI tools,
            # one-shot scripts). Skip the detection — the budget keeps
            # whatever ``_resolve_budget`` already produced.
            logger.debug(
                "ContextManager: no event loop for API context-window "
                "detection; using static budget for model=%s", model,
            )

    def _get_model_name(self) -> str:
        """Extract the model name from the default LLM profile."""
        try:
            profile = self._app_config.get_llm_profile("default")
            return profile.model
        except (KeyError, ValueError, ConfigError, AttributeError):
            return "unknown"

    @property
    def budget(self) -> ContextBudget:
        """Current dynamic token budget."""
        return self._budget

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

    def _create_flusher(self) -> Any:
        """Create MemoryFlusher when pre-compaction flush is enabled.

        Returns ``None`` when:
        - the feature is disabled via ``context.pre_compaction_flush``
        - neither memory nor preferences are available (nothing to flush to)
        - no usable LLM profile exists
        """
        if not self._config.pre_compaction_flush:
            return None
        if self._memory_service is None and self._preference_store is None:
            return None

        from ..llm.profile import create_llm_from_profile
        from ..memory.flush import MemoryFlusher

        # Reuse the cheap summarization profile when available; fall back
        # to default. Same precedence the preference learner uses.
        try:
            profile = self._app_config.get_llm_profile("summarization")
        except (KeyError, ValueError, ConfigError):
            try:
                profile = self._app_config.get_llm_profile("default")
            except (KeyError, ValueError, ConfigError):
                return None

        llm = create_llm_from_profile(profile)
        logger.info("Memory flusher initialised (model=%s)", profile.model)
        return MemoryFlusher(
            llm=llm,
            memory=self._memory_service,
            preferences=self._preference_store,
        )

    def _attach_hybrid_search(self) -> None:
        """Wire :class:`HybridSearch` into ``MemoryService.recall``.

        No-op when either side is missing — recall falls back to
        vector-only (existing behaviour).
        """
        if self._memory_service is None:
            return
        if self._messages_store is None:
            return
        from ..memory.search import HybridSearch

        hybrid = HybridSearch(
            memory=self._memory_service,
            messages_store=self._messages_store,
        )
        self._memory_service.attach_hybrid_search(hybrid)
        logger.info("Hybrid memory recall enabled (vector + FTS5 keyword)")

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
                max_tokens=self._budget.effective_history_tokens,
                keep_recent=self._config.keep_recent_messages,
                summarizer=self._summarizer,
            )

    def assemble_system_prompt(self) -> str:
        """Assemble the current system prompt. Used by resolver for lifecycle."""
        return self._prompt_assembler.assemble()

    def _require_conversation(self) -> ConversationData:
        """Return ``self._conversation`` narrowed to non-None.

        Most ContextManager methods are only valid after
        :meth:`set_conversation` has been called — Brain enforces
        that ordering at runtime. This helper documents the
        precondition and gives pyright a single narrowing site
        rather than one assert per access. Raising here on misuse
        is loud-and-actionable; a silent ``None`` would surface as
        an obscure ``AttributeError`` halfway through a turn.
        """
        if self._conversation is None:
            raise RuntimeError(
                "ContextManager: no conversation loaded; "
                "call set_conversation() first",
            )
        return self._conversation

    def close(self) -> None:
        """Persist and release resources."""
        if self._conversation is not None:
            self._persist()

    # ------------------------------------------------------------------
    # Turn preparation — the key API for Brain
    # ------------------------------------------------------------------

    def _build_augmented_system_prompt(self, base: str, user: str) -> str:
        """Append USER.md, memory and preference sections to ``base``.

        Sections (in order, each only when non-empty):
        - ``USER.md`` content (per-user override or default; sanitized)
        - ``KNOWN FACTS ({user})`` — flat memory pool from MemoryService
        - ``USER PREFERENCES ({user})`` — PreferenceStore output

        These three are the **volatile** tier of the system prompt — they
        change every turn (memory recall) or when the user edits USER.md.
        Keeping them out of the assembler-cached prompt maximises
        prompt-prefix cache hits at the LLM provider.

        Guests get no augmentation. The block is rebuilt on every turn
        because memory recall is per-turn — caching here would risk
        showing stale facts when the user pivots topics.
        """
        if is_guest(user):
            return base
        out = base
        user_md = self._prompt_assembler.load_user_md()
        if user_md:
            out += f"\n\n{user_md}"
        if self._memory_facts:
            rendered = "\n".join(f"- {m}" for m in self._memory_facts)
            out += f"\n\nKNOWN FACTS ({user}):\n{rendered}"
        if self._preference_store:
            prefs = self._preference_store.render_for_user(user)
            if prefs:
                out += f"\n\nUSER PREFERENCES ({user}):\n{prefs}"
        return out

    async def recall_memory(self, user: str, text: str) -> None:
        """Pre-fetch memory for the upcoming turn.

        Issues a single semantic-search call against the flat memory
        pool. mem0 already does the relevance ranking, so there's no
        per-tier filtering to do here.
        """
        self._memory_context = ""
        self._memory_facts = []
        if self._memory_service is None or is_guest(user):
            return

        try:
            self._memory_facts = await self._memory_service.recall(user, text)
        except Exception:
            logger.warning(
                "Memory recall failed for user %s", user, exc_info=True,
            )
            return

        # Legacy mirror: keep ``_memory_context`` populated for any
        # callers still reading the field directly.
        if self._memory_facts:
            self._memory_context = "\n".join(f"- {m}" for m in self._memory_facts)

    async def prepare_turn(
        self,
        user: str,
        text: str,
        *,
        attachments: list[Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Prepare messages for an LLM call.

        1. Add user message to conversation (persists)
        2. Rebuild system prompt in-memory if needed
        3. Augment with memory context (temporary, not persisted)
        4. Pre-turn compaction check (if enabled and over budget)
        5. Return a copy of messages for the LLM
           - For channel conversations: derived context via ChannelContextBuilder
           - For regular conversations: raw conversation messages

        When ``attachments`` is provided, the returned user message
        carries them as OpenAI content parts alongside the text. The
        persisted message stores only the text — the media URIs are
        reachable via the session's MediaStore, so we don't duplicate
        them into the conversation JSON.
        """
        self.add_message("user", text, name=user, attachments=attachments)

        # ``add_message`` ensures a conversation is loaded; narrow once
        # for the rest of this method so pyright stops re-flagging the
        # same Optional pattern at every access site.
        conv = self._require_conversation()

        # Track for preference learning
        self._last_user = user
        self._last_user_text = text

        # Rebuild system prompt if prompt assembler has new discoveries
        if self._prompt_assembler.needs_rebuild():
            new_prompt = self._prompt_assembler.assemble()
            conv.messages[0] = {"role": "system", "content": new_prompt}

        # Non-destructive compaction: derive context, preserve full history
        if (
            self._compaction_mode == CompactionMode.NON_DESTRUCTIVE
            and self._channel_context_builder is not None
        ):
            conv_messages = conv.messages[1:]
            base_system = (
                conv.messages[0]["content"]
                if conv.messages
                else ""
            )
            augmented_system = self._build_augmented_system_prompt(base_system, user)
            derived = await self._channel_context_builder.build(
                conv_messages,
                conv.id,
                augmented_system,
            )
            return derived

        # Pre-turn compaction: check before building the full message list
        if self._config.pre_turn_compact:
            estimated = self.count_tokens() * 1.2  # safety margin
            if estimated > self._budget.effective_history_tokens:
                await self.compact()

        # Build augmented system prompt (memory + preferences)
        messages = list(conv.messages)
        base_system = messages[0]["content"] if messages else ""
        augmented_system = self._build_augmented_system_prompt(base_system, user)

        # Destructive compaction: return full messages with augmented system prompt
        if augmented_system != messages[0]["content"]:
            messages[0] = {"role": "system", "content": augmented_system}

        if attachments:
            messages = await self._materialize_last_user_attachments(
                messages, text, attachments,
            )

        return messages

    async def _materialize_last_user_attachments(
        self,
        messages: list[dict[str, Any]],
        text: str,
        attachments: list[Any],
    ) -> list[dict[str, Any]]:
        """Replace the last user message's string content with OpenAI
        content parts that include the resolved attachment blocks.

        The persisted message in ``self._conversation.messages`` keeps
        its plain-text ``content`` and ``attachments`` metadata — only
        the list returned to the LLM gets the expanded shape. This way,
        token counting, compaction, and replay all continue to see
        string content, while the wire gets the multi-modal form.
        """
        from ..core.content import (
            TextBlock,
            block_from_dict,
            blocks_to_openai_parts,
        )

        # Normalise: attachments may arrive as dicts (persisted path) or
        # ContentBlocks (live path from router).
        blocks: list = []
        for a in attachments:
            if isinstance(a, dict):
                blocks.append(block_from_dict(a))
            else:
                blocks.append(a)

        # Materialize media:// URIs against the MediaStore so the wire
        # carries bytes the LLM can actually consume. Non-media sources
        # (data URLs, absolute paths) pass through. Capabilities drive
        # the waterfall for documents (native PDF vs page images vs text).
        if self._media_store is not None:
            materialized: list = []
            for b in blocks:
                materialized.append(
                    await self._media_store.materialize_for_llm(
                        b, capabilities=self._llm_capabilities,
                    )
                )
            blocks = materialized

        # Compose the new user content: the user's text prefix, then
        # the attachment blocks in order.
        full_blocks = [TextBlock(text=text), *blocks]
        parts = blocks_to_openai_parts(full_blocks)

        # Walk backwards to find the last user message (the one we just
        # appended in prepare_turn) and swap its content.
        out = list(messages)
        for i in range(len(out) - 1, -1, -1):
            if out[i].get("role") == "user":
                new_msg = {**out[i], "content": parts}
                out[i] = new_msg
                break
        return out

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
            return self._build_augmented_system_prompt(new_prompt, user)

        return _refresh

    def finish_turn(self, turn_messages: list[dict[str, Any]]) -> None:
        """Append turn messages (tool calls, results, final response) and persist."""
        conv = self._require_conversation()
        conv.messages.extend(turn_messages)
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
                asyncio.ensure_future(
                    self._preference_learner.analyze_turn(
                        self._last_user, self._last_user_text, assistant_text,
                    )
                )

    # ------------------------------------------------------------------
    # Compaction — delegates to :class:`Compactor`
    # ------------------------------------------------------------------

    async def compact(self, focus: str | None = None) -> None:
        """Compact conversation if over token budget.

        Delegates to :class:`Compactor`, which runs the 5-phase algorithm:
        prune → protect tail → summarize → sanitize → truncate fallback.
        After the compactor mutates the conversation, the manager applies
        the returned counters and persists once.

        When ``focus`` is set (user-initiated ``/compact <topic>``), the
        anti-thrashing guards are bypassed and the focus is forwarded to
        the summarizer.
        """
        if self._compaction_mode == CompactionMode.NON_DESTRUCTIVE:
            return

        conv = self._require_conversation()
        result = await self._compactor.compact(
            conversation=conv,
            last_user=self._last_user,
            focus=focus,
            compaction_passes=self._compaction_passes,
            ineffective_count=self._ineffective_count,
            tokens_before_last_compaction=self._tokens_before_last_compaction,
            summarizer=self._summarizer,
            flusher=self._flusher,
        )

        # Apply absolute counter values returned by the compactor.
        self._compaction_passes = result.new_compaction_passes
        self._ineffective_count = result.new_ineffective_count
        self._tokens_before_last_compaction = (
            result.new_tokens_before_last_compaction
        )
        if result.last_compaction_at is not None:
            self._last_compaction_at = result.last_compaction_at

        if result.persisted_changes:
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
                await self._memory_service.store_turn(
                    user_id, user_msg, assistant_msg,
                )
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
        self,
        role: str,
        content: str,
        *,
        name: str | None = None,
        attachments: list[Any] | None = None,
    ) -> None:
        """Append a message and persist immediately.

        ``attachments`` (list of ContentBlock) is persisted on the message
        under the ``attachments`` key so replay can re-materialize the
        same multi-modal context. The ``content`` field stays as the text
        summary for token-counting and compaction — the expansion to
        OpenAI content-parts happens at wire time in
        :meth:`_apply_attachments_to_last_user`.
        """
        msg: dict[str, Any] = {"role": role, "content": content}
        if name:
            msg["name"] = name
        if attachments:
            from ..core.content import block_to_dict
            msg["attachments"] = [block_to_dict(b) for b in attachments]
        self._require_conversation().messages.append(msg)
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
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self) -> None:
        """Save current conversation via resolver, and mirror messages to FTS."""
        if self._resolver is None or self._conversation is None:
            return
        self._resolver.save(self._conversation)
        if self._messages_store is not None:
            try:
                self._messages_store.replace_for_conversation(
                    self._conversation.id, self._conversation.messages,
                )
            except Exception:
                logger.debug(
                    "Failed to mirror conversation messages to FTS index",
                    exc_info=True,
                )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def conversation_id(self) -> str | None:
        return self._conversation.id if self._conversation else None

    @property
    def conversation(self) -> ConversationData | None:
        """Current ConversationData, or ``None`` before set_conversation()."""
        return self._conversation

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

    def usage_snapshot(self) -> UsageSnapshot:
        """Return a read-only view of the current context-budget usage."""
        budget = self._budget.effective_history_tokens
        tokens_used = self.count_tokens()
        fill_pct = (tokens_used / budget) if budget > 0 else 0.0
        return UsageSnapshot(
            tokens_used=tokens_used,
            budget=budget,
            context_window=self._budget.context_window,
            fill_pct=fill_pct,
            last_compaction_at=self._last_compaction_at,
            ineffective_count=self._ineffective_count,
            compaction_passes=self._compaction_passes,
            conversation_id=self.conversation_id,
        )

    async def gather_memory_snapshot(
        self, user: str,
    ) -> tuple[list[str], list[str], list[str]]:
        """Aggregate stored memory for an introspection query.

        Returns ``(pinned, learned, facts)``:
        - ``pinned`` / ``learned`` come from the file-backed PreferenceStore.
        - ``facts`` is the full mem0 fact set for the user (single flat pool).

        Used by the system-intent handler to answer "what do you remember
        about me?" without an LLM round-trip. Guest users get empty data.
        """
        pinned: list[str] = []
        learned: list[str] = []
        if self._preference_store is not None:
            pinned = self._preference_store.list_pinned(user)
            all_entries = self._preference_store.list_for_user(user)
            learned = [e for e in all_entries if e not in pinned]

        facts: list[str] = []
        if self._memory_service is None or is_guest(user):
            return pinned, learned, facts

        try:
            facts = await self._memory_service.get_all(user)
        except Exception:
            logger.warning(
                "Memory snapshot failed for user %s", user, exc_info=True,
            )
            facts = []
        return pinned, learned, facts

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
