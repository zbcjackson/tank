"""Configuration for the context management subsystem."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextConfig:
    """Configuration for :class:`ContextManager`."""

    max_history_tokens: int = 8000
    keep_recent_messages: int = 5
    summary_max_tokens: int = 500
    summary_temperature: float = 0.3
    store_type: str = "file"  # "file" | "sqlite"
    store_path: str = "~/.tank/sessions"  # dir for file, db path for sqlite
