"""Main API Server entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from ..channels.store import ChannelStore
from ..channels.subscription import ChannelSubscriptionManager
from ..config import AppConfig, find_config_yaml
from ..config.context import AppContext
from ..context import create_store
from ..media import MediaStore
from ..persistence import Database, bootstrap_legacy_data, run_migrations
from ..plugin.manager import PluginManager
from ..plugin.registry import ExtensionRegistry

if TYPE_CHECKING:
    from ..audio.input.voiceprint import VoiceprintRecognizer
    from ..channels.audio_service import ChannelAudioService
    from ..context.store import ConversationStore
    from ..jobs.delivery import DeliveryManager
    from ..jobs.scheduler import CronScheduler
    from ..jobs.store import JobStore

from . import deps
from .channels import router as channels_router
from .conversations import router as conversations_router
from .jobs import router as jobs_router
from .manager import ConnectionManager
from .metrics import router as metrics_router
from .router import router
from .skills import router as skills_router
from .speakers import router as speakers_router
from .users import router as users_router

if TYPE_CHECKING:
    from tank_contracts import ASREngine, TTSEngine

    from ..audio.input.vad import VADEngine
    from ..connectors import ConnectorManager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ApiServer")


# ---------------------------------------------------------------------------
# Initialization helpers — each encapsulates one startup concern
# ---------------------------------------------------------------------------


def _init_plugins() -> tuple[AppConfig, ExtensionRegistry]:
    plugin_manager = PluginManager()
    registry = plugin_manager.load_all()
    config = AppConfig.load(find_config_yaml(), registry=registry)
    return config, registry


def _init_stores(
    config: AppConfig,
    db: Database,
) -> tuple[ConversationStore | None, ChannelStore | None]:
    """Create conversation and channel stores."""
    conversation = create_store(enabled=config.context.persist, db=db)
    channel: ChannelStore | None = None
    if config.channels.enabled:
        try:
            channel = ChannelStore(db)
            logger.info("Channel store initialized on unified DB")
        except Exception as e:
            logger.warning("Failed to initialize channel store: %s", e)
    return conversation, channel


def _init_job_scheduler(
    config: AppConfig,
    stores: tuple[ConversationStore | None, ChannelStore | None],
    db: Database,
) -> tuple[JobStore | None, CronScheduler | None, DeliveryManager | None]:
    if not config.jobs.enabled:
        logger.info("Job scheduler disabled (jobs.enabled=false)")
        return None, None, None

    from ..jobs.delivery import DeliveryManager
    from ..jobs.runner import AutonomousRunner
    from ..jobs.scheduler import CronScheduler
    from ..jobs.store import JobStore

    conversation_store, channel_store = stores
    jobs_cfg = config.jobs
    job_store = JobStore(db)
    delivery = DeliveryManager(
        output_dir=jobs_cfg.output_dir,
        app_config=config,
        channel_store=channel_store,
        conversation_store=conversation_store,
    )
    runner = AutonomousRunner(
        app_config=config, job_store=job_store, delivery=delivery,
    )
    scheduler = CronScheduler(
        job_store=job_store,
        runner=runner,
        max_parallel=jobs_cfg.max_parallel,
        tick_interval=jobs_cfg.tick_interval,
    )

    seed_path = jobs_cfg.seed_path or "~/.tank/jobs/seed.yaml"
    result = job_store.load_seed_file(seed_path)
    if result["created"]:
        logger.info(
            "Loaded %d seed jobs: %s",
            len(result["created"]), ", ".join(result["created"]),
        )
    if result["deleted"]:
        logger.info(
            "Removed %d stale seed jobs: %s",
            len(result["deleted"]), ", ".join(result["deleted"]),
        )

    logger.info("Job scheduler initialized (max_parallel=%d)", jobs_cfg.max_parallel)
    return job_store, scheduler, delivery


def _init_voiceprint_recognizer(
    config: AppConfig, registry: ExtensionRegistry, db: Database,
) -> VoiceprintRecognizer | None:
    try:
        from ..audio.input.voiceprint_factory import (
            create_disabled_recognizer,
            create_voiceprint_recognizer,
        )

        speaker_cfg = config.get_feature_config("speaker")
        if not speaker_cfg.enabled or not speaker_cfg.extension:
            return create_disabled_recognizer()

        extractor = registry.instantiate(speaker_cfg.extension, speaker_cfg.config)
        recognizer = create_voiceprint_recognizer(extractor, speaker_cfg.config, db)
        logger.info("Shared voiceprint recognizer initialized")
        return recognizer
    except Exception as e:
        logger.warning("Failed to initialize voiceprint recognizer: %s", e)
        return None


def _init_audio_engines(
    config: AppConfig, registry: ExtensionRegistry,
) -> tuple[ASREngine | None, TTSEngine | None, VADEngine | None]:
    """Build process-global ASR/TTS/VAD engines once at startup.

    Returns (asr_engine, tts_engine, vad_engine). Each may be None when the
    corresponding feature is disabled or plugin instantiation fails.
    """
    from tank_contracts import ASREngine, TTSEngine

    from ..audio.input.vad import VADEngine

    asr_engine: ASREngine | None = None
    asr_slot = config.asr
    if asr_slot.enabled and asr_slot.extension is not None:
        try:
            engine = registry.instantiate(asr_slot.extension, asr_slot.config)
            if isinstance(engine, ASREngine):
                asr_engine = engine
                logger.info("Shared ASR engine initialized: %s", asr_slot.extension)
            else:
                logger.warning(
                    "ASR extension %s did not produce an ASREngine instance",
                    asr_slot.extension,
                )
        except Exception:
            logger.warning("Failed to initialize ASR engine", exc_info=True)

    tts_engine: TTSEngine | None = None
    tts_slot = config.tts
    if tts_slot.enabled and tts_slot.extension is not None:
        try:
            engine = registry.instantiate(tts_slot.extension, tts_slot.config)
            if isinstance(engine, TTSEngine):
                tts_engine = engine
                logger.info("Shared TTS engine initialized: %s", tts_slot.extension)
            else:
                logger.warning(
                    "TTS extension %s did not produce a TTSEngine instance",
                    tts_slot.extension,
                )
        except Exception:
            logger.warning("Failed to initialize TTS engine", exc_info=True)

    vad_engine: VADEngine | None = None
    try:
        vad_engine = VADEngine()
    except Exception:
        logger.warning("Failed to initialize VAD engine", exc_info=True)

    return asr_engine, tts_engine, vad_engine


def _init_connectors(
    config: AppConfig,
    registry: ExtensionRegistry,
    connection_manager: ConnectionManager,
    channel_store: ChannelStore | None,
    conversation_store: ConversationStore | None,
    database: Database,
    app_context: AppContext,
) -> ConnectorManager | None:
    """Build :class:`ConnectorManager` from ``config.yaml`` ``connectors:``.

    Returns ``None`` when no connectors are configured — the existing
    WebSocket entrypoint remains the only entrypoint in that case, and
    no connector machinery is loaded.
    """
    instances = config.connectors.instances
    if not instances:
        return None

    if channel_store is None or conversation_store is None:
        logger.warning(
            "Connectors configured but ChannelStore/ConversationStore "
            "unavailable — skipping connector initialization",
        )
        return None

    from ..connectors import (
        ApprovalBroker,
        ConnectorIdentityStore,
        ConnectorManager,
        DynamicAllowlistStore,
        SessionMapper,
    )
    from ..connectors.base import Connector
    from ..policy.connector_access import (
        ConnectorAllowlistPolicy,
        parse_allowlist,
    )

    identity_store = ConnectorIdentityStore(database)
    # Phase 10: shared across every connector instance. One SQLite table
    # backs every "Allow forever" grant; per-instance isolation comes
    # from the ``instance_name`` column, not from separate store objects.
    dynamic_allowlist_store = DynamicAllowlistStore(database)
    session_mapper = SessionMapper(
        identity_store=identity_store,
        channel_store=channel_store,
        conversation_store=conversation_store,
    )
    manager = ConnectorManager(
        connection_manager=connection_manager,
        session_mapper=session_mapper,
        app_context=app_context,
        dynamic_allowlist_store=dynamic_allowlist_store,
    )

    for inst in instances:
        if not inst.enabled:
            logger.info("Connector '%s' disabled — skipping", inst.instance)
            continue
        try:
            connector = registry.instantiate(
                inst.extension,
                {
                    "instance": inst.instance,
                    "config": inst.config,
                },
            )
        except Exception:
            logger.exception(
                "Failed to instantiate connector '%s' (extension=%s)",
                inst.instance, inst.extension,
            )
            continue

        if not isinstance(connector, Connector):
            logger.warning(
                "Connector '%s' (extension=%s) did not produce a Connector instance",
                inst.instance, inst.extension,
            )
            continue

        manager.register(connector)

        # Phase 6: attach per-instance allowlist policy if configured.
        # Missing ``allowlist`` key → allow-all (pre-Phase-6 behaviour);
        # malformed ``allowlist`` raises ConfigError at parse time so
        # operators fail fast at startup rather than silently letting
        # everyone through (or locking everyone out).
        #
        # Phase 10: the policy also consults ``dynamic_allowlist_store``
        # before rule evaluation so admin-granted ``Allow forever``
        # rows short-circuit to ALLOW. Per-instance admin identities
        # from the allowlist config spin up an :class:`ApprovalBroker`
        # for the REQUIRE_APPROVAL path; without admins, a
        # REQUIRE_APPROVAL verdict fails closed with a warning.
        #
        # Decisions are still logged at INFO level via the manager's
        # ``_on_inbound`` path — a proper audit Bus for connector-level
        # decisions is deferred until the audit subsystem grows an
        # app-scoped Bus (today's Bus is per-Assistant).
        allowlist_cfg = inst.config.get("allowlist")
        if allowlist_cfg:
            parsed = parse_allowlist(
                allowlist_cfg, instance_name=inst.instance,
            )
            policy = ConnectorAllowlistPolicy(
                parsed,
                instance_name=inst.instance,
                dynamic_store=dynamic_allowlist_store,
            )
            manager.set_allowlist_policy(inst.instance, policy)

            # Phase 10: spin up an ApprovalBroker when admins are
            # configured. The broker's ``dispatch`` callback points at
            # the manager's own ``_on_inbound`` so replays re-enter the
            # allowlist gate — the one-shot set or dynamic grant
            # short-circuits the replayed event through.
            if parsed.admin_external_ids:
                one_shot_set = manager._one_shot_set_for(inst.instance)  # noqa: SLF001
                broker = ApprovalBroker(
                    instance_name=inst.instance,
                    admin_external_ids=parsed.admin_external_ids,
                    dynamic_store=dynamic_allowlist_store,
                    dispatch=manager._on_inbound,  # noqa: SLF001 — intentional shared dispatch
                    one_shot_passes=one_shot_set,
                )
                manager.set_approval_broker(inst.instance, broker)

            if parsed.pending_reply:
                manager.set_pending_reply(inst.instance, parsed.pending_reply)

        unauthorized_reply = inst.config.get("unauthorized_reply")
        if isinstance(unauthorized_reply, str) and unauthorized_reply.strip():
            manager.set_unauthorized_reply(inst.instance, unauthorized_reply)

    return manager


def _init_channel_audio_service(
    tts_engine: TTSEngine | None,
    subscription_manager: ChannelSubscriptionManager,
    connection_manager: ConnectionManager,
) -> ChannelAudioService | None:
    """Build the channel audio service if a shared TTS engine is available."""
    if tts_engine is None:
        return None

    try:
        from ..channels.audio_service import ChannelAudioService

        service = ChannelAudioService(
            tts_engine=tts_engine,
            subscription_manager=subscription_manager,
            connection_manager=connection_manager,
        )
        logger.info("Channel audio service initialized")
        return service
    except Exception:
        logger.warning("Failed to create channel audio service", exc_info=True)
        return None


def _wire_routers(app: FastAPI) -> None:
    app.include_router(router)
    app.include_router(speakers_router)
    app.include_router(users_router)
    app.include_router(metrics_router)
    app.include_router(conversations_router)
    app.include_router(skills_router)
    app.include_router(jobs_router)
    app.include_router(channels_router)


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv()  # .env → os.environ before any config loading (covers uvicorn reload path)

app_config, _registry = _init_plugins()

# Unified persistence. Alembic brings the schema to head, then the
# first-run bootstrap copies data from any legacy per-module DBs and
# renames them to .bak. Both are idempotent and safe on every startup.
run_migrations(app_config.database.url)
_database = Database(app_config.database.url, echo=app_config.database.echo)
bootstrap_legacy_data(_database)

_store, _channel_store = _init_stores(app_config, _database)

_job_store, _scheduler, _delivery = _init_job_scheduler(
    app_config, (_store, _channel_store), _database,
)
_voiceprint_recognizer = _init_voiceprint_recognizer(app_config, _registry, _database)

_asr_engine, _tts_engine, _vad_engine = _init_audio_engines(app_config, _registry)

_media_store = MediaStore(Path("~/.tank/media").expanduser())

# Resolve LLM capabilities once at startup. Read by:
#   - POST /api/upload (capability-gated upload)
#   - ConnectorManager (capability-gated inbound images)
try:
    from ..llm.capabilities import resolve_capabilities_sync

    _llm_capabilities = resolve_capabilities_sync(
        app_config.get_llm_profile("default"),
    )
    logger.info(
        "LLM capabilities resolved: modalities=%s source=%s",
        sorted(_llm_capabilities.input_modalities),
        _llm_capabilities.source.value,
    )
except Exception:
    logger.warning("Failed to resolve LLM capabilities", exc_info=True)
    _llm_capabilities = None

app_context = AppContext(
    app_config=app_config,
    registry=_registry,
    job_store=_job_store,
    scheduler=_scheduler,
    conversation_store=_store,
    voiceprint_recognizer=_voiceprint_recognizer,
    channel_store=_channel_store,
    media_store=_media_store,
    asr_engine=_asr_engine,
    tts_engine=_tts_engine,
    vad_engine=_vad_engine,
    llm_capabilities=_llm_capabilities,
)
connection_manager = ConnectionManager(app_context=app_context)

_connector_manager = _init_connectors(
    app_config, _registry, connection_manager, _channel_store, _store, _database,
    app_context,
)

_subscription_manager = ChannelSubscriptionManager()

# Build the channel audio service before wiring deps so the composition root
# is initialised exactly once.
_channel_audio_service = _init_channel_audio_service(
    _tts_engine, _subscription_manager, connection_manager,
)

if _delivery is not None:
    _delivery.set_connection_manager(connection_manager)
    if _channel_audio_service is not None:
        _delivery.set_channel_audio_service(_channel_audio_service)

deps.init(
    app_context,
    connection_manager,
    _subscription_manager,
    _channel_audio_service,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API Server starting up")
    if _scheduler is not None:
        await _scheduler.start()
    if _connector_manager is not None:
        await _connector_manager.start_all()
    yield
    logger.info("API Server shutting down")
    if _connector_manager is not None:
        await _connector_manager.stop_all()
    if _channel_audio_service is not None:
        await _channel_audio_service.stop()
    if _scheduler is not None:
        await _scheduler.stop()
    if _job_store is not None:
        _job_store.close()
    await connection_manager.close_all()
    if _asr_engine is not None:
        try:
            _asr_engine.close()
        except Exception:
            logger.warning("ASR engine close failed", exc_info=True)
    if _vad_engine is not None:
        try:
            _vad_engine.close()
        except Exception:
            logger.warning("VAD engine close failed", exc_info=True)


app = FastAPI(title="Tank Voice Assistant API", version="0.1.0", lifespan=lifespan)
_wire_routers(app)


@app.get("/health")
async def health_check(detail: bool = False):
    """Health check endpoint."""
    if not detail:
        return {"status": "ok"}

    components: dict = {}
    overall = "healthy"

    for session_id, assistant in connection_manager.iter_sessions():
        session_health = assistant.health_snapshot()
        pipeline_info = session_health.get("pipeline")
        if pipeline_info and not pipeline_info.get("is_healthy", True):
            overall = "degraded"
        components[session_id] = session_health

    status_code = 200 if overall == "healthy" else 503
    return JSONResponse(
        content={"status": overall, "sessions": components},
        status_code=status_code,
    )


@app.get("/api/capabilities")
async def llm_capabilities() -> dict:
    """Return input modalities the configured LLM can consume.

    Clients (web upload, CLI file-send) call this once on connect to
    gate file uploads at the boundary rather than bouncing a request
    through the LLM only to find it can't see the attachment.

    Capability is fixed at server startup — LLM profile is immutable
    until restart — so a cached response per session is fine.
    """
    from ..llm.capabilities import resolve_capabilities_sync

    profile = app_config.get_llm_profile("default")
    caps = resolve_capabilities_sync(profile)
    return {
        "model_id": caps.model_id,
        "input_modalities": sorted(caps.input_modalities),
        "source": caps.source.value,
    }


# Upload size cap. Images/PDFs over this are rejected at the boundary
# rather than paid for through the LLM. Tune from config if needed.
_UPLOAD_MAX_BYTES = 25 * 1024 * 1024


@app.post("/api/upload")
async def upload_media(
    file: UploadFile,
    session_id: str,
) -> dict:
    """Store an uploaded file and return its ``media://`` URI.

    Capability-gated: the current LLM must accept the file's modality
    (image/file/audio/video). Unsupported MIME types are rejected with
    HTTP 415 so the client can show a clear error before the bytes
    leave the browser.

    Session-scoped: media is written under ``~/.tank/media/<session>/``
    and references can only be resolved back for the same session.
    """
    from ..core.content import modality_for_mime
    from ..llm.capabilities import resolve_capabilities_sync
    from ..media.office import IWORK_MIME_TYPES

    mime_type = file.content_type or "application/octet-stream"

    # iWork formats: helpful hint rather than a generic 415. Users
    # AirDropping from a Mac often end up here without realising
    # Pages/Numbers/Keynote aren't a common interchange format.
    if mime_type in IWORK_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"{mime_type} isn't supported. Export to PDF "
                "(File → Export To → PDF…) and try again."
            ),
        )

    modality = modality_for_mime(mime_type)
    if modality is None:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported MIME type: {mime_type}",
        )

    profile = app_config.get_llm_profile("default")
    caps = resolve_capabilities_sync(profile)
    if modality not in caps.input_modalities:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Current model ({caps.model_id}) cannot accept {modality} "
                f"input. Supported: {sorted(caps.input_modalities)}."
            ),
        )

    data = await file.read()
    if len(data) > _UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File too large: {len(data)} bytes > "
                f"{_UPLOAD_MAX_BYTES} bytes limit."
            ),
        )
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload.")

    stored = await _media_store.put(data, mime_type, session_id=session_id)
    return {
        "media_uri": stored.media_uri,
        "mime_type": stored.mime_type,
        "size": stored.size,
        "modality": modality,
    }
