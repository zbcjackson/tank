"""Tool-call loop guardrail primitives.

Tracks per-turn tool-call observations and returns decisions. The
controller is side-effect free: runtime code (in ``llm.py``) owns
whether decisions become warning guidance, synthetic tool results,
or tool-schema removal.

Detects three failure patterns:
1. **Exact repeat failure** — same tool + same args hash fails N times
2. **Same-tool failure** — same tool (any args) fails N times
3. **No-progress loop** — idempotent tool returns identical result hash
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config.models import ToolGuardrailsConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ToolCallSignature:
    """Identity of a tool call for deduplication."""

    tool_name: str
    args_hash: str

    @classmethod
    def from_call(cls, tool_name: str, args: str) -> ToolCallSignature:
        h = hashlib.sha256(args.encode()).hexdigest()[:16]
        return cls(tool_name=tool_name, args_hash=h)


@dataclass(frozen=True, slots=True)
class GuardrailDecision:
    """What the guardrail recommends for the current tool call."""

    action: str  # "allow" | "warn" | "block"
    reason: str = ""

    @property
    def should_warn(self) -> bool:
        return self.action == "warn"

    @property
    def should_block(self) -> bool:
        return self.action == "block"


_ALLOW = GuardrailDecision(action="allow")


class ToolCallGuardrailController:
    """Per-turn tool loop detector.

    Instantiate at the start of ``chat_stream()`` tool loop.
    Call :meth:`record_result` after each tool execution.
    """

    def __init__(self, config: ToolGuardrailsConfig | None = None) -> None:
        from ..config.models import ToolGuardrailsConfig as _Cfg

        self._cfg = config or _Cfg()
        # Exact signature → failure count
        self._exact_failures: dict[ToolCallSignature, int] = defaultdict(int)
        # Tool name → failure count (regardless of args)
        self._tool_failures: dict[str, int] = defaultdict(int)
        # Exact signature → last result hash (for no-progress detection)
        self._result_hashes: dict[ToolCallSignature, str] = {}
        # Exact signature → identical result count
        self._no_progress: dict[ToolCallSignature, int] = defaultdict(int)

    @property
    def enabled(self) -> bool:
        return self._cfg.enabled

    def reset(self) -> None:
        """Clear all state (e.g., new conversation turn)."""
        self._exact_failures.clear()
        self._tool_failures.clear()
        self._result_hashes.clear()
        self._no_progress.clear()

    def record_result(
        self,
        signature: ToolCallSignature,
        *,
        failed: bool,
        result_content: str = "",
        idempotent: bool = False,
    ) -> GuardrailDecision:
        """Record a tool result and return a decision.

        Args:
            signature: Tool name + args hash.
            failed: Whether the tool returned an error.
            result_content: Raw text content of the result (for no-progress hash).
            idempotent: Whether the tool is idempotent (enables no-progress detection).

        Returns:
            GuardrailDecision with action "allow", "warn", or "block".
        """
        if not self._cfg.enabled:
            return _ALLOW

        # --- Pattern 1: exact repeat failure ---
        if failed:
            self._exact_failures[signature] += 1
            self._tool_failures[signature.tool_name] += 1

            exact_count = self._exact_failures[signature]
            if exact_count >= self._cfg.exact_repeat_block_after:
                msg = (
                    f"Tool '{signature.tool_name}' has failed {exact_count} times "
                    f"with identical arguments. This tool is now blocked for this turn. "
                    f"Try a completely different approach."
                )
                logger.warning(
                    "Guardrail BLOCK: %s exact failures=%d",
                    signature.tool_name, exact_count,
                )
                return GuardrailDecision(action="block", reason=msg)

            if exact_count >= self._cfg.exact_repeat_warn_after:
                msg = (
                    f"WARNING: Tool '{signature.tool_name}' has failed {exact_count} times "
                    f"with identical arguments. Consider trying a different approach or "
                    f"different arguments."
                )
                return GuardrailDecision(action="warn", reason=msg)

            # --- Pattern 2: same-tool failure (any args) ---
            tool_count = self._tool_failures[signature.tool_name]
            if tool_count >= self._cfg.same_tool_fail_block_after:
                msg = (
                    f"Tool '{signature.tool_name}' has failed {tool_count} times "
                    f"this turn (various arguments). This tool is now blocked. "
                    f"Use a different tool or approach."
                )
                logger.warning(
                    "Guardrail BLOCK: %s total failures=%d",
                    signature.tool_name, tool_count,
                )
                return GuardrailDecision(action="block", reason=msg)

            if tool_count >= self._cfg.same_tool_fail_warn_after:
                msg = (
                    f"WARNING: Tool '{signature.tool_name}' has failed {tool_count} times "
                    f"this turn. Consider using a different tool."
                )
                return GuardrailDecision(action="warn", reason=msg)

            return _ALLOW

        # --- Pattern 3: no-progress loop (idempotent tools only) ---
        if idempotent and result_content:
            result_hash = hashlib.sha256(result_content.encode()).hexdigest()[:16]
            prev_hash = self._result_hashes.get(signature)
            self._result_hashes[signature] = result_hash

            if prev_hash == result_hash:
                self._no_progress[signature] += 1
                np_count = self._no_progress[signature]

                if np_count >= self._cfg.no_progress_block_after:
                    msg = (
                        f"Tool '{signature.tool_name}' has returned identical results "
                        f"{np_count + 1} times. No progress is being made. "
                        f"This tool is blocked for this turn."
                    )
                    logger.warning(
                        "Guardrail BLOCK: %s no-progress=%d",
                        signature.tool_name, np_count,
                    )
                    return GuardrailDecision(action="block", reason=msg)

                if np_count >= self._cfg.no_progress_warn_after:
                    msg = (
                        f"WARNING: Tool '{signature.tool_name}' is returning identical "
                        f"results. Consider using different arguments or a different tool."
                    )
                    return GuardrailDecision(action="warn", reason=msg)
            else:
                # Reset no-progress counter when result changes
                self._no_progress[signature] = 0

        return _ALLOW
