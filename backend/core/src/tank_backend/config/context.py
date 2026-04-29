"""Scoped dependency containers.

``AppContext``    — app-level singletons, created once at server startup.
``SessionContext`` — per-session objects, created per WebSocket connection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..agents.approval import PendingToolCallStore, ToolApprovalPolicy
    from ..llm.llm import LLM
    from ..pipeline.bus import Bus
    from ..tools.manager import ToolManager



@dataclass(frozen=True)
class AppContext:
    """App-level singletons. Shared across all sessions. Immutable."""

    app_config: Any  # plugin.config.AppConfig or config.app_config.AppConfig
    job_store: Any = None
    scheduler: Any = None
    conversation_store: Any = None
    voiceprint_recognizer: Any = None


@dataclass(frozen=True)
class SessionContext:
    """Per-session objects. Created per WebSocket connection. Immutable."""

    app: AppContext
    bus: Bus
    llm: LLM
    tool_manager: ToolManager
    approval_policy: ToolApprovalPolicy
    pending_store: PendingToolCallStore
