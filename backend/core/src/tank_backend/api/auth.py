"""WebSocket connection auth (protocol plan P0-2).

The check is a pure function so the six token/require combinations are
unit-testable without a WebSocket. Applied in ``websocket_endpoint`` right
after accept — before any session/assistant work — so a rejected connection
costs nothing but a close frame.
"""

from __future__ import annotations

import hmac
import logging

from ..config.models import AuthConfig

logger = logging.getLogger(__name__)

WS_AUTH_CLOSE_CODE = 1008  # Policy Violation
WS_AUTH_CLOSE_REASON = "invalid or missing auth token"


def check_ws_auth(config: AuthConfig, provided: str | None) -> bool:
    """Decide whether a connection presenting *provided* token may proceed.

    - ``require=True``: a valid token is mandatory. An empty configured
      token fails closed — every connection is rejected (a misconfigured
      deployment must not silently run open).
    - ``require=False`` (LAN default): token-less clients connect as
      before; a client that *does* present a token must present the right
      one — a wrong token means the client is misconfigured, so it is
      rejected rather than silently downgraded to anonymous.
    - No configured token + ``require=False``: auth disabled entirely.
    """
    if not config.token:
        if config.require:
            logger.error(
                "auth.require=true but auth.token is empty — rejecting all "
                "WebSocket connections (fail closed)"
            )
            return False
        return True
    if provided is None:
        return not config.require
    return hmac.compare_digest(provided.encode("utf-8"), config.token.encode("utf-8"))
