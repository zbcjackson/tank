"""Main API Server entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ..channels.store import ChannelStore
from ..channels.subscription import ChannelSubscriptionManager
from ..config import AppConfig, find_config_yaml
from ..config.context import AppContext
from ..context import create_store
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


def _init_channel_audio_service(
    config: AppConfig,
    registry: ExtensionRegistry,
    subscription_manager: ChannelSubscriptionManager,
    connection_manager: ConnectionManager,
) -> ChannelAudioService | None:
    """Build the channel audio service if TTS is enabled and wired correctly."""
    tts_slot = config.tts
    if not tts_slot.enabled or tts_slot.extension is None:
        return None

    try:
        from tank_contracts.tts import TTSEngine

        from ..channels.audio_service import ChannelAudioService

        engine = registry.instantiate(tts_slot.extension, tts_slot.config)
        if not isinstance(engine, TTSEngine):
            logger.warning("TTS extension did not produce a TTSEngine instance")
            return None

        service = ChannelAudioService(
            tts_engine=engine,
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

app_context = AppContext(
    app_config=app_config,
    registry=_registry,
    job_store=_job_store,
    scheduler=_scheduler,
    conversation_store=_store,
    voiceprint_recognizer=_voiceprint_recognizer,
    channel_store=_channel_store,
)
connection_manager = ConnectionManager(app_context=app_context)

_subscription_manager = ChannelSubscriptionManager()

# Build the channel audio service before wiring deps so the composition root
# is initialised exactly once.
_channel_audio_service = _init_channel_audio_service(
    app_config, _registry, _subscription_manager, connection_manager,
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
    yield
    logger.info("API Server shutting down")
    if _channel_audio_service is not None:
        await _channel_audio_service.stop()
    if _scheduler is not None:
        await _scheduler.stop()
    if _job_store is not None:
        _job_store.close()
    await connection_manager.close_all()


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
