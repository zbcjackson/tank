"""Typed configuration models for all config.yaml sections.

Each model is a frozen dataclass with sensible defaults.
``parse_section`` converts raw YAML dicts into these models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from ..policy.verdict import AccessLevel

# ── Pipeline ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class BrainConfig:
    """``brain:`` section."""

    max_history_tokens: int = 8000


@dataclass(frozen=True)
class EchoGuardConfig:
    """``echo_guard:`` section.

    In config.yaml, ``similarity_threshold`` and ``window_seconds`` live
    under a nested ``self_echo_detection:`` key.  ``__config_flatten__``
    tells ``parse_section`` to hoist them into the top-level dict before
    constructing the dataclass.
    """

    __config_flatten__: ClassVar[dict[str, str]] = {
        "self_echo_detection": "",  # hoist all sub-keys to top level
    }

    enabled: bool = True
    vad_threshold_during_playback: float = 0.85
    similarity_threshold: float = 0.6
    window_seconds: float = 10.0


@dataclass(frozen=True)
class AssistantConfig:
    """``assistant:`` section."""

    speech_interrupt_enabled: bool = True


# ── Persistence ──────────────────────────────────────────────────

@dataclass(frozen=True)
class DatabaseConfig:
    """``database:`` section — unified ORM-backed persistence.

    One database file (SQLite) or URL (Postgres) backs conversations,
    channels, jobs, and speakers. Swap to Postgres by changing ``url``.
    """

    url: str = "sqlite+pysqlite:///~/.tank/tank.db"
    echo: bool = False


# ── Context & memory ─────────────────────────────────────────────

@dataclass(frozen=True)
class ContextConfig:
    """``context:`` section."""

    # Dynamic sizing
    context_window: int | None = None      # explicit override, None = auto-detect
    history_share: float = 0.50            # fraction of window for history
    output_reserve: int = 4096             # tokens reserved for LLM output
    headroom: int = 2000                   # safety buffer

    # Backward compat: 0 = use dynamic budget; >0 = hard cap
    max_history_tokens: int = 0
    keep_recent_messages: int = 5
    summary_max_tokens: int = 500
    summary_temperature: float = 0.3
    persist: bool = True

    # Compaction controls
    pre_turn_compact: bool = True
    max_compaction_passes: int = 3
    tool_result_max_share: float = 0.30
    pre_compaction_flush: bool = True


@dataclass(frozen=True)
class MemoryConfig:
    """``memory:`` section."""

    enabled: bool = False
    db_path: str = "../data/memory"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_model: str = ""
    search_limit: int = 5


@dataclass(frozen=True)
class PreferenceConfig:
    """``preferences:`` section."""

    enabled: bool = False
    max_entries: int = 20
    auto_learn: bool = True
    base_dir: str = ""


@dataclass(frozen=True)
class ConsolidationWeights:
    """Six-factor weighting for the Dream consolidator's scoring pass.

    Weights need not sum to 1.0 — they're applied to per-candidate
    factors that are each normalised to [0, 1]. Defaults match the
    OpenClaw heuristic that the doc credits as well-validated.
    """

    frequency: float = 0.24
    relevance: float = 0.30
    diversity: float = 0.15
    recency: float = 0.15
    consolidation: float = 0.10
    conceptual: float = 0.06


@dataclass(frozen=True)
class ConsolidationConfig:
    """``consolidation:`` section — Dream consolidation pipeline."""

    enabled: bool = False
    min_idle_minutes: int = 30
    interval_hours: int = 24
    diary_filename: str = "DREAMS.md"
    llm_profile: str = "consolidation"
    top_k_candidates: int = 20
    schedule: str = "0 3 * * *"        # 03:00 every day (cron syntax)
    weights: ConsolidationWeights = field(default_factory=ConsolidationWeights)


# ── Tools & policies ─────────────────────────────────────────────

@dataclass(frozen=True)
class NetworkAccessRuleConfig:
    """A single network access rule in config."""

    hosts: tuple[str, ...] = ()
    policy: AccessLevel = AccessLevel.ALLOW
    reason: str = ""


@dataclass(frozen=True)
class ServiceCredentialConfig:
    """A single service credential binding."""

    name: str = ""
    env_var: str = ""
    allowed_hosts: tuple[str, ...] = ()


@dataclass(frozen=True)
class NetworkAccessConfig:
    """``network_access:`` section."""

    default: AccessLevel = AccessLevel.ALLOW
    rules: tuple[NetworkAccessRuleConfig, ...] = ()
    service_credentials: tuple[ServiceCredentialConfig, ...] = ()


@dataclass(frozen=True)
class FileAccessRuleConfig:
    """A single file access rule in config."""

    paths: tuple[str, ...] = ()
    read: AccessLevel = AccessLevel.ALLOW
    write: AccessLevel = AccessLevel.REQUIRE_APPROVAL
    delete: AccessLevel = AccessLevel.REQUIRE_APPROVAL
    reason: str = ""
    priority: int = 0


@dataclass(frozen=True)
class BackupConfig:
    """``backup:`` sub-section of file_access."""

    enabled: bool = True
    path: str = "~/.tank/backups"
    max_age_days: int = 30


@dataclass(frozen=True)
class FileAccessConfig:
    """``file_access:`` section."""

    default_read: AccessLevel = AccessLevel.ALLOW
    default_write: AccessLevel = AccessLevel.REQUIRE_APPROVAL
    default_delete: AccessLevel = AccessLevel.REQUIRE_APPROVAL
    rules: tuple[FileAccessRuleConfig, ...] = ()
    backup: BackupConfig = field(default_factory=BackupConfig)


@dataclass(frozen=True)
class AuditConfig:
    """``audit:`` section.

    Rotation is opt-in. Leaving ``max_bytes=0`` preserves the pre-Phase-8
    unbounded append behaviour — operators who already pipeline the log
    via external tooling (logrotate, fluent-bit, …) don't need to know
    about the in-process rotation machinery. Setting any positive
    ``max_bytes`` enables size-based rotation.
    """

    enabled: bool = False
    log_path: str = "~/.tank/audit.jsonl"
    max_bytes: int = 0        # 0 disables in-process rotation
    backup_count: int = 5     # how many ``.jsonl.<N>`` backups to keep


@dataclass(frozen=True)
class DangerousPatternConfig:
    """A single dangerous command pattern."""

    pattern: str = ""
    description: str = ""


@dataclass(frozen=True)
class LLMEvaluationConfig:
    """``llm_evaluation:`` sub-section of command_security."""

    enabled: bool = False
    api_key: str = ""
    model: str = ""
    base_url: str = ""


@dataclass(frozen=True)
class CommandSecurityConfig:
    """``command_security:`` section."""

    extra_safe_commands: tuple[str, ...] = ()
    extra_dangerous_patterns: tuple[DangerousPatternConfig, ...] = ()
    always_require_approval: tuple[str, ...] = ()
    llm_evaluation: LLMEvaluationConfig = field(default_factory=LLMEvaluationConfig)


@dataclass(frozen=True)
class ToolGuardrailsConfig:
    """``tool_guardrails:`` section — loop detection thresholds."""

    enabled: bool = True
    exact_repeat_warn_after: int = 2
    exact_repeat_block_after: int = 4
    same_tool_fail_warn_after: int = 3
    same_tool_fail_block_after: int = 6
    no_progress_warn_after: int = 3
    no_progress_block_after: int = 5


@dataclass(frozen=True)
class HookConfig:
    """A single hook definition under ``hooks:``."""

    event: str = ""  # "pre_tool_call" | "post_tool_call"
    command: str = ""
    matcher: str = ""  # Regex on tool name (empty = all)
    timeout: float = 5.0
    enabled: bool = True


@dataclass(frozen=True)
class HooksConfig:
    """``hooks:`` section — user-defined shell hook scripts."""

    hooks: tuple[HookConfig, ...] = ()


@dataclass(frozen=True)
class MountConfig:
    """A single mount specification in sandbox config."""

    host: str = ""
    mode: Literal["ro", "rw"] = "ro"


@dataclass(frozen=True)
class DockerConfig:
    """``docker:`` sub-section of sandbox."""

    image: str = ""
    workspace_host_path: str = ""


@dataclass(frozen=True)
class SandboxConfig:
    """``sandbox:`` section."""

    enabled: bool = True
    backend: Literal["auto", "seatbelt", "bubblewrap", "docker"] = "auto"
    image: str = "tank-sandbox:latest"
    workspace_host_path: str = "./workspace"
    mounts: tuple[MountConfig, ...] = ()
    denied_mounts: tuple[str, ...] = ()
    memory_limit: str = "1g"
    cpu_count: int = 2
    default_timeout: int = 120
    max_timeout: int = 600
    network_enabled: bool = True
    docker: DockerConfig = field(default_factory=DockerConfig)


# ── Agent orchestration ──────────────────────────────────────────

@dataclass(frozen=True)
class ToolsetProfileConfig:
    """A single named toolset profile under ``toolsets.profiles``."""

    tools: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class ToolsetsConfig:
    """``toolsets:`` section — named tool subsets for agents and jobs.

    Profiles define named sets of allowed tools. Agents and jobs reference
    a profile by name via ``toolset: <name>`` in their definition. The
    special profile ``"all"`` means "no filtering" (default behavior).

    Example config.yaml::

        toolsets:
          profiles:
            safe:
              description: "Read-only tools"
              tools: [file_read, file_list, file_search, web_search, calculate, get_time]
            research:
              description: "Web and file research"
              tools: [file_read, file_list, file_search, web_search, web_fetch, calculate]
            full:
              description: "All tools (default)"
              tools: []  # empty = all tools
    """

    profiles: dict[str, ToolsetProfileConfig] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentsConfig:
    """``agents:`` section."""

    llm_profile: str = "default"
    dirs: list[str] = field(default_factory=lambda: ["../agents", "~/.tank/agents"])
    max_depth: int = 3
    max_concurrent: int = 5
    system_prompt: str = ""


@dataclass(frozen=True)
class NotificationHubConfig:
    """``notifications:`` section."""

    enabled: bool = True
    proactive_delivery: bool = True
    settle_seconds: float = 1.0
    max_wait_seconds: float = 60.0
    max_batch_size: int = 10


# ── Skills ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SkillsConfig:
    """``skills:`` section."""

    enabled: bool = True
    dirs: list[str] = field(default_factory=lambda: ["~/.tank/skills", "../skills"])
    auto_approve_threshold: str = "low"
    catalog_budget_percent: int = 2
    catalog_budget_max_chars: int = 12000


# ── Jobs ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class JobsConfig:
    """``jobs:`` section."""

    enabled: bool = False
    max_parallel: int = 3
    tick_interval: int = 60
    output_dir: str = "~/.tank/jobs/output"
    seed_path: str = ""


# ── Channels ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class ChannelsConfig:
    """``channels:`` section."""

    enabled: bool = True


# ── Connectors ────────────────────────────────────────────────────

@dataclass(frozen=True)
class ConnectorInstanceConfig:
    """One configured connector instance under ``connectors:``.

    ``instance`` is a locally-unique logical name (e.g. ``my-tg-bot``).
    ``extension`` is the fully-qualified plugin extension reference
    (``plugin:extension``) that must resolve to an extension of type
    ``connector``. ``config`` holds the instance-specific options
    passed to the connector factory.
    """

    instance: str = ""
    extension: str = ""
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConnectorsConfig:
    """``connectors:`` section — a list of configured connector instances
    plus cross-cutting behaviour knobs.

    ``asr_transcribe_timeout_s`` bounds the :class:`ASREngine.transcribe_once`
    call that :class:`ConnectorManager` makes on inbound voice notes.
    A hung ASR engine could otherwise freeze inbound dispatch indefinitely.
    Set to ``0`` to disable the bound (restores pre-Phase-8 behaviour).
    """

    instances: tuple[ConnectorInstanceConfig, ...] = ()
    asr_transcribe_timeout_s: float = 30.0


# ── Observability ─────────────────────────────────────────────────

@dataclass(frozen=True)
class AlertingConfig:
    """``alerting:`` section."""

    enabled: bool = False
    latency_spike_multiplier: float = 2.0
    latency_spike_consecutive: int = 5
    error_rate_threshold: float = 0.10
    error_rate_window_s: float = 300.0
    queue_saturation_pct: float = 0.80
    queue_saturation_duration_s: float = 30.0
    stuck_approval_timeout_s: float = 300.0
    alert_cooldown_s: float = 60.0
    webhook_url: str = ""


@dataclass(frozen=True)
class HealthMonitorConfig:
    """``health_monitor:`` section."""

    poll_interval_s: float = 5.0
    stuck_threshold_s: float = 10.0
    max_consecutive_failures: int = 3
    auto_restart_enabled: bool = True
    restart_backoff_base_s: float = 1.0
    restart_backoff_max_s: float = 30.0
