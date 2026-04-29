"""Typed configuration models for all config.yaml sections.

Each model is a frozen dataclass with sensible defaults.
``parse_section`` converts raw YAML dicts into these models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

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

    @classmethod
    def from_dict(cls, raw: dict) -> MemoryConfig:
        """Build from a config dict, ignoring unknown keys."""
        import dataclasses
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in known})


@dataclass(frozen=True)
class PreferenceConfig:
    """``preferences:`` section."""

    enabled: bool = False
    max_entries: int = 20
    auto_learn: bool = True
    base_dir: str = ""


# ── Tools & policies ─────────────────────────────────────────────

@dataclass(frozen=True)
class NetworkAccessConfig:
    """``network_access:`` section (raw rules kept as dicts)."""

    default: str = "allow"
    rules: list[dict[str, Any]] = field(default_factory=list)
    service_credentials: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class FileAccessConfig:
    """``file_access:`` section (raw rules kept as dicts)."""

    default_read: str = "allow"
    default_write: str = "require_approval"
    default_delete: str = "require_approval"
    rules: list[dict[str, Any]] = field(default_factory=list)
    backup: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AuditConfig:
    """``audit:`` section."""

    enabled: bool = False
    log_path: str = "~/.tank/audit.jsonl"


@dataclass(frozen=True)
class CommandSecurityConfig:
    """``command_security:`` section."""

    extra_safe_commands: list[str] = field(default_factory=list)
    extra_dangerous_patterns: list[dict[str, str]] = field(default_factory=list)
    always_require_approval: list[str] = field(default_factory=list)
    llm_evaluation: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SandboxConfig:
    """``sandbox:`` section (raw mounts/docker kept as dicts)."""

    enabled: bool = True
    backend: str = "auto"
    image: str = "tank-sandbox:latest"
    workspace_host_path: str = "./workspace"
    mounts: list[dict[str, str]] = field(default_factory=list)
    denied_mounts: list[str] = field(default_factory=list)
    memory_limit: str = "1g"
    cpu_count: int = 2
    default_timeout: int = 120
    max_timeout: int = 600
    network_enabled: bool = True
    docker: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def from_dict(data: dict) -> SandboxConfig:
        """Create config from a dict (e.g. parsed YAML section)."""
        import dataclasses
        if not data:
            return SandboxConfig(enabled=False)
        known_fields = {f.name for f in dataclasses.fields(SandboxConfig)}
        return SandboxConfig(**{k: v for k, v in data.items() if k in known_fields})


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
