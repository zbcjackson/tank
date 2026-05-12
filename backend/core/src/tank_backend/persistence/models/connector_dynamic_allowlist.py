"""ConnectorDynamicAllowlistRow — admin-granted allowlist entries.

Separate from the static, config-declared allowlist rules because
(a) these come from user action, not operator config;
(b) they need to persist across restarts but also be listable / revocable
    from a future admin UI;
(c) they're scoped to ``(instance_name, platform, external_id)`` —
    two connector instances (staging + prod) share no grants.

The composite primary key makes ``grant()`` idempotent at the DB layer:
attempts to re-insert the same triple are rejected with an IntegrityError
and the store treats that as a successful no-op, which is exactly the
"Allow forever, again" scenario.
"""

from __future__ import annotations

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class ConnectorDynamicAllowlistRow(Base):
    __tablename__ = "connector_dynamic_allowlist"

    instance_name: Mapped[str] = mapped_column(String, primary_key=True)
    platform:      Mapped[str] = mapped_column(String, primary_key=True)
    external_id:   Mapped[str] = mapped_column(String, primary_key=True)
    granted_by:    Mapped[str] = mapped_column(String, nullable=False)
    created_at:    Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        # Index by (instance, platform) so the ``list_for_instance`` +
        # per-platform admin UI (future) stays O(log n) rather than
        # scanning the whole table.
        Index(
            "ix_connector_dynamic_allowlist_instance_platform",
            "instance_name", "platform",
        ),
    )
