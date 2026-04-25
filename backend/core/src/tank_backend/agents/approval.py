"""Human-in-the-loop approval system for sensitive tool execution.

State-machine approach: restricted tools are parked (not blocked), the LLM
asks the user naturally, and a CONFIRMING turn with ``confirm_action`` handles
the approval/rejection.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


def make_approval_id() -> str:
    """Generate a unique approval ID."""
    return uuid.uuid4().hex[:12]


# Tools that use command-level security evaluation via CommandSecurityPolicy.
COMMAND_TOOLS: frozenset[str] = frozenset({
    "run_command",
    "persistent_shell",
})


class ToolApprovalPolicy:
    """Thin router deciding which tools require user approval.

    Command tools (``run_command``, ``persistent_shell``) delegate to
    ``CommandSecurityPolicy`` for per-command evaluation.

    File tools handle their own approval via ``ApprovalCallback`` inside
    ``execute()`` with per-path granularity — not managed here.

    All other tools are auto-approved.
    """

    def __init__(
        self,
        command_policy: Any | None = None,
        llm: Any | None = None,
    ) -> None:
        self._command_policy = command_policy
        self._llm = llm

    def needs_approval(self, tool_name: str, tool_args: dict[str, Any] | None = None) -> bool:
        """Return True if the tool requires user approval before execution.

        Sync version — uses only pattern matching and allowlists, no LLM.
        """
        if tool_name in COMMAND_TOOLS:
            command = (tool_args or {}).get("command", "")
            if command and self._command_policy is not None:
                verdict = self._command_policy.evaluate(command)
                return not verdict.allowed
            # No command arg or no policy → require approval (safe default)
            return True
        return False

    async def needs_approval_async(
        self, tool_name: str, tool_args: dict[str, Any] | None = None
    ) -> bool:
        """Return True if the tool requires user approval before execution.

        Async version — uses pattern matching, allowlists, and optional LLM evaluation.
        """
        if tool_name in COMMAND_TOOLS:
            command = (tool_args or {}).get("command", "")
            if command and self._command_policy is not None:
                verdict = await self._command_policy.evaluate_async(command, self._llm)
                return not verdict.allowed
            # No command arg or no policy → require approval (safe default)
            return True
        return False


@dataclass(frozen=True)
class PendingToolCall:
    """A parked tool call awaiting user confirmation."""

    approval_id: str
    tool_name: str
    tool_args: dict[str, Any]
    tool_call_id: str       # OpenAI tool_call.id for message history
    arguments_raw: str      # Original JSON string for replay
    description: str        # Human-readable (e.g., "run command: ls -la")
    session_id: str
    created_at: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict for persistence."""
        return {
            "approval_id": self.approval_id,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "tool_call_id": self.tool_call_id,
            "arguments_raw": self.arguments_raw,
            "description": self.description,
            "session_id": self.session_id,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> PendingToolCall:
        """Deserialize from JSON-compatible dict."""
        return PendingToolCall(
            approval_id=data["approval_id"],
            tool_name=data["tool_name"],
            tool_args=data.get("tool_args", {}),
            tool_call_id=data.get("tool_call_id", ""),
            arguments_raw=data.get("arguments_raw", "{}"),
            description=data.get("description", ""),
            session_id=data.get("session_id", ""),
            created_at=data.get("created_at", 0.0),
        )


class PendingToolCallStore:
    """Thread-safe per-Brain store for parked tool calls.

    Maintains a FIFO list of tool calls that were intercepted by the
    ApprovalGateExecutor and need user confirmation before execution.
    """

    def __init__(self) -> None:
        self._pending: list[PendingToolCall] = []
        self._lock = threading.Lock()

    def park(self, pending: PendingToolCall) -> None:
        """Add a tool call to the pending queue."""
        with self._lock:
            self._pending.append(pending)

    def get_oldest_pending(self) -> PendingToolCall | None:
        """Return the oldest pending call without removing it."""
        with self._lock:
            return self._pending[0] if self._pending else None

    def consume(self, approval_id: str) -> PendingToolCall | None:
        """Remove and return the pending call matching *approval_id*."""
        with self._lock:
            for i, p in enumerate(self._pending):
                if p.approval_id == approval_id:
                    return self._pending.pop(i)
            return None

    def list_pending(self) -> list[PendingToolCall]:
        """Return a snapshot of all pending calls."""
        with self._lock:
            return list(self._pending)

    def clear_all(self) -> None:
        """Remove all pending calls (e.g., on conversation reset)."""
        with self._lock:
            self._pending.clear()

    def to_list(self) -> list[dict[str, Any]]:
        """Serialize all pending calls for persistence."""
        with self._lock:
            return [p.to_dict() for p in self._pending]

    def restore(self, items: list[dict[str, Any]]) -> None:
        """Replace pending calls from persisted data."""
        with self._lock:
            self._pending = [PendingToolCall.from_dict(d) for d in items]


def _build_tool_description(tool_name: str, tool_args: dict[str, Any]) -> str:
    """Build a human-readable description of a tool call.

    Moved here from llm_agent.py — this is the canonical location.
    """
    import json

    if tool_name in ("run_command", "persistent_shell") and "command" in tool_args:
        return tool_args["command"]
    if tool_name == "manage_process":
        action = tool_args.get("action", "")
        pid = tool_args.get("process_id", "")
        return f"Process {action}: {pid}" if pid else f"Process {action}"
    # Generic fallback
    return f"{tool_name}({json.dumps(tool_args, ensure_ascii=False)})"


class ApprovalGateExecutor:
    """Wraps ToolManager. Parks restricted tools instead of executing them.

    When a tool requires approval, this executor:
    1. Parks the call in PendingToolCallStore
    2. Posts an APPROVAL ui_message to the Bus
    3. Returns an error dict instructing the LLM to ask the user

    The LLM sees the error and asks the user naturally. On the next turn,
    Brain switches to CONFIRMING mode where only confirm_action is available.
    """

    def __init__(
        self,
        tool_manager: Any,
        approval_policy: ToolApprovalPolicy,
        pending_store: PendingToolCallStore,
        session_id: str,
        bus: Any,
        current_msg_id_fn: Callable[[], str],
    ) -> None:
        self._tool_manager = tool_manager
        self._policy = approval_policy
        self._store = pending_store
        self._session_id = session_id
        self._bus = bus
        self._current_msg_id_fn = current_msg_id_fn

    async def execute_openai_tool_call(self, tool_call: Any) -> dict[str, Any]:
        """Execute tool or park it if approval is required."""
        import json

        tool_name = tool_call.function.name

        try:
            tool_args = json.loads(tool_call.function.arguments)
        except (json.JSONDecodeError, TypeError):
            tool_args = {}

        if not await self._policy.needs_approval_async(tool_name, tool_args):
            return await self._tool_manager.execute_openai_tool_call(tool_call)

        description = _build_tool_description(tool_name, tool_args)
        pending = PendingToolCall(
            approval_id=make_approval_id(),
            tool_name=tool_name,
            tool_args=tool_args,
            tool_call_id=tool_call.id,
            arguments_raw=tool_call.function.arguments,
            description=description,
            session_id=self._session_id,
            created_at=time.time(),
        )
        self._store.park(pending)

        # Post APPROVAL ui_message for frontend ApprovalCard
        from ..core.events import DisplayMessage, UpdateType
        from ..pipeline.bus import BusMessage

        self._bus.post(
            BusMessage(
                type="ui_message",
                source="approval_gate",
                payload=DisplayMessage(
                    speaker="Brain",
                    text=description,
                    is_user=False,
                    msg_id=self._current_msg_id_fn(),
                    is_final=False,
                    update_type=UpdateType.APPROVAL,
                    metadata={
                        "approval_id": pending.approval_id,
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                    },
                ),
                timestamp=time.time(),
            )
        )

        return {
            "error": (
                "APPROVAL REQUIRED: This tool requires user confirmation before execution. "
                f"You MUST ask the user: 'I'd like to {description}. Should I go ahead?' "
                "Do NOT attempt to call this tool again until the user confirms."
            )
        }
