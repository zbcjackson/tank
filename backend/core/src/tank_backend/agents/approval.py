"""Human-in-the-loop approval system for sensitive tool execution."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Default timeout for approval requests (seconds)
DEFAULT_APPROVAL_TIMEOUT = 120.0


@dataclass(frozen=True)
class ApprovalRequest:
    """Immutable request for user approval before tool execution."""

    approval_id: str
    tool_name: str
    tool_args: dict[str, Any]
    description: str
    session_id: str


@dataclass(frozen=True)
class ApprovalResult:
    """Immutable result of an approval decision."""

    approval_id: str
    approved: bool
    reason: str = ""


def make_approval_id() -> str:
    """Generate a unique approval ID."""
    return uuid.uuid4().hex[:12]


# Tools that always require approval regardless of config.
# These run arbitrary commands — no in-tool policy to protect the user.
HARDCODED_REQUIRE_APPROVAL: frozenset[str] = frozenset({
    "run_command",
    "persistent_shell",
})


class ToolApprovalPolicy:
    """Config-driven policy determining which tools require approval.

    Sandbox tools (``run_command``, ``persistent_shell``) always require approval
    — this is hardcoded and cannot be overridden by config.

    File tools handle their own approval via ``ApprovalCallback`` inside
    ``execute()`` with per-path granularity, so they don't need tool-level
    approval here.

    The config-driven lists (``always_approve``, ``require_approval``,
    ``require_approval_first_time``) are an optional mechanism for future
    tools that don't implement their own policy.

    Tools not listed in any category default to ``always_approve``.
    """

    def __init__(
        self,
        always_approve: set[str] | None = None,
        require_approval: set[str] | None = None,
        require_approval_first_time: set[str] | None = None,
    ) -> None:
        self._always_approve = always_approve or set()
        self._require_approval = require_approval or set()
        self._require_approval_first_time = require_approval_first_time or set()
        self._session_approved: set[str] = set()

    def needs_approval(self, tool_name: str) -> bool:
        """Return True if the tool requires user approval before execution."""
        # Hardcoded tools always require approval
        if tool_name in HARDCODED_REQUIRE_APPROVAL:
            return True
        if tool_name in self._require_approval:
            return True
        if tool_name in self._require_approval_first_time:
            return tool_name not in self._session_approved
        # always_approve or unlisted → no approval needed
        return False

    def record_approved(self, tool_name: str) -> None:
        """Record that a tool has been approved in this session (for first-time tracking)."""
        self._session_approved.add(tool_name)

    def reset(self) -> None:
        """Clear first-time approval tracking (e.g., on session reset)."""
        self._session_approved.clear()


@dataclass
class _PendingApproval:
    """Internal state for a pending approval request."""

    request: ApprovalRequest
    future: asyncio.Future[ApprovalResult]
    loop: asyncio.AbstractEventLoop
    timeout_handle: asyncio.TimerHandle | None = None
    resolved: bool = False


class ApprovalManager:
    """Manages pending approval requests with async Future resolution.

    Each request gets a Future that the agent awaits. The Future is resolved
    when the user responds (via REST or WebSocket) or when the timeout fires.
    """

    def __init__(self, timeout: float = DEFAULT_APPROVAL_TIMEOUT) -> None:
        self._timeout = timeout
        self._pending: dict[str, _PendingApproval] = {}
        self._on_request_callback: Callable[[ApprovalRequest], None] | None = None

    def set_on_request(self, callback: Callable[[ApprovalRequest], None]) -> None:
        """Register a callback invoked whenever an approval is requested.

        The Brain uses this to post approval notifications to the UI,
        ensuring they go through the same Bus/WebSocket path as all
        other UI messages — regardless of whether the request originates
        from the outer agent or an inner sub-agent.
        """
        self._on_request_callback = callback

    async def request_approval(self, request: ApprovalRequest) -> ApprovalResult:
        """Create a pending approval and wait for resolution or timeout.

        Returns:
            ApprovalResult with approved=True/False.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[ApprovalResult] = loop.create_future()

        # Schedule timeout auto-rejection
        timeout_handle = loop.call_later(
            self._timeout,
            self._timeout_reject,
            request.approval_id,
        )

        self._pending[request.approval_id] = _PendingApproval(
            request=request,
            future=future,
            loop=loop,
            timeout_handle=timeout_handle,
        )

        logger.info(
            "Approval requested: id=%s tool=%s session=%s",
            request.approval_id, request.tool_name, request.session_id,
        )

        # Notify the Brain (or whoever registered) so it can post to the UI
        if self._on_request_callback is not None:
            try:
                self._on_request_callback(request)
            except Exception:
                logger.error("on_request callback error", exc_info=True)

        try:
            return await future
        finally:
            self._cleanup(request.approval_id)

    def resolve(self, approval_id: str, approved: bool, reason: str = "") -> bool:
        """Resolve a pending approval. Returns True if the approval existed.

        Thread-safe: the Future may live on a different event loop (e.g. a
        ThreadedQueue consumer thread). We use ``call_soon_threadsafe`` so the
        resolution is scheduled on the loop that owns the Future.
        """
        pending = self._pending.get(approval_id)
        if pending is None:
            logger.warning("Resolve called for unknown approval_id=%s", approval_id)
            return False

        if pending.resolved or pending.future.done():
            logger.warning("Resolve called for already-resolved approval_id=%s", approval_id)
            return False

        result = ApprovalResult(
            approval_id=approval_id,
            approved=approved,
            reason=reason,
        )
        pending.resolved = True
        pending.loop.call_soon_threadsafe(pending.future.set_result, result)

        action = "approved" if approved else "rejected"
        logger.info("Approval %s: id=%s reason=%s", action, approval_id, reason or "(none)")
        return True

    def get_pending(self, session_id: str | None = None) -> list[ApprovalRequest]:
        """Return pending approval requests, optionally filtered by session."""
        requests = []
        for entry in self._pending.values():
            if not entry.future.done() and (
                session_id is None or entry.request.session_id == session_id
            ):
                requests.append(entry.request)
        return requests

    def _timeout_reject(self, approval_id: str) -> None:
        """Auto-reject an approval after timeout."""
        pending = self._pending.get(approval_id)
        if pending is None or pending.future.done():
            return

        result = ApprovalResult(
            approval_id=approval_id,
            approved=False,
            reason="Approval timed out",
        )
        pending.future.set_result(result)
        logger.info("Approval timed out: id=%s", approval_id)

    def _cleanup(self, approval_id: str) -> None:
        """Remove a completed approval from pending state."""
        pending = self._pending.pop(approval_id, None)
        if pending and pending.timeout_handle:
            pending.timeout_handle.cancel()


async def request_with_notification(
    manager: ApprovalManager,
    request: ApprovalRequest,
    bus: Any = None,
) -> ApprovalResult:
    """Request approval via the ApprovalManager.

    The UI notification is handled by the manager's ``on_request`` callback
    (registered by the Brain). No need to post to the Bus here — that would
    cause duplicate notifications.

    The ``bus`` parameter is kept for backward compatibility but ignored.
    """
    return await manager.request_approval(request)


# ---------------------------------------------------------------------------
# State-machine approval: PendingToolCall + PendingToolCallStore
# ---------------------------------------------------------------------------


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
        tool_name = tool_call.function.name

        if not self._policy.needs_approval(tool_name):
            return await self._tool_manager.execute_openai_tool_call(tool_call)

        # Park the call
        import json

        try:
            tool_args = json.loads(tool_call.function.arguments)
        except (json.JSONDecodeError, TypeError):
            tool_args = {}

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
