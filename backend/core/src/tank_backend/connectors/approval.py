"""ApprovalBroker — in-memory coordination for ``REQUIRE_APPROVAL`` verdicts.

When :class:`ConnectorAllowlistPolicy` returns a ``REQUIRE_APPROVAL``
verdict, :class:`ConnectorManager` hands the message to the broker.
The broker:

1. Parks the pending :class:`MessageEvent` in a per-connector dict keyed
   on a fresh ``approval_id`` (16 hex, ~64 bits of entropy).
2. Calls the connector's
   :meth:`~tank_contracts.connector.Connector.send_approval_prompt` to
   render a three-button message to the first configured admin.
3. Replies "Request sent to admin..." to the unknown sender via the
   manager's ``_safe_send`` path.

When the admin clicks a button, the connector's SDK-level handler
parses the ``approval_id`` + choice from the callback data and calls
:meth:`ApprovalBroker.resolve`. The broker then:

- ``allow_once``: inserts the sender's ``external_id`` into the
  ``_one_shot_passes`` set the manager gave us at construction, then
  replays the pending message back through the manager's ``_on_inbound``
  (``dispatch`` callback). The second pass sees the one-shot hit and
  bypasses the allowlist gate for this single turn.
- ``allow_forever``: writes a row to :class:`DynamicAllowlistStore`
  (idempotent), then replays. The second pass hits the dynamic
  short-circuit in the policy and allows normally.
- ``deny``: delivers the "not authorised" reply to the sender, drops
  the pending entry. No replay, no dynamic row.

**In-memory only.** Pending entries live in a plain ``dict``; a
restart loses every in-flight request. The trade-off matches Phase 6's
trust model — restarts are rare, admin prompts are ephemeral, and the
sender simply re-pings. A 24-hour TTL cleans stale entries on each
``request`` / ``resolve`` call.

**Security.** :meth:`resolve` verifies the clicking identity appears
in the connector's ``admin_external_ids`` set; clicks from random
users (which Slack / Telegram do permit, since anyone who sees a
message with buttons can click them) are rejected with a warning.
"""

from __future__ import annotations

import logging
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Iterable

    from tank_contracts.connector import Connector, Identity, MessageEvent

    from .dynamic_allowlist import DynamicAllowlistStore

logger = logging.getLogger(__name__)


# 24-hour TTL on pending approval entries. Mostly paranoia — in practice
# admins either click within minutes or never, but a leaky dict under
# heavy unapproved traffic could eventually hold the kernel's OOM killer's
# attention. Cleanup is lazy (runs on access) so there's no background
# timer to own.
_PENDING_TTL_S = 24 * 60 * 60

# Approval IDs are 16 hex chars = 64 bits of entropy. Generous for a
# short-lived token that's only honoured when the clicking identity
# also matches the configured admin allowlist.
_APPROVAL_ID_BYTES = 8

# Preview cap for the pending message's text in the admin prompt.
# Short enough to fit comfortably in a mobile Telegram / Discord DM,
# long enough to give an admin context for a decision.
_PREVIEW_MAX_CHARS = 200


# Admin-visible choice names. Kept as plain strings because each
# platform encodes them into its own callback-data format
# (``approve:once:{id}`` for Telegram, ``action_id`` for Slack, etc.).
CHOICE_ALLOW_ONCE = "allow_once"
CHOICE_ALLOW_FOREVER = "allow_forever"
CHOICE_DENY = "deny"

VALID_CHOICES = frozenset({CHOICE_ALLOW_ONCE, CHOICE_ALLOW_FOREVER, CHOICE_DENY})


@dataclass(frozen=True)
class PendingApproval:
    """One message awaiting admin decision."""

    approval_id: str
    source: Connector
    event: MessageEvent
    created_at: float  # monotonic seconds


# Dispatch callback: signature matches :meth:`ConnectorManager._on_inbound`.
Dispatch = Callable[["Connector", "MessageEvent"], "Awaitable[None]"]


