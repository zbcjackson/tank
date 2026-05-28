"""Compactor — the 5-phase compaction algorithm extracted from ContextManager.

Compaction is invoked by :class:`ContextManager` when the conversation exceeds
its token budget (or when the user manually invokes ``/compact``).  The
algorithm is intentionally split into phases so the cheap, deterministic steps
(pruning, sanitization, truncation) can succeed even when the expensive,
LLM-driven step (summarization) fails.

Phases:

1. **Prune** oversized / duplicate tool results in place (cheap; no LLM).
2. **Protect tail** — keep the most recent ``tail_budget`` of tokens verbatim.
3. **Summarize** everything before the tail (best-effort; may call the LLM).
4. **Sanitize** tool_call ↔ tool_result pairings (drop orphaned tool results).
5. **Truncate** as a fallback when summarization fails.

The :class:`Compactor` is stateless between calls — the anti-thrashing counters
that drive "skip if recent attempts were ineffective" live on
:class:`ContextManager` and are passed in via parameters and returned via
:class:`CompactionResult`.  This keeps ``usage_snapshot()`` and other read
paths on the manager untouched while the compaction body lives here.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import tiktoken

from ..config.models import ContextConfig
from .budget import ContextBudget
from .compaction_store import CompactionStore
from .compactions import CompactionRecord
from .conversation import ConversationData, Summarizer

if TYPE_CHECKING:
    from ..memory.flush import MemoryFlusher

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CompactionResult:
    """Outcome of a single :meth:`Compactor.compact` call.

    The manager applies these fields to its own state and decides whether to
    persist.  All counters are *absolute* values the manager should adopt —
    not deltas — so the manager doesn't need to know how thrashing works.

    Attributes:
        persisted_changes: ``True`` when the conversation was mutated and the
            caller should persist it.  ``False`` for no-ops (under budget,
            skipped due to anti-thrashing).
        tokens_before: Token count before compaction ran, or ``0`` for no-ops.
        tokens_after: Token count after compaction, or the unchanged count
            for no-ops.
        compacted_count: Number of source messages folded into the summary.
            ``0`` when the path didn't produce a summary (e.g. truncation,
            no-op).
        last_compaction_at: ISO-8601 timestamp of this run, or ``None`` for
            no-ops.  The manager assigns this to its public
            ``_last_compaction_at`` field.
        new_compaction_passes: Absolute session-level pass counter the
            manager should adopt.
        new_ineffective_count: Absolute thrashing counter the manager should
            adopt.
        new_tokens_before_last_compaction: Absolute "tokens before last
            compaction" value the manager should adopt; consumed by the next
            call's thrashing calculation.
    """

    persisted_changes: bool
    tokens_before: int
    tokens_after: int
    compacted_count: int
    last_compaction_at: str | None
    new_compaction_passes: int
    new_ineffective_count: int
    new_tokens_before_last_compaction: int


class Compactor:
    """Stateless 5-phase compaction engine.

    One instance per :class:`ContextManager`; reused for every ``compact``
    call.  All caller state (conversation, anti-thrashing counters) is passed
    in per call so the same compactor can be invoked on different
    conversations without leaking state.
    """

    def __init__(
        self,
        *,
        budget: ContextBudget,
        config: ContextConfig,
        encoder: tiktoken.Encoding,
        compaction_store: CompactionStore | None,
    ) -> None:
        self._budget = budget
        self._config = config
        self._encoder = encoder
        self._compaction_store = compaction_store

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def compact(
        self,
        *,
        conversation: ConversationData,
        last_user: str,
        focus: str | None,
        compaction_passes: int,
        ineffective_count: int,
        tokens_before_last_compaction: int,
        summarizer: Summarizer | None,
        flusher: MemoryFlusher | None,
    ) -> CompactionResult:
        """Run compaction against ``conversation`` and return what happened.

        ``summarizer`` and ``flusher`` are passed in per-call so the manager
        can swap them out (notably in tests) without rebuilding the
        compactor.  Both are optional — when ``summarizer`` is ``None`` the
        algorithm short-circuits to truncation; when ``flusher`` is ``None``
        the pre-compaction memory flush is skipped.

        The caller is responsible for guarding against
        :class:`CompactionMode.NON_DESTRUCTIVE`; this method always assumes
        it is allowed to mutate ``conversation.messages`` in place.

        ``focus`` overrides the under-budget and anti-thrashing guards (the
        user has explicitly asked for compaction with a topic in mind).

        ``compaction_passes`` / ``ineffective_count`` /
        ``tokens_before_last_compaction`` are passed in by the manager so
        the compactor can read them; the new values it computes are
        returned in :class:`CompactionResult` for the manager to adopt.
        """
        forced = focus is not None

        # Anti-thrashing pre-checks (manager-owned counters drive these but the
        # decision lives next to the algorithm that produced them).
        if not forced:
            if ineffective_count >= 2:
                logger.debug(
                    "Compaction skipped: anti-thrashing guard (%d ineffective)",
                    ineffective_count,
                )
                return _noop_result(
                    compaction_passes=compaction_passes,
                    ineffective_count=ineffective_count,
                    tokens_before_last=tokens_before_last_compaction,
                    tokens_now=self.count_tokens(conversation.messages),
                )
            if compaction_passes >= self._config.max_compaction_passes:
                logger.debug(
                    "Compaction skipped: max passes reached (%d)",
                    compaction_passes,
                )
                return _noop_result(
                    compaction_passes=compaction_passes,
                    ineffective_count=ineffective_count,
                    tokens_before_last=tokens_before_last_compaction,
                    tokens_now=self.count_tokens(conversation.messages),
                )

        budget = self._budget.effective_history_tokens
        total = self.count_tokens(conversation.messages)
        if not forced and total <= budget:
            return _noop_result(
                compaction_passes=compaction_passes,
                ineffective_count=ineffective_count,
                tokens_before_last=tokens_before_last_compaction,
                tokens_now=total,
            )

        # Begin work — update local copies of the counters as we go.
        new_passes = compaction_passes + 1
        new_tokens_before = total
        last_at = datetime.now(timezone.utc).isoformat()

        # Phase 1: Prune oversized tool results
        self._prune_tool_results(conversation, budget)
        total = self.count_tokens(conversation.messages)
        if not forced and total <= budget:
            new_ineffective = self._compute_ineffective(
                ineffective_count=ineffective_count,
                tokens_before=new_tokens_before,
                tokens_after=total,
            )
            return CompactionResult(
                persisted_changes=True,
                tokens_before=new_tokens_before,
                tokens_after=total,
                compacted_count=0,
                last_compaction_at=last_at,
                new_compaction_passes=new_passes,
                new_ineffective_count=new_ineffective,
                new_tokens_before_last_compaction=new_tokens_before,
            )

        # Phase 2: Split into to_summarize / tail
        system_msg = conversation.messages[0]
        rest = conversation.messages[1:]
        tail: list[dict[str, Any]]

        if forced:
            # User-triggered compaction with focus: pin the tail to the last
            # ``keep_recent_messages`` so the summarizer always has prior
            # turns to compress.
            keep = max(self._config.keep_recent_messages, 1)
            tail = rest[-keep:] if len(rest) >= keep else list(rest)
        else:
            tail_budget = self._budget.tail_budget
            tail = []
            tail_tokens = 0
            for msg in reversed(rest):
                msg_tokens = self.count_tokens([msg])
                if tail and tail_tokens + msg_tokens > tail_budget * 1.5:
                    break  # allow 1.5x overshoot to avoid splitting mid-message
                tail.append(msg)
                tail_tokens += msg_tokens
                if tail_tokens >= tail_budget:
                    break
            tail.reverse()

            # Hard minimum: always keep last 3 messages
            if len(tail) < 3 and len(rest) >= 3:
                tail = rest[-3:]

        tail_start = len(rest) - len(tail)
        to_summarize = rest[:tail_start]

        if not to_summarize:
            self._truncate(conversation, budget)
            tokens_after = self.count_tokens(conversation.messages)
            new_ineffective = self._compute_ineffective(
                ineffective_count=ineffective_count,
                tokens_before=new_tokens_before,
                tokens_after=tokens_after,
            )
            return CompactionResult(
                persisted_changes=True,
                tokens_before=new_tokens_before,
                tokens_after=tokens_after,
                compacted_count=0,
                last_compaction_at=last_at,
                new_compaction_passes=new_passes,
                new_ineffective_count=new_ineffective,
                new_tokens_before_last_compaction=new_tokens_before,
            )

        # Pre-compaction flush: persist durable facts before summarization
        # compresses them away.  Best-effort; failure must not block.
        if flusher is not None and last_user:
            try:
                await flusher.flush(
                    user=last_user, messages=to_summarize,
                )
            except Exception:
                logger.warning(
                    "Pre-compaction flush failed", exc_info=True,
                )

        # Phase 3: Summarize
        previous_summary = self._extract_previous_summary(to_summarize)
        if summarizer is not None:
            try:
                summary_text = await summarizer.summarize(
                    to_summarize,
                    previous_summary=previous_summary,
                    focus=focus,
                )
                summary_msg: dict[str, Any] = {
                    "role": "system",
                    "content": f"Previous conversation summary:\n{summary_text}",
                    "metadata": {
                        "type": "compaction_summary",
                        "compacted_count": len(to_summarize),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }
                pre_compaction_messages = list(to_summarize)
                conversation.messages = [system_msg, summary_msg] + tail
                # Phase 4: Sanitize tool pairs
                self._sanitize_tool_pairs(conversation)
                tokens_after = self.count_tokens(conversation.messages)
                self._record_compaction(
                    conv=conversation,
                    focus=focus,
                    tokens_before=new_tokens_before,
                    tokens_after=tokens_after,
                    summary_text=summary_text,
                    pre_compaction_messages=pre_compaction_messages,
                )
                new_ineffective = self._compute_ineffective(
                    ineffective_count=ineffective_count,
                    tokens_before=new_tokens_before,
                    tokens_after=tokens_after,
                )
                logger.info(
                    "Context compacted: %d msgs → summary + tail(%d), "
                    "%d→%d tokens",
                    len(to_summarize),
                    len(tail),
                    new_tokens_before,
                    tokens_after,
                )
                return CompactionResult(
                    persisted_changes=True,
                    tokens_before=new_tokens_before,
                    tokens_after=tokens_after,
                    compacted_count=len(to_summarize),
                    last_compaction_at=last_at,
                    new_compaction_passes=new_passes,
                    new_ineffective_count=new_ineffective,
                    new_tokens_before_last_compaction=new_tokens_before,
                )
            except Exception:
                logger.warning(
                    "Summarization failed, falling back to truncation",
                    exc_info=True,
                )

        # Phase 5: Fallback truncation (tail from Phase 2 is preserved)
        self._truncate(conversation, budget)
        self._sanitize_tool_pairs(conversation)
        tokens_after = self.count_tokens(conversation.messages)
        new_ineffective = self._compute_ineffective(
            ineffective_count=ineffective_count,
            tokens_before=new_tokens_before,
            tokens_after=tokens_after,
        )
        return CompactionResult(
            persisted_changes=True,
            tokens_before=new_tokens_before,
            tokens_after=tokens_after,
            compacted_count=0,
            last_compaction_at=last_at,
            new_compaction_passes=new_passes,
            new_ineffective_count=new_ineffective,
            new_tokens_before_last_compaction=new_tokens_before,
        )

    # ------------------------------------------------------------------
    # Token counting
    # ------------------------------------------------------------------

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Estimate token count for ``messages`` using the shared encoder."""
        total = 0
        for msg in messages:
            total += 4  # ~4 tokens overhead per message
            content = msg.get("content") or ""
            if isinstance(content, str):
                total += len(self._encoder.encode(content))
            for tc in msg.get("tool_calls", []):
                fn = tc.get("function", {})
                total += len(self._encoder.encode(fn.get("name", "")))
                total += len(self._encoder.encode(fn.get("arguments", "")))
                total += 4  # tool call structure overhead
        return total

    # ------------------------------------------------------------------
    # Phase helpers (formerly private methods of ContextManager)
    # ------------------------------------------------------------------

    def _prune_tool_results(self, conv: ConversationData, budget: int) -> int:
        """Phase 1: Prune oversized tool results in-place.

        Replaces tool result messages exceeding the per-result token limit
        with a 1-line summary.  Returns the number of messages pruned (used
        only for logging).
        """
        del budget  # the cap comes from self._budget.max_tool_result_tokens
        max_per_result = self._budget.max_tool_result_tokens
        pruned = 0
        seen_content: dict[str, int] = {}

        for msg in conv.messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "tool" and content:
                content_hash = content[:200]
                seen_content[content_hash] = seen_content.get(content_hash, 0) + 1
                if seen_content[content_hash] > 1:
                    msg["content"] = "[Duplicate tool result omitted]"
                    pruned += 1
                    continue

            if role == "tool" and isinstance(content, str):
                tokens = self.count_tokens([msg])
                if tokens > max_per_result:
                    tool_name = msg.get("name", "tool")
                    truncated = content[:100].replace("\n", " ")
                    msg["content"] = (
                        f"[{tool_name}] {truncated}..."
                        f" (truncated, was {tokens} tokens)"
                    )
                    pruned += 1

        if pruned:
            logger.debug("Phase 1: pruned %d oversized/duplicate tool results", pruned)
        return pruned

    @staticmethod
    def _extract_previous_summary(
        messages: list[dict[str, Any]],
    ) -> str | None:
        """Find an existing compaction summary in ``messages`` for incremental update."""
        for msg in messages:
            metadata = msg.get("metadata", {})
            if isinstance(metadata, dict) and metadata.get("type") == "compaction_summary":
                content = msg.get("content", "")
                if content.startswith("Previous conversation summary:\n"):
                    return content[len("Previous conversation summary:\n"):]
                if content.startswith("Previous conversation summary: "):
                    return content[len("Previous conversation summary: "):]
                return content
        return None

    @staticmethod
    def _sanitize_tool_pairs(conv: ConversationData) -> None:
        """Phase 4: Remove tool results that lost their matching tool_call."""
        messages = conv.messages
        tool_call_ids: set[str] = set()
        tool_result_ids: set[str] = set()

        for msg in messages:
            for tc in msg.get("tool_calls", []):
                tc_id = tc.get("id")
                if tc_id:
                    tool_call_ids.add(tc_id)
            if msg.get("role") == "tool":
                tool_id = msg.get("tool_call_id")
                if tool_id:
                    tool_result_ids.add(tool_id)

        orphan_results = tool_result_ids - tool_call_ids
        if orphan_results:
            conv.messages = [
                msg for msg in messages
                if msg.get("role") != "tool"
                or msg.get("tool_call_id") not in orphan_results
            ]
            logger.debug(
                "Phase 4: removed %d orphaned tool results", len(orphan_results),
            )

    @staticmethod
    def _compute_ineffective(
        *,
        ineffective_count: int,
        tokens_before: int,
        tokens_after: int,
    ) -> int:
        """Return the new ineffective-counter value for the next call."""
        if tokens_before <= 0:
            return ineffective_count
        savings_ratio = 1.0 - (tokens_after / tokens_before)
        if savings_ratio < 0.10:
            new_value = ineffective_count + 1
            logger.debug(
                "Ineffective compaction (%.0f%% savings, count=%d)",
                savings_ratio * 100,
                new_value,
            )
            return new_value
        return 0

    def _record_compaction(
        self,
        *,
        conv: ConversationData,
        focus: str | None,
        tokens_before: int,
        tokens_after: int,
        summary_text: str,
        pre_compaction_messages: list[dict[str, Any]],
    ) -> None:
        """Persist a :class:`CompactionRecord`.  Failure is non-fatal."""
        if self._compaction_store is None:
            return
        try:
            parent = self._compaction_store.latest_for_conversation(conv.id)
            self._compaction_store.save(CompactionRecord(
                id=uuid.uuid4().hex,
                conversation_id=conv.id,
                parent_id=parent.id if parent else None,
                created_at=datetime.now(timezone.utc),
                focus=focus,
                tokens_before=tokens_before,
                tokens_after=tokens_after,
                compacted_count=len(pre_compaction_messages),
                summary_text=summary_text,
                pre_compaction_messages=pre_compaction_messages,
            ))
        except Exception:
            logger.warning("Failed to persist compaction lineage", exc_info=True)

    def _truncate(self, conv: ConversationData, budget: int) -> None:
        """Phase 5 fallback: drop oldest non-system messages to fit ``budget``."""
        system_msg = conv.messages[0]
        rest = conv.messages[1:]

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

        old_count = len(conv.messages)
        conv.messages = [system_msg] + rest[keep_from:]
        logger.info(
            "Context truncated: %d → %d messages",
            old_count,
            len(conv.messages),
        )


def _noop_result(
    *,
    compaction_passes: int,
    ineffective_count: int,
    tokens_before_last: int,
    tokens_now: int,
) -> CompactionResult:
    """Build a :class:`CompactionResult` for a path that didn't mutate state."""
    return CompactionResult(
        persisted_changes=False,
        tokens_before=0,
        tokens_after=tokens_now,
        compacted_count=0,
        last_compaction_at=None,
        new_compaction_passes=compaction_passes,
        new_ineffective_count=ineffective_count,
        new_tokens_before_last_compaction=tokens_before_last,
    )
