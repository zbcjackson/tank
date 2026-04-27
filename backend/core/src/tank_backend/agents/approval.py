"""Approval system for sensitive tool execution.

The approval gate evaluates tool calls through ``ToolApprovalPolicy`` which
returns a three-way ``PolicyVerdict``. For ``REQUIRE_APPROVAL`` verdicts,
the gate parks the call and asks the user via the confirm agent flow.
In autonomous mode, the resolver auto-approves or auto-denies instead.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..policy.verdict import AccessLevel, PolicyVerdict

logger = logging.getLogger(__name__)


def make_approval_id() -> str:
    """Generate a unique approval ID."""
    return uuid.uuid4().hex[:12]


# Tools that use command-level security evaluation via CommandSecurityPolicy.
COMMAND_TOOLS: frozenset[str] = frozenset({
    "run_command",
    "persistent_shell",
})

# File tools — evaluated via FileAccessPolicy.
FILE_TOOLS: frozenset[str] = frozenset({
    "file_read", "file_write", "file_edit", "file_delete",
    "file_list", "file_search",
})

# Web tools — evaluated via NetworkAccessPolicy.
WEB_TOOLS: frozenset[str] = frozenset({
    "web_fetch", "web_search",
})


class ToolApprovalPolicy:
    """Evaluates tool calls and returns a three-way PolicyVerdict.

    Routes to the appropriate security policy based on tool type:
    - Command tools → CommandSecurityPolicy
    - File tools → FileAccessPolicy
    - Web tools → NetworkAccessPolicy
    - All other tools → ALLOW
    """

    def __init__(
        self,
        command_policy: Any | None = None,
        file_policy: Any | None = None,
        network_policy: Any | None = None,
        llm: Any | None = None,
    ) -> None:
        self._command_policy = command_policy
        self._file_policy = file_policy
        self._network_policy = network_policy
        self._llm = llm

    def evaluate(
        self, tool_name: str, tool_args: dict[str, Any] | None = None,
    ) -> PolicyVerdict:
        """Evaluate synchronously."""
        args = tool_args or {}

        if tool_name in COMMAND_TOOLS:
            return self._evaluate_command(args)

        if tool_name in FILE_TOOLS:
            return self._evaluate_file(tool_name, args)

        if tool_name in WEB_TOOLS:
            return self._evaluate_network(tool_name, args)

        return PolicyVerdict(
            level=AccessLevel.ALLOW,
            reason=f"auto-approved tool: {tool_name}",
            policy="tool",
        )

    async def evaluate_async(
        self, tool_name: str, tool_args: dict[str, Any] | None = None,
    ) -> PolicyVerdict:
        """Evaluate asynchronously (with optional LLM for unknown commands)."""
        args = tool_args or {}

        if tool_name in COMMAND_TOOLS:
            return await self._evaluate_command_async(args)

        if tool_name in FILE_TOOLS:
            return self._evaluate_file(tool_name, args)

        if tool_name in WEB_TOOLS:
            return self._evaluate_network(tool_name, args)

        return PolicyVerdict(
            level=AccessLevel.ALLOW,
            reason=f"auto-approved tool: {tool_name}",
            policy="tool",
        )

    # ------------------------------------------------------------------
    # Command evaluation
    # ------------------------------------------------------------------

    def _evaluate_command(self, args: dict[str, Any]) -> PolicyVerdict:
        command = args.get("command", "")
        if command and self._command_policy is not None:
            return self._command_policy.evaluate(command)
        return PolicyVerdict(
            level=AccessLevel.REQUIRE_APPROVAL,
            reason="no command argument or no policy configured",
            policy="command",
        )

    async def _evaluate_command_async(
        self, args: dict[str, Any],
    ) -> PolicyVerdict:
        command = args.get("command", "")
        if command and self._command_policy is not None:
            return await self._command_policy.evaluate_async(
                command, self._llm,
            )
        return PolicyVerdict(
            level=AccessLevel.REQUIRE_APPROVAL,
            reason="no command argument or no policy configured",
            policy="command",
        )

    # ------------------------------------------------------------------
    # File evaluation
    # ------------------------------------------------------------------

    def _evaluate_file(
        self, tool_name: str, args: dict[str, Any],
    ) -> PolicyVerdict:
        if self._file_policy is None:
            return PolicyVerdict(
                level=AccessLevel.ALLOW,
                reason="no file policy configured",
                policy="file",
            )

        path = args.get("path", "")
        if not path:
            return PolicyVerdict(
                level=AccessLevel.ALLOW,
                reason="no path argument",
                policy="file",
            )

        # Map tool name to operation
        op_map = {
            "file_read": "read", "file_list": "read",
            "file_search": "read", "file_write": "write",
            "file_edit": "write", "file_delete": "delete",
        }
        operation = op_map.get(tool_name, "read")
        return self._file_policy.evaluate(path, operation)

    # ------------------------------------------------------------------
    # Network evaluation
    # ------------------------------------------------------------------

    def _evaluate_network(
        self, tool_name: str, args: dict[str, Any],
    ) -> PolicyVerdict:
        if self._network_policy is None:
            return PolicyVerdict(
                level=AccessLevel.ALLOW,
                reason="no network policy configured",
                policy="network",
            )

        url = args.get("url", "") or args.get("query", "")
        if not url:
            return PolicyVerdict(
                level=AccessLevel.ALLOW,
                reason="no url/query argument",
                policy="network",
            )

        # Extract host from URL
        try:
            from urllib.parse import urlparse
            host = urlparse(url).hostname or ""
        except Exception:
            host = ""

        if not host:
            return PolicyVerdict(
                level=AccessLevel.ALLOW,
                reason="could not extract host",
                policy="network",
            )

        return self._network_policy.evaluate(host)


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
    """Build a human-readable description of a tool call."""
    import json

    if tool_name in ("run_command", "persistent_shell") and "command" in tool_args:
        return tool_args["command"]
    if tool_name == "manage_process":
        action = tool_args.get("action", "")
        pid = tool_args.get("process_id", "")
        return f"Process {action}: {pid}" if pid else f"Process {action}"
    # Generic fallback
    return f"{tool_name}({json.dumps(tool_args, ensure_ascii=False)})"


class InteractiveResolver:
    """Resolver for interactive mode — always parks for user confirmation.

    Returns REQUIRE_APPROVAL so the gate parks the call and asks the user
    via the confirm agent flow. This applies to ALL tool types (command,
    file, network) — the user must explicitly approve.
    """

    def __init__(
        self,
        pending_store: PendingToolCallStore,
        session_id: str,
        bus: Any,
        current_msg_id_fn: Callable[[], str],
    ) -> None:
        self._store = pending_store
        self._session_id = session_id
        self._bus = bus
        self._current_msg_id_fn = current_msg_id_fn

    async def resolve(
        self,
        verdict: PolicyVerdict,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> AccessLevel:
        """Always return REQUIRE_APPROVAL — gate parks and asks the user."""
        return AccessLevel.REQUIRE_APPROVAL


class ApprovalGateExecutor:
    """Wraps ToolManager. Evaluates policy and delegates to resolver.

    Flow:
      ALLOW            → execute tool
      DENY             → return error to agent (hard block)
      REQUIRE_APPROVAL → resolver decides:
        - InteractiveResolver → park call, ask user
        - AlwaysApproveResolver → execute tool
        - AlwaysDenyResolver → return error to agent
    """

    def __init__(
        self,
        tool_manager: Any,
        approval_policy: ToolApprovalPolicy,
        resolver: Any,
        pending_store: PendingToolCallStore,
        session_id: str,
        bus: Any,
        current_msg_id_fn: Callable[[], str],
    ) -> None:
        self._tool_manager = tool_manager
        self._policy = approval_policy
        self._resolver = resolver
        self._store = pending_store
        self._session_id = session_id
        self._bus = bus
        self._current_msg_id_fn = current_msg_id_fn

    async def execute_openai_tool_call(self, tool_call: Any) -> dict[str, Any]:
        """Execute tool, block it, or delegate to resolver."""
        import json

        tool_name = tool_call.function.name

        try:
            tool_args = json.loads(tool_call.function.arguments)
        except (json.JSONDecodeError, TypeError):
            tool_args = {}

        verdict = await self._policy.evaluate_async(tool_name, tool_args)

        # ALLOW → execute immediately
        if verdict.level == AccessLevel.ALLOW:
            return await self._tool_manager.execute_openai_tool_call(tool_call)

        # DENY → hard block
        if verdict.level == AccessLevel.DENY:
            return {
                "error": (
                    f"BLOCKED: {verdict.reason}. "
                    "This operation is not permitted."
                )
            }

        # REQUIRE_APPROVAL → ask resolver
        resolved = await self._resolver.resolve(verdict, tool_name, tool_args)

        if resolved == AccessLevel.ALLOW:
            return await self._tool_manager.execute_openai_tool_call(tool_call)

        if resolved == AccessLevel.DENY:
            return {
                "error": (
                    f"DENIED: {verdict.reason}. "
                    "This operation was not approved."
                )
            }

        # REQUIRE_APPROVAL from resolver → park for interactive approval
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
                "APPROVAL REQUIRED: This tool requires user confirmation "
                "before execution. "
                f"You MUST ask the user: 'I'd like to {description}. "
                "Should I go ahead?' "
                "Do NOT attempt to call this tool again until the user confirms."
            )
        }
