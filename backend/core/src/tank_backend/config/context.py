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
    from ..context.compaction_store import CompactionStore
    from ..context.store import ConversationStore
    from ..jobs.scheduler import CronScheduler
    from ..jobs.store import JobStore
    from ..llm.capabilities import ModelCapabilities
    from ..llm.llm import LLM
    from ..media import MediaStore
    from ..persistence.conversation_messages_store import (
        ConversationMessagesStore,
    )
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
    compaction_store: CompactionStore | None = None
    conversation_messages_store: ConversationMessagesStore | None = None
    voiceprint_recognizer: VoiceprintRecognizer | None = None
    channel_store: ChannelStore | None = None
    media_store: MediaStore | None = None
    asr_engine: ASREngine | None = None
    tts_engine: TTSEngine | None = None
    vad_engine: VADEngine | None = None
    # Resolved once at startup from the default LLM profile. Consumers
    # (``ConnectorManager``, upload endpoint, …) read ``input_modalities``
    # to decide whether to accept multi-modal content before it hits the
    # LLM transport.
    llm_capabilities: ModelCapabilities | None = None


@dataclass(frozen=True)
class SessionContext:
    """Per-session objects. Created per WebSocket connection. Immutable."""

    app: AppContext
    bus: Bus
    llm: LLM
    tool_manager: ToolManager
    approval_policy: ToolApprovalPolicy
    pending_store: PendingToolCallStore
