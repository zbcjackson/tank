"""ConnectorManager — lifecycle + dispatch for configured connectors.

Owns a collection of :class:`Connector` instances (one per configured
platform account), routes their inbound messages through the session
mapper into the existing :class:`ConnectionManager`, and wires outbound
streaming replies through a per-session :class:`StreamConsumer`.

The manager is additive: the existing WebSocket entrypoint at
``api/router.py`` continues to work unchanged. A connector-free deploy
behaves exactly as today.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ..core.content import ImageBlock, TextBlock
from ..policy.verdict import AccessLevel
from .base import Attachment
from .exceptions import DuplicateConnectorError
from .stream_consumer import StreamConsumer
from .voice_bridge import (
    VoiceBridgeError,
    concat_audio_chunks,
    decode_any_audio,
    decode_ogg_opus,
    encode_pcm_to_opus,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from ..api.manager import ConnectionManager
    from ..config.context import AppContext
    from ..core.assistant import Assistant
    from ..core.content import ContentBlock
    from ..pipeline.bus import BusMessage
    from ..policy.connector_access import ConnectorAllowlistPolicy
    from .approval import ApprovalBroker
    from .base import (
        Connector,
        Identity,
        MessageEvent,
    )
    from .dynamic_allowlist import DynamicAllowlistStore
    from .session_mapper import SessionMapper

logger = logging.getLogger("ConnectorManager")


# Match the /api/upload boundary. Oversized images are rejected in the
# connector path with a user-visible message before they hit MediaStore.
_MAX_IMAGE_BYTES = 25 * 1024 * 1024

# Default polite text sent to identities the allowlist rejects. Operators
# can override per-instance via ``unauthorized_reply`` in connector config.
_DEFAULT_UNAUTHORIZED_REPLY = "You're not authorised to use this bot."

# Phase 10: default text shown to an unknown sender while their message
# awaits admin approval. Operators override per-instance via
# ``allowlist.pending_reply``. Keep it short and reassuring — the sender
# doesn't need to know about the admin's UX.
_DEFAULT_PENDING_REPLY = "Request sent to admin. I'll reply once they approve."


class ConnectorManager:
    """Registers connectors, starts them at lifespan startup, tears them
    down at shutdown, and routes messages in both directions.

    Thread model: connector inbound callbacks may arrive on any thread
    (the platform SDK's loop). :meth:`_on_inbound` is an ``async`` method
    that runs on the FastAPI event loop — connectors schedule it with
    ``asyncio.run_coroutine_threadsafe`` or await it directly if they
    already live on the main loop.
    """

    def __init__(
        self,
        connection_manager: ConnectionManager,
        session_mapper: SessionMapper,
        app_context: AppContext,
        dynamic_allowlist_store: DynamicAllowlistStore | None = None,
    ) -> None:
        self._conn_mgr = connection_manager
        self._session_mapper = session_mapper
        self._app_context = app_context
        self._dynamic_allowlist_store = dynamic_allowlist_store
        self._connectors: dict[str, Connector] = {}
        # Track StreamConsumers and dispatchers so we can GC them when
        # sessions end. Keyed by (instance_name, session_id).
        self._consumers: dict[tuple[str, str], StreamConsumer] = {}
        self._dispatchers: dict[tuple[str, str], _ImageDispatcher] = {}
        self._voice_dispatchers: dict[tuple[str, str], _VoiceDispatcher] = {}
        # Per-instance allowlist policies and rejection text. Absence of
        # a policy means allow-all — the zero-config case that matches
        # pre-Phase-6 behaviour.
        self._allowlist_policies: dict[str, ConnectorAllowlistPolicy] = {}
        self._unauthorized_replies: dict[str, str] = {}
        # Phase 10: REQUIRE_APPROVAL machinery.
        # ``_brokers``: per-instance :class:`ApprovalBroker` (built only
        # when the policy configures ``admin_external_ids``).
        # ``_one_shot_passes``: per-instance set of ``external_id`` strings
        # that bypass the allowlist gate for exactly one inbound event;
        # populated by the broker on an ``allow_once`` verdict and
        # consumed on the replay's second pass through :meth:`_on_inbound`.
        # ``_pending_replies``: per-instance override for the "please wait"
        # reply sent to the sender while the admin decides.
        self._brokers: dict[str, ApprovalBroker] = {}
        self._one_shot_passes: dict[str, set[str]] = {}
        self._pending_replies: dict[str, str] = {}

    # ── Registration ────────────────────────────────────────────────

    def register(self, connector: Connector) -> None:
        """Add a :class:`Connector` instance. Must be called before
        :meth:`start_all`.
        """
        if connector.instance_name in self._connectors:
            raise DuplicateConnectorError(
                f"Connector instance '{connector.instance_name}' already registered"
            )
        connector.set_message_handler(
            # Bind the connector at registration time so the handler knows
            # its source when events arrive.
            self._make_inbound_handler(connector),
        )
        self._connectors[connector.instance_name] = connector
        logger.info(
            "Registered connector '%s' (platform=%s)",
            connector.instance_name, connector.platform,
        )

    def _make_inbound_handler(self, connector: Connector):
        async def handler(event: MessageEvent) -> None:
            await self._on_inbound(connector, event)
        return handler

    def iter_connectors(self) -> Iterable[Connector]:
        return self._connectors.values()

    def get(self, instance_name: str) -> Connector | None:
        return self._connectors.get(instance_name)

    # ── Allowlist wiring ────────────────────────────────────────────

    def set_allowlist_policy(
        self,
        instance_name: str,
        policy: ConnectorAllowlistPolicy,
    ) -> None:
        """Attach an allowlist policy to a connector instance.

        Must be called after :meth:`register` — the instance name is the
        link between them. Omitting this call leaves the instance in
        allow-all mode (pre-Phase-6 behaviour).

        Rebinding a policy at runtime is supported: call again with the
        same ``instance_name`` and a fresh :class:`ConnectorAllowlistPolicy`
        (the one in ``app_context.bus``-wired mode will re-publish every
        decision afterwards).
        """
        if instance_name not in self._connectors:
            raise KeyError(
                f"Cannot set allowlist for unknown connector "
                f"instance '{instance_name}'",
            )
        self._allowlist_policies[instance_name] = policy
        logger.info(
            "Attached allowlist policy to connector '%s'", instance_name,
        )

    def set_unauthorized_reply(self, instance_name: str, text: str) -> None:
        """Override the polite rejection text for one connector instance."""
        if instance_name not in self._connectors:
            raise KeyError(
                f"Cannot set reply for unknown connector "
                f"instance '{instance_name}'",
            )
        self._unauthorized_replies[instance_name] = text

    # ── Approval workflow (Phase 10) ────────────────────────────────

    def set_approval_broker(
        self, instance_name: str, broker: ApprovalBroker,
    ) -> None:
        """Attach an :class:`ApprovalBroker` to a connector instance.

        Wired at startup when the instance's allowlist configures
        ``admin_external_ids``. The broker's ``dispatch`` callback
        points at :meth:`_on_inbound` so replays re-enter the same
        gate — the one-shot set or dynamic grant allows the replay
        through on its second pass.

        The per-instance one-shot set is stored here so the broker and
        the inbound gate share the same mutable object; the broker
        adds to it on ``allow_once``, the gate discards on consume.
        """
        if instance_name not in self._connectors:
            raise KeyError(
                f"Cannot set approval broker for unknown connector "
                f"instance '{instance_name}'",
            )
        self._brokers[instance_name] = broker
        # The set was already wired at construction time when the
        # broker was built (see :func:`_wire_approval` in server.py),
        # so we just make sure the manager knows about it.
        self._one_shot_passes.setdefault(instance_name, set())

        connector = self._connectors[instance_name]
        connector.set_approval_broker(broker)
        logger.info(
            "Attached ApprovalBroker to connector '%s'", instance_name,
        )

    def set_pending_reply(self, instance_name: str, text: str) -> None:
        """Override the "please wait" reply sent to senders awaiting approval."""
        if instance_name not in self._connectors:
            raise KeyError(
                f"Cannot set pending reply for unknown connector "
                f"instance '{instance_name}'",
            )
        self._pending_replies[instance_name] = text

    def _one_shot_set_for(self, instance_name: str) -> set[str]:
        """Return the per-instance one-shot pass set, lazily creating it.

        Exposed for :class:`ApprovalBroker` construction at startup —
        the broker mutates the *same* set that the gate reads, so
        "Allow once" grants pass through without a second coordination
        surface.
        """
        return self._one_shot_passes.setdefault(instance_name, set())

    # ── Lifecycle ───────────────────────────────────────────────────

    async def start_all(self) -> None:
        """Start every registered connector. Failures are logged but do
        not abort — other connectors keep starting."""
        for connector in self._connectors.values():
            try:
                await connector.start()
                logger.info("Started connector '%s'", connector.instance_name)
            except Exception:
                logger.exception(
                    "Failed to start connector '%s'", connector.instance_name,
                )

    async def stop_all(self) -> None:
        """Stop every connector and release per-session consumers."""
        for connector in self._connectors.values():
            try:
                await connector.stop()
                logger.info("Stopped connector '%s'", connector.instance_name)
            except Exception:
                logger.exception(
                    "Failed to stop connector '%s'", connector.instance_name,
                )
        self._consumers.clear()
        self._dispatchers.clear()
        self._voice_dispatchers.clear()

    # ── Dispatch ────────────────────────────────────────────────────

    async def _on_inbound(
        self, source: Connector, event: MessageEvent,
    ) -> None:
        """Route an inbound platform message to the right Assistant.

        Allowlist gate — runs before session resolution or Assistant
        construction so denied requests cost essentially nothing.
        Absence of a policy for this instance means allow-all
        (zero-config case, pre-Phase-6 behaviour).

        Phase 10 adds two short-circuits:

        1. **One-shot pass**: after an admin clicked "Allow once", the
           broker added the sender's ``external_id`` to the per-instance
           set. Inbound events for that identity skip the allowlist gate
           exactly once; the consume-on-hit semantics mean the next
           message will face the gate again.

        2. **REQUIRE_APPROVAL**: the policy returns an approval verdict
           when an unknown sender's identity doesn't match any rule
           under a ``default: require_approval`` allowlist. The manager
           routes through :class:`ApprovalBroker` — pending message
           parked, admin prompt fired, polite-wait reply sent to the
           sender. The broker's ``allow_*`` verdicts replay via this
           same method, taking the one-shot or dynamic-grant fast path.
        """
        identity = event.identity

        # Phase 10: one-shot consume. Must run *before* policy.evaluate()
        # so a replayed "allow_once" message doesn't bounce back into a
        # fresh approval request.
        one_shot_set = self._one_shot_passes.get(source.instance_name)
        one_shot_hit = (
            one_shot_set is not None
            and identity.external_id in one_shot_set
        )
        if one_shot_hit:
            # Consume before any await points so concurrent events on
            # the same identity don't double-dip.
            assert one_shot_set is not None  # noqa: S101 — guarded above
            one_shot_set.discard(identity.external_id)
            logger.debug(
                "ConnectorManager: one-shot allow for %s/%s via '%s'",
                identity.platform, identity.external_id,
                source.instance_name,
            )

        if not one_shot_hit:
            policy = self._allowlist_policies.get(source.instance_name)
            if policy is not None:
                verdict = policy.evaluate(identity)
                if verdict.level is AccessLevel.DENY:
                    reply_text = self._unauthorized_replies.get(
                        source.instance_name,
                        _DEFAULT_UNAUTHORIZED_REPLY,
                    )
                    await _safe_send(source, identity, reply_text)
                    logger.info(
                        "ConnectorManager: denied inbound from %s/%s via '%s' "
                        "(%s): %s",
                        identity.platform, identity.external_id,
                        source.instance_name,
                        verdict.level.value, verdict.reason,
                    )
                    return
                if verdict.level is AccessLevel.REQUIRE_APPROVAL:
                    broker = self._brokers.get(source.instance_name)
                    if broker is None:
                        # Operator configured require_approval but
                        # didn't list any admins (or the broker failed
                        # to wire at startup). Fail closed: deny the
                        # sender, log loudly so the operator sees it.
                        logger.warning(
                            "ConnectorManager: REQUIRE_APPROVAL verdict on "
                            "'%s' but no broker attached "
                            "(admin_external_ids empty?); denying",
                            source.instance_name,
                        )
                        reply_text = self._unauthorized_replies.get(
                            source.instance_name,
                            _DEFAULT_UNAUTHORIZED_REPLY,
                        )
                        await _safe_send(source, identity, reply_text)
                        return
                    # Tell the sender we're waiting on the admin, then
                    # let the broker park the pending event + send the
                    # admin prompt. Reply first so the sender sees a
                    # response even if the admin-prompt send fails.
                    pending_text = self._pending_replies.get(
                        source.instance_name,
                        _DEFAULT_PENDING_REPLY,
                    )
                    await _safe_send(source, identity, pending_text)
                    await broker.request(source, event)
                    return
                # ALLOW → fall through to existing dispatch path.

        try:
            session_id = self._session_mapper.resolve(identity)
        except Exception:
            logger.exception(
                "SessionMapper.resolve failed for %s/%s via '%s'",
                identity.platform, identity.external_id, source.instance_name,
            )
            return

        # Connector sessions are text-only today. Voice in/out (Phase 4+)
        # will flip these based on ``source.capabilities.supports_voice_*``.
        # Skipping ASR/TTS keeps the pipeline from running VAD on silence
        # or generating TTS chunks that nobody plays.
        assistant, is_new = await self._conn_mgr.get_or_create_assistant(
            session_id,
            wants_audio_input=False,
            wants_audio_output=False,
        )

        if is_new:
            self._attach_outbound_stream(assistant, source, identity, session_id)

        blocks = await self._attachments_to_blocks(
            event.attachments,
            session_id=session_id,
            source=source,
            identity=identity,
        )

        # A pure voice note arrives as ``MessageEvent(text="",
        # attachments=[audio])``. ``_attachments_to_blocks`` transcribes the
        # audio into a :class:`TextBlock` (with a ``[voice message transcript]``
        # prefix). That block *is* the user's turn — but
        # ``Assistant.process_input`` short-circuits on empty ``text``, so
        # without the hoist below the turn is lost. Lift the first
        # TextBlock out of ``blocks`` into ``text`` when ``event.text`` is
        # empty, so voice-only messages reach the Brain like typed text.
        text = event.text
        if not text and blocks:
            for idx, block in enumerate(blocks):
                if isinstance(block, TextBlock):
                    text = block.text
                    # Drop the hoisted block; anything else (images,
                    # additional text blocks) continues via attachments.
                    blocks = blocks[:idx] + blocks[idx + 1:] or None
                    break

        user_display = identity.display_name or identity.external_id
        try:
            assistant.process_input(
                text=text,
                user=user_display,
                attachments=blocks,
            )
        except Exception:
            logger.exception(
                "Assistant.process_input raised for session %s via '%s'",
                session_id, source.instance_name,
            )

    # ── Outbound wiring ────────────────────────────────────────────

    def _attach_outbound_stream(
        self,
        assistant: Assistant,
        source: Connector,
        identity: Identity,
        session_id: str,
    ) -> None:
        """Subscribe the outbound dispatchers for this session to the
        Assistant's Bus so text streams, image attachments, and voice
        all flow back through ``source``.
        """
        consumer = StreamConsumer(connector=source, identity=identity)
        assistant._bus.subscribe("ui_message", consumer.on_ui_message)  # noqa: SLF001
        self._consumers[(source.instance_name, session_id)] = consumer

        dispatcher = _ImageDispatcher(
            connector=source,
            identity=identity,
            media_store=self._app_context.media_store,
        )
        assistant._bus.subscribe("outbound_attachment", dispatcher.on_event)  # noqa: SLF001
        self._dispatchers[(source.instance_name, session_id)] = dispatcher

        voice_dispatcher = _VoiceDispatcher(
            connector=source,
            identity=identity,
            tts_engine=self._app_context.tts_engine,
        )
        assistant._bus.subscribe("outbound_voice", voice_dispatcher.on_event)  # noqa: SLF001
        self._voice_dispatchers[(source.instance_name, session_id)] = voice_dispatcher

        logger.debug(
            "Attached outbound stream: connector=%s session=%s",
            source.instance_name, session_id,
        )

    # ── Helpers ────────────────────────────────────────────────────

    async def _attachments_to_blocks(
        self,
        attachments: tuple[Attachment, ...],
        *,
        session_id: str,
        source: Connector,
        identity: Identity,
    ) -> list[ContentBlock] | None:
        """Convert platform-agnostic attachments to Tank content blocks.

        Supported kinds:

        - ``text`` → :class:`TextBlock`
        - ``image`` with string data (URL/data URL) → :class:`ImageBlock`
          passthrough; the LLM transport handles resolution.
        - ``image`` with bytes → stored in :class:`MediaStore`, emitted
          as an :class:`ImageBlock` with a ``media://`` URI. Gated on
          the configured LLM's ``"image"`` modality.
        - ``audio`` / ``file`` → dropped (Phase 5+).

        Returns ``None`` when nothing survived so
        ``Assistant.process_input(attachments=None)`` stays the common
        zero-overhead path.
        """
        if not attachments:
            return None

        blocks: list[ContentBlock] = []
        for att in attachments:
            if att.kind == "text" and isinstance(att.data, str):
                blocks.append(TextBlock(text=att.data))
            elif att.kind == "image":
                block = await self._image_to_block(
                    att, session_id=session_id,
                    source=source, identity=identity,
                )
                if block is not None:
                    blocks.append(block)
            elif att.kind == "audio":
                block = await self._audio_to_text_block(
                    att, source=source, identity=identity,
                )
                if block is not None:
                    blocks.append(block)
            else:
                logger.debug(
                    "ConnectorManager: dropping unsupported attachment "
                    "(kind=%s, data=%s) — handled in Phase 5+",
                    att.kind, type(att.data).__name__,
                )
        return blocks or None

    async def _image_to_block(
        self,
        att: Attachment,
        *,
        session_id: str,
        source: Connector,
        identity: Identity,
    ) -> ImageBlock | None:
        """Turn one image attachment into an :class:`ImageBlock`.

        Capability-gated: if the default LLM can't see images, the
        connector sends a user-visible "text-only" reply and the block is
        dropped. Oversize and store-failure errors also get user-visible
        replies so the user knows why their photo didn't reach the LLM.
        """
        # Capability gate
        caps = self._app_context.llm_capabilities
        if caps is not None and "image" not in caps.input_modalities:
            await _safe_send(
                source, identity,
                "I can see text but not images with my current setup.",
            )
            return None

        # URL / data-URL case — no download, no storage. The LLM transport
        # resolves the scheme at send time.
        if isinstance(att.data, str):
            return ImageBlock(
                source=att.data,
                mime_type=att.mime_type or "image/png",
            )

        # Bytes case — persist via MediaStore, emit a ``media://`` URI.
        media_store = self._app_context.media_store
        if media_store is None:
            logger.warning(
                "MediaStore unavailable — dropping inbound image on %s",
                source.instance_name,
            )
            return None

        if len(att.data) > _MAX_IMAGE_BYTES:
            await _safe_send(
                source, identity,
                "That image is too large — please send one under 25 MB.",
            )
            return None

        mime_type = att.mime_type or "image/jpeg"
        try:
            stored = await media_store.put(
                att.data, mime_type, session_id=session_id,
            )
        except Exception:
            logger.exception("MediaStore.put failed for inbound image")
            await _safe_send(
                source, identity,
                "Sorry, I couldn't save that image — please try again.",
            )
            return None

        return ImageBlock(source=stored.media_uri, mime_type=stored.mime_type)

    async def _audio_to_text_block(
        self,
        att: Attachment,
        *,
        source: Connector,
        identity: Identity,
    ) -> TextBlock | None:
        """Transcribe a voice attachment into a :class:`TextBlock`.

        Decodes Ogg/Opus → 16 kHz float32 PCM via
        :mod:`~tank_backend.connectors.voice_bridge`, runs a one-shot
        transcription through :attr:`AppContext.asr_engine`, returns the
        transcript wrapped in a ``TextBlock`` with a ``[voice message
        transcript]`` prefix so the LLM can tell the text came from audio.

        Returns ``None`` silently for empty transcripts (pure silence /
        unintelligible) — spamming the user with "I heard nothing" is
        worse than no reply. Other failures send user-visible errors so
        operators can tell what went wrong.
        """
        asr_engine = self._app_context.asr_engine
        if asr_engine is None:
            await _safe_send(
                source, identity,
                "I can't transcribe voice messages with my current setup.",
            )
            return None

        if isinstance(att.data, str):
            # URL-based audio (e.g. a link to an externally hosted clip).
            # Decoding arbitrary URLs is deferred — v1 only handles bytes
            # that arrived over the connector's own download path.
            logger.debug(
                "ConnectorManager: URL-based audio attachment not supported in v1",
            )
            return None

        try:
            # Dispatch on MIME: Telegram's fixed ``audio/ogg`` hits the
            # tight ogg-specific decoder; everything else (Slack's
            # audio/webm, Apple mobile's audio/mp4, web recordings, …)
            # goes through the format-sniffing ``decode_any_audio``.
            # The split preserves Telegram's fast path byte-for-byte
            # while giving other connectors a one-liner to opt in.
            mime_type = (att.mime_type or "").split(";", 1)[0].strip().lower()
            if mime_type == "audio/ogg":
                pcm = await asyncio.to_thread(decode_ogg_opus, att.data)
            else:
                pcm = await asyncio.to_thread(
                    decode_any_audio, att.data, mime_type=att.mime_type,
                )
        except VoiceBridgeError:
            logger.exception("Voice decode failed for inbound audio")
            await _safe_send(
                source, identity,
                "Sorry, I couldn't read that voice message.",
            )
            return None
        except Exception:
            logger.exception("Unexpected error decoding inbound audio")
            await _safe_send(
                source, identity,
                "Sorry, I couldn't read that voice message.",
            )
            return None

        timeout_s = (
            self._app_context.app_config.connectors.asr_transcribe_timeout_s
        )
        try:
            if timeout_s > 0:
                transcript = await asyncio.wait_for(
                    asr_engine.transcribe_once(pcm, sample_rate=16000),
                    timeout=timeout_s,
                )
            else:
                transcript = await asr_engine.transcribe_once(
                    pcm, sample_rate=16000,
                )
        except asyncio.TimeoutError:
            # A hung ASR engine (model deadlock, upstream network drop,
            # pathological audio input) would otherwise block the inbound
            # dispatcher for this session until TCP timeouts fire, minutes
            # later. The bound above — configurable via
            # ``connectors.asr_transcribe_timeout_s``, default 30s — caps
            # the wait; the user sees a prompt polite reply instead of a
            # silent drop.
            logger.warning(
                "ASR timeout (> %.1fs) for inbound audio via '%s'",
                timeout_s, source.instance_name,
            )
            await _safe_send(
                source, identity,
                "Sorry, transcribing your voice message took too long.",
            )
            return None
        except Exception:
            logger.exception("ASR transcribe_once failed")
            await _safe_send(
                source, identity,
                "Sorry, I couldn't transcribe that voice message.",
            )
            return None

        transcript = transcript.strip()
        if not transcript:
            logger.debug(
                "ConnectorManager: empty ASR transcript from '%s'; dropping",
                source.instance_name,
            )
            return None

        return TextBlock(text=f"[voice message transcript] {transcript}")


async def _safe_send(
    connector: Connector, identity: Identity, text: str,
) -> None:
    """Best-effort send of an error message; swallow exceptions so the
    inbound path never fails because of a notification failure."""
    try:
        await connector.send(identity=identity, text=text)
    except Exception:
        logger.exception(
            "Failed to deliver error reply via '%s'",
            connector.instance_name,
        )


class _ImageDispatcher:
    """Subscribe to ``outbound_attachment`` Bus events; send any
    :class:`ImageBlock` s through the bound connector.

    Bus delivery is synchronous; connector ``send`` is async — we hop to
    the event loop via :func:`asyncio.run_coroutine_threadsafe`.
    """

    def __init__(
        self,
        *,
        connector: Connector,
        identity: Identity,
        media_store,  # MediaStore | None
    ) -> None:
        self._connector = connector
        self._identity = identity
        self._media_store = media_store
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:  # pragma: no cover — defensive only
            self._loop = asyncio.new_event_loop()

    def on_event(self, message: BusMessage) -> None:
        payload = message.payload or {}
        blocks = payload.get("blocks") or ()
        if not blocks:
            return
        asyncio.run_coroutine_threadsafe(self._dispatch(blocks), self._loop)

    async def _dispatch(self, blocks: Iterable[ContentBlock]) -> None:
        caps = self._connector.capabilities
        if not caps.supports_images_out:
            logger.debug(
                "Connector '%s' lacks image output support; dropping "
                "outbound attachment(s)",
                self._connector.instance_name,
            )
            return

        for block in blocks:
            if not isinstance(block, ImageBlock):
                continue
            try:
                att = await self._resolve_image_attachment(block)
            except Exception:
                logger.exception(
                    "Failed to resolve outbound image %r", block.source,
                )
                continue
            if att is None:
                continue

            try:
                result = await self._connector.send(
                    identity=self._identity,
                    text="",
                    attachments=(att,),
                )
            except Exception:
                logger.exception(
                    "Outbound image send raised on '%s'",
                    self._connector.instance_name,
                )
                continue
            if not result.ok:
                logger.warning(
                    "Outbound image send failed on '%s': %s",
                    self._connector.instance_name, result.error,
                )

    async def _resolve_image_attachment(
        self, block: ImageBlock,
    ) -> Attachment | None:
        """Turn an :class:`ImageBlock` into a platform-ready :class:`Attachment`.

        ``media://`` URIs are resolved to bytes through MediaStore.
        Other schemes (``data:``, ``http(s)://``, absolute paths) pass
        through as the string payload so the connector can either upload
        them or have the platform fetch them.
        """
        if block.source.startswith("media://"):
            if self._media_store is None:
                logger.warning(
                    "MediaStore unavailable — cannot resolve %s",
                    block.source,
                )
                return None
            data, mime = await self._media_store.get(block.source)
            return Attachment(kind="image", data=data, mime_type=mime)
        return Attachment(
            kind="image", data=block.source, mime_type=block.mime_type,
        )


class _VoiceDispatcher:
    """Subscribe to ``outbound_voice`` Bus events; synthesize the assistant
    reply via :attr:`AppContext.tts_engine` and send it as a voice message
    through the bound connector.

    Unlike :class:`_ImageDispatcher`, voice output is strictly
    **completion-only** — Telegram (and every other chat platform we'll
    support) doesn't let us stream audio into a voice message. We
    collect the full text, generate the full PCM, encode once, send once.

    Gated on ``connector.capabilities.supports_voice_out`` and the
    presence of a TTS engine in AppContext. Missing either → silently no-op,
    so the text reply (via :class:`StreamConsumer`) continues to flow.
    """

    def __init__(
        self,
        *,
        connector: Connector,
        identity: Identity,
        tts_engine,  # TTSEngine | None
    ) -> None:
        self._connector = connector
        self._identity = identity
        self._tts_engine = tts_engine
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:  # pragma: no cover — defensive only
            self._loop = asyncio.new_event_loop()
        # Serialize multiple turns — two concurrent TTS generations in the
        # same chat would play over each other.
        self._lock = asyncio.Lock()

    def on_event(self, message: BusMessage) -> None:
        payload = message.payload or {}
        text = (payload.get("text") or "").strip()
        if not text:
            return
        language = payload.get("language") or "auto"
        asyncio.run_coroutine_threadsafe(
            self._dispatch(text, language), self._loop,
        )

    async def _dispatch(self, text: str, language: str) -> None:
        if not self._connector.capabilities.supports_voice_out:
            return
        if self._tts_engine is None:
            return

        async with self._lock:
            try:
                chunks = []
                async for chunk in self._tts_engine.generate_stream(
                    text, language=language,
                ):
                    chunks.append(chunk)
            except Exception:
                logger.exception(
                    "TTS generate_stream failed for connector '%s'",
                    self._connector.instance_name,
                )
                return

            if not chunks:
                return

            try:
                pcm, sample_rate = concat_audio_chunks(chunks)
            except VoiceBridgeError:
                logger.exception(
                    "Failed to concatenate TTS chunks for connector '%s'",
                    self._connector.instance_name,
                )
                return

            try:
                ogg = await asyncio.to_thread(
                    encode_pcm_to_opus, pcm, sample_rate,
                )
            except VoiceBridgeError:
                logger.exception(
                    "Voice encode failed for connector '%s'",
                    self._connector.instance_name,
                )
                return
            except Exception:
                logger.exception(
                    "Unexpected error encoding voice for connector '%s'",
                    self._connector.instance_name,
                )
                return

            try:
                result = await self._connector.send_voice(
                    self._identity, ogg, mime_type="audio/ogg",
                )
            except Exception:
                logger.exception(
                    "connector.send_voice raised on '%s'",
                    self._connector.instance_name,
                )
                return

            if not result.ok:
                logger.warning(
                    "Outbound voice send failed on '%s': %s",
                    self._connector.instance_name, result.error,
                )
