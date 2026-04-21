"""Configuration for the preferences system."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PreferenceConfig:
    """Preferences system configuration (from config.yaml ``preferences:`` section)."""

    enabled: bool = False
    max_entries: int = 20
    base_dir: str = ""  # defaults to ~/.tank/

    @classmethod
    def from_dict(cls, data: dict) -> PreferenceConfig:
        return cls(
            enabled=data.get("enabled", False),
            max_entries=data.get("max_entries", 20),
            base_dir=data.get("base_dir", ""),
        )