class ApprovalBroker:
    """Per-connector-instance coordinator for ``REQUIRE_APPROVAL`` verdicts.

    One broker per connector instance. The manager builds it at startup
    and attaches it to the connector via :meth:`Connector.set_approval_broker`
    so the connector's SDK-level button-click handler can reach
    :meth:`resolve`.
    """

    def __init__(
        self,
        *,
        instance_name: str,
        admin_external_ids: Iterable[str],
        dynamic_store: DynamicAllowlistStore,
        dispatch: Dispatch,
        one_shot_passes: set[str],
    ) -> None:
        self._instance_name = instance_name
        # Materialise into a plain frozenset so per-resolve membership
        # checks are O(1) without re-iterating whatever ``config`` gave us.
        self._admin_external_ids: frozenset[str] = frozenset(admin_external_ids)
        self._dynamic_store = dynamic_store
        self._dispatch = dispatch
        # Shared with ConnectorManager: the manager's inbound gate pops
        # entries on first hit, so we don't need to coordinate TTL or
        # isolation — any leftover after the replay's second pass is a
        # bug, not a design point.
        self._one_shot_passes = one_shot_passes
        self._pending: dict[str, PendingApproval] = {}

    @property
    def instance_name(self) -> str:
        return self._instance_name

    @property
    def admin_external_ids(self) -> frozenset[str]:
        return self._admin_external_ids

    @property
    def pending_count(self) -> int:
        """Observability hook — tests + future metrics read this."""
        return len(self._pending)

    # ── Request ─────────────────────────────────────────────────────

    async def request(
        self, source: Connector, event: MessageEvent,
    ) -> str | None:
        """Park the event, send the admin prompt, return the approval_id.

        Returns ``None`` when the prompt could not be dispatched (no
        admin configured, or ``send_approval_prompt`` raised). The
        caller — normally :class:`ConnectorManager` — already handles
        the "please wait" reply to the sender separately, so ``None``
        just means "don't expect this approval_id to resolve later."
        """
        self._gc_expired()

        if not self._admin_external_ids:
            logger.warning(
                "ApprovalBroker '%s': no admin_external_ids configured; "
                "dropping approval request for %s",
                self._instance_name, event.identity.external_id,
            )
            return None

        approval_id = secrets.token_hex(_APPROVAL_ID_BYTES)
        pending = PendingApproval(
            approval_id=approval_id,
            source=source,
            event=event,
            created_at=time.monotonic(),
        )
        self._pending[approval_id] = pending

        # Same-platform routing (Phase 10 non-goal: cross-platform
        # broadcast). Pick the first admin identity deterministically;
        # future phases can fan out / pick by round-robin.
        admin_ext_id = next(iter(sorted(self._admin_external_ids)))

        # Build an :class:`Identity` the connector can use to route the
        # outbound prompt. Only ``platform`` + ``external_id`` are
        # guaranteed meaningful here — the connector's own send path
        # (e.g. Slack's ``_resolve_channel``) fills in whatever else it
        # needs. We keep ``metadata`` empty so downstream code can tell
        # this is a *synthesized* identity (not one derived from an
        # inbound message).
        admin_identity = _make_admin_identity(
            platform=event.identity.platform,
            external_id=admin_ext_id,
        )

        preview = _preview_text(event)
        try:
            await source.send_approval_prompt(
                admin_identity=admin_identity,
                approval_id=approval_id,
                sender=event.identity,
                preview=preview,
            )
        except NotImplementedError:
            # Operator configured ``require_approval`` on a connector
            # whose SDK implementation doesn't support interactive
            # buttons. Log loudly and drop the pending entry; the
            # manager's "please wait" reply already went out, but the
            # sender will just never hear back. Surfacing at the policy
            # / startup layer would be nicer — a future phase can add
            # a capability flag and validate at config-load.
            logger.error(
                "ApprovalBroker '%s': connector %s does not implement "
                "send_approval_prompt; cannot route approval. Use 'allow'/'deny' "
                "rules instead.",
                self._instance_name, source.platform,
            )
            self._pending.pop(approval_id, None)
            return None
        except Exception:
            logger.exception(
                "ApprovalBroker '%s': send_approval_prompt raised; "
                "dropping pending entry %s",
                self._instance_name, approval_id,
            )
            self._pending.pop(approval_id, None)
            return None

        logger.info(
            "ApprovalBroker '%s': parked approval %s for sender %s (admin=%s)",
            self._instance_name, approval_id,
            event.identity.external_id, admin_ext_id,
        )
        return approval_id

    # ── Resolve ─────────────────────────────────────────────────────

    async def resolve(
        self,
        approval_id: str,
        choice: str,
        admin_identity: Identity,
    ) -> PendingApproval | None:
        """Admin button-click arrived — route the verdict.

        Silent no-op when:

        - ``approval_id`` is unknown (stale click after restart / TTL).
        - ``choice`` is not one of :data:`VALID_CHOICES`.
        - ``admin_identity`` isn't in the configured admin set (random
          non-admin clicked a button they happened to see).

        Each no-op logs at debug / warning so operators can diagnose.

        Returns the resolved :class:`PendingApproval` on a successful
        admin-click, or ``None`` when the resolve was a no-op. Callers
        (the three connector click handlers) use the return value to
        render a post-click confirmation — the admin sees "Approved
        for Alice" instead of stale, still-clickable buttons. Stale or
        unauthorised clicks return ``None`` so those paths leave the
        prompt alone (the admin would see buttons vanish without any
        confirmation, which is confusing).
        """
        self._gc_expired()

        if choice not in VALID_CHOICES:
            logger.warning(
                "ApprovalBroker '%s': unknown choice %r for approval %s",
                self._instance_name, choice, approval_id,
            )
            return None

        pending = self._pending.pop(approval_id, None)
        if pending is None:
            logger.info(
                "ApprovalBroker '%s': approval %s is stale or unknown; ignoring %s",
                self._instance_name, approval_id, choice,
            )
            return None

        if admin_identity.external_id not in self._admin_external_ids:
            logger.warning(
                "ApprovalBroker '%s': non-admin %s attempted to resolve "
                "approval %s (sender was %s); denying implicitly",
                self._instance_name,
                admin_identity.external_id,
                approval_id,
                pending.event.identity.external_id,
            )
            # Don't replay or deny — the pending entry has already been
            # popped, so the sender gets nothing. A real admin can
            # re-prompt by asking the sender to message again. Return
            # ``None`` so the click handler knows not to overwrite the
            # prompt (the non-admin who clicked shouldn't see confirmation).
            return None

        if choice == CHOICE_DENY:
            await _safe_connector_send(
                pending.source,
                pending.event.identity,
                "You're not authorised to use this bot.",
            )
            logger.info(
                "ApprovalBroker '%s': approval %s denied by admin %s",
                self._instance_name, approval_id, admin_identity.external_id,
            )
            return pending

        if choice == CHOICE_ALLOW_FOREVER:
            self._dynamic_store.grant(
                instance_name=self._instance_name,
                platform=pending.event.identity.platform,
                external_id=pending.event.identity.external_id,
                granted_by=admin_identity.external_id,
            )
            logger.info(
                "ApprovalBroker '%s': approval %s granted forever by admin %s "
                "for sender %s",
                self._instance_name, approval_id,
                admin_identity.external_id,
                pending.event.identity.external_id,
            )
        else:  # CHOICE_ALLOW_ONCE
            # The manager's inbound gate will pop this on the replay.
            # We intentionally use ``external_id`` rather than a full
            # ``Identity`` — the check is by-value, not by-object, so
            # a re-synthesised ``Identity`` on the replay will still hit.
            self._one_shot_passes.add(pending.event.identity.external_id)
            logger.info(
                "ApprovalBroker '%s': approval %s granted once by admin %s "
                "for sender %s",
                self._instance_name, approval_id,
                admin_identity.external_id,
                pending.event.identity.external_id,
            )

        # Replay the pending message back through the manager's
        # inbound path. The second pass finds an allowed identity
        # (via the dynamic store for "forever" or the one-shot set for
        # "once") and dispatches to the Assistant normally.
        try:
            await self._dispatch(pending.source, pending.event)
        except Exception:
            logger.exception(
                "ApprovalBroker '%s': replay dispatch raised for approval %s",
                self._instance_name, approval_id,
            )

        return pending

    # ── Internal ────────────────────────────────────────────────────

    def _gc_expired(self) -> None:
        """Drop pending entries older than :data:`_PENDING_TTL_S`.

        Lazy: runs on every request + resolve call. No background
        timer means no lifecycle coupling to the connector's event loop.
        Fine for realistic traffic; a connector that never gets a
        request wouldn't accumulate stale entries anyway.
        """
        if not self._pending:
            return
        cutoff = time.monotonic() - _PENDING_TTL_S
        expired = [
            aid for aid, p in self._pending.items() if p.created_at < cutoff
        ]
        for aid in expired:
            self._pending.pop(aid, None)
        if expired:
            logger.debug(
                "ApprovalBroker '%s': GC'd %d expired entries",
                self._instance_name, len(expired),
            )


