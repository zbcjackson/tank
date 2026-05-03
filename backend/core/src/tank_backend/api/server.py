"""Main API Server entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv

load_dotenv()  # .env → os.environ before any config loading (covers uvicorn reload path)

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from ..config import AppConfig, find_config_yaml  # noqa: E402
from ..config.context import AppContext  # noqa: E402
from ..context import create_store  # noqa: E402
from ..plugin.manager import PluginManager  # noqa: E402
from ..plugin.registry import ExtensionRegistry  # noqa: E402
from .channels import router as channels_router  # noqa: E402
from .channels import set_channel_store  # noqa: E402
from .channels import set_conversation_store as set_channels_conversation_store  # noqa: E402
from .conversations import router as conversations_router  # noqa: E402
from .conversations import set_store as set_conversations_store  # noqa: E402
from .jobs import router as jobs_router  # noqa: E402
from .jobs import set_job_store  # noqa: E402
from .jobs import set_scheduler as set_jobs_scheduler  # noqa: E402
from .manager import ConnectionManager  # noqa: E402
from .metrics import router as metrics_router  # noqa: E402
from .metrics import set_connection_manager as set_metrics_connection_manager  # noqa: E402
from .router import router  # noqa: E402
from .router import set_connection_manager as set_router_connection_manager  # noqa: E402
from .skills import router as skills_router  # noqa: E402
from .skills import set_connection_manager as set_skills_connection_manager  # noqa: E402
from .speakers import router as speakers_router  # noqa: E402
from .speakers import set_connection_manager  # noqa: E402
from .users import router as users_router  # noqa: E402
from .users import set_connection_manager as set_users_connection_manager  # noqa: E402

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


def _init_conversation_store(config: AppConfig) -> Any:
    return create_store(
        store_type=config.context.store_type,
        store_path=config.context.store_path,
    )


def _init_job_scheduler(
    config: AppConfig,
    channel_store: Any | None = None,
    conversation_store: Any | None = None,
) -> tuple[Any, Any]:
    if not config.jobs.enabled:
        logger.info("Job scheduler disabled (jobs.enabled=false)")
        return None, None

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
    return job_store, scheduler


def _init_voiceprint_recognizer(
    config: AppConfig, registry: ExtensionRegistry,
) -> Any | None:
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


def _wire_routers(
    app: FastAPI,
    mgr: ConnectionManager,
    store: Any,
    job_store: Any | None,
    scheduler: Any | None,
    channel_store: Any | None,
) -> None:
    app.include_router(router)
    app.include_router(speakers_router)
    app.include_router(users_router)
    app.include_router(metrics_router)
    app.include_router(conversations_router)
    app.include_router(skills_router)
    app.include_router(jobs_router)
    app.include_router(channels_router)

    set_router_connection_manager(mgr)
    set_connection_manager(mgr)
    set_metrics_connection_manager(mgr)
    set_skills_connection_manager(mgr)
    set_users_connection_manager(mgr)
    set_conversations_store(store)
    if job_store is not None:
        set_job_store(job_store)
    if scheduler is not None:
        set_jobs_scheduler(scheduler)
    if channel_store is not None:
        set_channel_store(channel_store)
        set_channels_conversation_store(store)


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

app_config, _registry = _init_plugins()
_store = _init_conversation_store(app_config)

# Channel store (before job scheduler, so jobs can deliver to channels)
from ..channels.store import ChannelStore  # noqa: E402

_channel_store: Any = None
if app_config.channels.enabled:
    try:
        _channel_store = ChannelStore(app_config.channels.db_path)
        logger.info("Channel store initialized at %s", app_config.channels.db_path)
    except Exception as e:
        logger.warning("Failed to initialize channel store: %s", e)

_job_store, _scheduler = _init_job_scheduler(
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
_wire_routers(app, connection_manager, _store, _job_store, _scheduler, _channel_store)


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
