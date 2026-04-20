"""Configuration for the memory subsystem."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryConfig:
    """Memory service configuration (sourced from config.yaml ``memory:`` section)."""

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
        return cls(
            enabled=raw.get("enabled", False),
            db_path=raw.get("db_path", "../data/memory"),
            llm_api_key=raw.get("llm_api_key", ""),
            llm_base_url=raw.get("llm_base_url", ""),
            llm_model=raw.get("llm_model", ""),
            embedding_api_key=raw.get("embedding_api_key", ""),
            embedding_base_url=raw.get("embedding_base_url", ""),
            embedding_model=raw.get("embedding_model", ""),
            search_limit=raw.get("search_limit", 5),
        )
