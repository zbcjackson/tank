"""Unified security verdict types and approval resolvers.

All security policies return ``PolicyVerdict`` with a three-way ``AccessLevel``.
The ``ApprovalResolver`` protocol decides what to do with ``REQUIRE_APPROVAL``
verdicts — interactive mode asks the user, autonomous mode auto-approves or
auto-denies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class AccessLevel(Enum):
    """Three-way security verdict."""

    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


@dataclass(frozen=True)
class PolicyVerdict:
    """Result of any security policy evaluation."""

    level: AccessLevel
    reason: str
    policy: str = ""
    context: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ApprovalResolver(Protocol):
    """Decides what to do with REQUIRE_APPROVAL verdicts.

    Only called for REQUIRE_APPROVAL — ALLOW and DENY are handled
    directly by the approval gate without consulting the resolver.
    """

    async def resolve(
        self,
        verdict: PolicyVerdict,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> AccessLevel:
        """Return ALLOW or DENY for a REQUIRE_APPROVAL verdict."""
        ...


class AlwaysApproveResolver:
    """Auto-approve all REQUIRE_APPROVAL verdicts.

    For trusted autonomous jobs (approval_mode='always_approve').
    """

    async def resolve(
        self,
        verdict: PolicyVerdict,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> AccessLevel:
        logger.debug(
            "AlwaysApproveResolver: approving %s (%s)",
            tool_name, verdict.reason,
        )
        return AccessLevel.ALLOW


class AlwaysDenyResolver:
    """Auto-deny all REQUIRE_APPROVAL verdicts.

    Safe default for autonomous jobs (approval_mode='always_deny').
    """

    async def resolve(
        self,
        verdict: PolicyVerdict,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> AccessLevel:
        logger.debug(
            "AlwaysDenyResolver: denying %s (%s)",
            tool_name, verdict.reason,
        )
        return AccessLevel.DENY
