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
    from .base import (
        Connector,
        Identity,
        MessageEvent,
    )
    from .session_mapper import SessionMapper

logger = logging.getLogger("ConnectorManager")


# Match the /api/upload boundary. Oversized images are rejected in the
# connector path with a user-visible message before they hit MediaStore.
_MAX_IMAGE_BYTES = 25 * 1024 * 1024

# Default polite text sent to identities the allowlist rejects. Operators
# can override per-instance via ``unauthorized_reply`` in connector config.
_DEFAULT_UNAUTHORIZED_REPLY = "You're not authorised to use this bot."


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
    ) -> None:
        self._conn_mgr = connection_manager
        self._session_mapper = session_mapper
        self._app_context = app_context
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
        """Route an inbound platform message to the right Assistant."""
        identity = event.identity

        # Allowlist gate — runs before any session resolution or Assistant
        # construction so denied requests cost essentially nothing. Absence
        # of a policy for this instance means allow-all (zero-config case,
        # pre-Phase-6 behaviour).
        policy = self._allowlist_policies.get(source.instance_name)
        if policy is not None:
            verdict = policy.evaluate(identity)
            if verdict.level is not AccessLevel.ALLOW:
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

        user_display = identity.display_name or identity.external_id
        try:
            assistant.process_input(
                text=event.text,
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
            pcm = await asyncio.to_thread(decode_ogg_opus, att.data)
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

        try:
            transcript = await asr_engine.transcribe_once(pcm, sample_rate=16000)
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
