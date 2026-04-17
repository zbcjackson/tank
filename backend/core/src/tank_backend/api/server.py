"""Main API Server entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # .env → os.environ before any config loading (covers uvicorn reload path)

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from ..context import create_store  # noqa: E402
from ..plugin import AppConfig  # noqa: E402
from ..plugin.manager import PluginManager  # noqa: E402
from .approvals import router as approvals_router  # noqa: E402
from .approvals import set_connection_manager as set_approvals_connection_manager  # noqa: E402
from .conversations import router as conversations_router  # noqa: E402
from .conversations import set_store as set_conversations_store  # noqa: E402
from .manager import ConnectionManager  # noqa: E402
from .metrics import router as metrics_router  # noqa: E402
from .metrics import set_connection_manager as set_metrics_connection_manager  # noqa: E402
from .router import router  # noqa: E402
from .router import set_connection_manager as set_router_connection_manager  # noqa: E402
from .speakers import router as speakers_router  # noqa: E402
from .speakers import set_connection_manager  # noqa: E402

# Configure logging to output to console
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ApiServer")

# --- Single plugin load at startup ---
_plugin_manager = PluginManager()
_registry = _plugin_manager.load_all()
app_config = AppConfig(registry=_registry)

# --- Connection manager (receives app_config, no more PluginManager inside) ---
connection_manager = ConnectionManager(app_config=app_config)

# --- Conversation store for REST API ---
_ctx_raw = app_config.get_section("context", {})
_store = create_store(
    store_type=_ctx_raw.get("store_type", "file"),
    store_path=_ctx_raw.get("store_path", "~/.tank/conversations"),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("API Server starting up")
    yield
    # Shutdown
    logger.info("API Server shutting down")
    await connection_manager.close_all()


app = FastAPI(title="Tank Voice Assistant API", version="0.1.0", lifespan=lifespan)

app.include_router(router)
app.include_router(speakers_router)
app.include_router(metrics_router)
app.include_router(approvals_router)
app.include_router(conversations_router)
set_router_connection_manager(connection_manager)
set_connection_manager(connection_manager)
set_metrics_connection_manager(connection_manager)
set_approvals_connection_manager(connection_manager)
set_conversations_store(_store)


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
