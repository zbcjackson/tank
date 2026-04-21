"""User preference management — per-user learned preferences from conversations."""

from .config import PreferenceConfig
from .store import PreferenceStore

__all__ = ["PreferenceConfig", "PreferenceStore"]
