"""Shared SQLAlchemy DeclarativeBase for all Tank ORM models.

All ORM row types across modules (conversations, channels, jobs, speakers)
inherit from the same ``Base`` so Alembic autogenerate can discover them
via ``Base.metadata``.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Root class for all Tank ORM models."""
