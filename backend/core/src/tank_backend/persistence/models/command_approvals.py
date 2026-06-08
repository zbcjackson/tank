"""CommandApprovalRow — persisted command approval grants.

When a user approves an unknown command via the interactive confirm flow,
the base command is stored here so it auto-allows on subsequent sessions.
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class CommandApprovalRow(Base):
    __tablename__ = "command_approvals"

    command_pattern: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
