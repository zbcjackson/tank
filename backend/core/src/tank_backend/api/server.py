"""Main API Server entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # .env → os.environ before any config loading (covers uvicorn reload path)

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from ..config.context import AppContext  # noqa: E402
from ..context import create_store  # noqa: E402
from ..plugin import AppConfig  # noqa: E402
from ..plugin.manager import PluginManager  # noqa: E402
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

# Configure logging to output to console
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ApiServer")

# --- Single plugin load at startup ---
_plugin_manager = PluginManager()
_registry = _plugin_manager.load_all()
app_config = AppConfig(registry=_registry)

# --- Conversation store for REST API ---
_store = create_store(
    store_type=app_config.context.store_type,
    store_path=app_config.context.store_path,
)

# --- Job scheduler (opt-in via config.yaml jobs.enabled) ---
_job_store = None
_scheduler = None

if app_config.jobs.enabled:
    from ..jobs.delivery import DeliveryManager
    from ..jobs.runner import AutonomousRunner
    from ..jobs.scheduler import CronScheduler
    from ..jobs.store import JobStore

    _jobs_cfg = app_config.jobs
    _job_store = JobStore(db_path=_jobs_cfg.db_path)
    _job_delivery = DeliveryManager(
        output_dir=_jobs_cfg.output_dir,
        app_config=app_config,
    )
    _job_runner = AutonomousRunner(
        app_config=app_config,
        job_store=_job_store,
        delivery=_job_delivery,
    )
    _scheduler = CronScheduler(
        job_store=_job_store,
        runner=_job_runner,
        max_parallel=_jobs_cfg.max_parallel,
        tick_interval=_jobs_cfg.tick_interval,
    )

    # Load seed file if present
    seed_path = _jobs_cfg.seed_path or "~/.tank/jobs/seed.yaml"
    result = _job_store.load_seed_file(seed_path)
    if result["created"]:
        logger.info("Loaded %d seed jobs: %s", len(result["created"]), ", ".join(result["created"]))
    if result["deleted"]:
        logger.info(
            "Removed %d stale seed jobs: %s",
            len(result["deleted"]), ", ".join(result["deleted"]),
        )

    logger.info("Job scheduler initialized (max_parallel=%d)", _jobs_cfg.max_parallel)
else:
    logger.info("Job scheduler disabled (jobs.enabled=false)")

# --- AppContext: single object holding all app-level singletons ---
app_context = AppContext(
    app_config=app_config,
    job_store=_job_store,
    scheduler=_scheduler,
    conversation_store=_store,
)

# --- Connection manager ---
connection_manager = ConnectionManager(app_config=app_config, app_context=app_context)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("API Server starting up")
    if _scheduler is not None:
        await _scheduler.start()
    yield
    # Shutdown
    logger.info("API Server shutting down")
    if _scheduler is not None:
        await _scheduler.stop()
    if _job_store is not None:
        _job_store.close()
    await connection_manager.close_all()


app = FastAPI(title="Tank Voice Assistant API", version="0.1.0", lifespan=lifespan)

app.include_router(router)
app.include_router(speakers_router)
app.include_router(users_router)
app.include_router(metrics_router)
app.include_router(conversations_router)
app.include_router(skills_router)
app.include_router(jobs_router)
set_router_connection_manager(connection_manager)
set_connection_manager(connection_manager)
set_metrics_connection_manager(connection_manager)
set_skills_connection_manager(connection_manager)
set_users_connection_manager(connection_manager)
set_conversations_store(_store)
if _job_store is not None:
    set_job_store(_job_store)
if _scheduler is not None:
    set_jobs_scheduler(_scheduler)
if _job_store is not None and _scheduler is not None:
    connection_manager.set_job_manager(_job_store, _scheduler)


@app.get("/health")
async def health_check(detail: bool = False):
    """Health check endpoint."""
    if not detail:
        return {"status": "ok"}

    # Deep health check: aggregate across all active sessions
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