# ── Helpers ─────────────────────────────────────────────────────────


def _preview_text(event: MessageEvent) -> str:
    """Shape a pending message into a short, admin-friendly preview.

    Empty text (attachment-only messages) becomes a placeholder so the
    admin still sees *something*. Long text is truncated with an
    ellipsis at a word boundary when possible.
    """
    text = (event.text or "").strip()
    if not text:
        if event.attachments:
            return f"[{len(event.attachments)} attachment(s), no text]"
        return "[empty message]"

    if len(text) <= _PREVIEW_MAX_CHARS:
        return text

    # Truncate at a space if one exists in the tail window, else hard-cut.
    trunc = text[: _PREVIEW_MAX_CHARS - 1]
    last_space = trunc.rfind(" ", _PREVIEW_MAX_CHARS // 2)
    if last_space > 0:
        trunc = trunc[:last_space]
    return trunc + "…"


def _make_admin_identity(*, platform: str, external_id: str) -> Identity:
    """Build a minimal :class:`Identity` for outbound admin routing.

    Only ``platform`` and ``external_id`` are meaningful — the connector's
    send path re-derives whatever routing info (Slack channel ID,
    Discord DM channel, Telegram chat ID) it needs from those two.
    Metadata is empty so downstream code can distinguish a synthesized
    admin identity from an inbound-derived one if it ever needs to.
    """
    # Local import to avoid a circular reference — the broker lives in
    # ``tank_backend.connectors``, but :class:`Identity` is declared in
    # ``tank_contracts`` which is a leaf package. The import is cheap
    # at module-load time; doing it inside the helper keeps the top of
    # this module focused on the core story.
    from tank_contracts.connector import Identity

    return Identity(
        platform=platform,
        external_id=external_id,
        display_name="",
        is_group=False,
        metadata={},
    )


async def _safe_connector_send(
    connector: Connector, identity: Identity, text: str,
) -> None:
    """Best-effort reply from the broker; swallow all exceptions.

    The broker is often called from an SDK callback-handler coroutine
    where an unhandled exception would kill the connector's dispatcher
    task. Callers that need better error telemetry should build it on
    top of :meth:`Connector.send` directly.
    """
    try:
        await connector.send(identity=identity, text=text)
    except Exception:
        logger.exception(
            "ApprovalBroker: failed to deliver reply via '%s'",
            connector.instance_name,
        )


__all__ = [
    "CHOICE_ALLOW_FOREVER",
    "CHOICE_ALLOW_ONCE",
    "CHOICE_DENY",
    "VALID_CHOICES",
    "ApprovalBroker",
    "PendingApproval",
]
