"""Typed configuration models for all config.yaml sections.

Each model is a frozen dataclass with sensible defaults.
``parse_section`` converts raw YAML dicts into these models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

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


# ── Context & memory ─────────────────────────────────────────────

@dataclass(frozen=True)
class ContextConfig:
    """``context:`` section."""

    max_history_tokens: int = 8000
    keep_recent_messages: int = 5
    summary_max_tokens: int = 500
    summary_temperature: float = 0.3
    store_type: str = "file"
    store_path: str = "~/.tank/sessions"


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


# ── Tools & policies ─────────────────────────────────────────────

@dataclass(frozen=True)
class NetworkAccessRuleConfig:
    """A single network access rule in config."""

    hosts: tuple[str, ...] = ()
    policy: str = "allow"
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

    default: str = "allow"
    rules: tuple[NetworkAccessRuleConfig, ...] = ()
    service_credentials: tuple[ServiceCredentialConfig, ...] = ()


@dataclass(frozen=True)
class FileAccessRuleConfig:
    """A single file access rule in config."""

    paths: tuple[str, ...] = ()
    read: str = "allow"
    write: str = "require_approval"
    delete: str = "require_approval"
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

    default_read: str = "allow"
    default_write: str = "require_approval"
    default_delete: str = "require_approval"
    rules: tuple[FileAccessRuleConfig, ...] = ()
    backup: BackupConfig = field(default_factory=BackupConfig)


@dataclass(frozen=True)
class AuditConfig:
    """``audit:`` section."""

    enabled: bool = False
    log_path: str = "~/.tank/audit.jsonl"


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
class MountConfig:
    """A single mount specification in sandbox config."""

    host: str = ""
    mode: str = "ro"


@dataclass(frozen=True)
class DockerConfig:
    """``docker:`` sub-section of sandbox."""

    image: str = ""
    workspace_host_path: str = ""


@dataclass(frozen=True)
class SandboxConfig:
    """``sandbox:`` section."""

    enabled: bool = True
    backend: str = "auto"
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
class AgentsConfig:
    """``agents:`` section."""

    llm_profile: str = "default"
    dirs: list[str] = field(default_factory=lambda: ["../agents", "~/.tank/agents"])
    max_depth: int = 3
    max_concurrent: int = 5
    system_prompt: str = ""


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
    db_path: str = "~/.tank/jobs/jobs.db"
    output_dir: str = "~/.tank/jobs/output"
    seed_path: str = ""


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
