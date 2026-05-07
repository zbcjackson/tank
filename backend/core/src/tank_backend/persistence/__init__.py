"""Unified persistence layer for Tank.

One :class:`Database` lives in the composition root and is passed into
every store (conversations, channels, jobs, speakers). Stores still
return their existing frozen-dataclass domain types — the ORM row types
in :mod:`.models` are internal to the persistence layer.
"""

from __future__ import annotations

from .base import Base
from .bootstrap import BootstrapResult, bootstrap_legacy_data, default_legacy_sources
from .database import Database
from .migrate import run_migrations

__all__ = [
    "Base",
    "BootstrapResult",
    "Database",
    "bootstrap_legacy_data",
    "default_legacy_sources",
    "run_migrations",
]
