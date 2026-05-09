"""Scoped dependency containers.

``AppContext``    — app-level singletons, created once at server startup.
``SessionContext`` — per-session objects, created per WebSocket connection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tank_contracts import ASREngine, TTSEngine

    from ..agents.approval import PendingToolCallStore, ToolApprovalPolicy
    from ..audio.input.vad import VADEngine
    from ..audio.input.voiceprint import VoiceprintRecognizer
    from ..channels.store import ChannelStore
    from ..config import AppConfig
    from ..context.store import ConversationStore
    from ..jobs.scheduler import CronScheduler
    from ..jobs.store import JobStore
    from ..llm.llm import LLM
    from ..media import MediaStore
    from ..pipeline.bus import Bus
    from ..plugin.registry import ExtensionRegistry
    from ..tools.manager import ToolManager



@dataclass(frozen=True)
class AppContext:
    """App-level singletons. Shared across all sessions. Immutable."""

    app_config: AppConfig
    registry: ExtensionRegistry | None = None
    job_store: JobStore | None = None
    scheduler: CronScheduler | None = None
    conversation_store: ConversationStore | None = None
    voiceprint_recognizer: VoiceprintRecognizer | None = None
    channel_store: ChannelStore | None = None
    media_store: MediaStore | None = None
    asr_engine: ASREngine | None = None
    tts_engine: TTSEngine | None = None
    vad_engine: VADEngine | None = None


@dataclass(frozen=True)
class SessionContext:
    """Per-session objects. Created per WebSocket connection. Immutable."""

    app: AppContext
    bus: Bus
    llm: LLM
    tool_manager: ToolManager
    approval_policy: ToolApprovalPolicy
    pending_store: PendingToolCallStore
