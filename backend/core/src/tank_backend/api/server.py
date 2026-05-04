"""Main API Server entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ..channels.store import ChannelStore
from ..config import AppConfig, find_config_yaml
from ..config.context import AppContext
from ..context import create_store
from ..plugin.manager import PluginManager
from ..plugin.registry import ExtensionRegistry

if TYPE_CHECKING:
    from ..audio.input.voiceprint import VoiceprintRecognizer
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


def _init_conversation_store(config: AppConfig) -> ConversationStore | None:
    return create_store(
        store_type=config.context.store_type,
        store_path=config.context.store_path,
    )


def _init_job_scheduler(
    config: AppConfig,
    channel_store: ChannelStore | None = None,
    conversation_store: ConversationStore | None = None,
) -> tuple[JobStore | None, CronScheduler | None, DeliveryManager | None]:
    if not config.jobs.enabled:
        logger.info("Job scheduler disabled (jobs.enabled=false)")
        return None, None, None

    from ..jobs.delivery import DeliveryManager
    from ..jobs.runner import AutonomousRunner
    from ..jobs.scheduler import CronScheduler
    from ..jobs.store import JobStore

    jobs_cfg = config.jobs
    job_store = JobStore(db_path=jobs_cfg.db_path)
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
    config: AppConfig, registry: ExtensionRegistry,
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
        recognizer = create_voiceprint_recognizer(extractor, speaker_cfg.config)
        logger.info("Shared voiceprint recognizer initialized")
        return recognizer
    except Exception as e:
        logger.warning("Failed to initialize voiceprint recognizer: %s", e)
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
_store = _init_conversation_store(app_config)

# Channel store (before job scheduler, so jobs can deliver to channels)
_channel_store: ChannelStore | None = None
if app_config.channels.enabled:
    try:
        _channel_store = ChannelStore(app_config.channels.db_path)
        logger.info("Channel store initialized at %s", app_config.channels.db_path)
    except Exception as e:
        logger.warning("Failed to initialize channel store: %s", e)

_job_store, _scheduler, _delivery = _init_job_scheduler(
    app_config, channel_store=_channel_store, conversation_store=_store,
)
_voiceprint_recognizer = _init_voiceprint_recognizer(app_config, _registry)

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

# Initialise the composition root — all API modules use deps.* from here on
deps.init(app_context, connection_manager)

# Wire broadcast into delivery manager (created before ConnectionManager)
if _delivery is not None:
    _delivery.set_connection_manager(connection_manager)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API Server starting up")
    if _scheduler is not None:
        await _scheduler.start()
    yield
    logger.info("API Server shutting down")
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
