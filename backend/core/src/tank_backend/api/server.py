"""Main API Server entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # .env → os.environ before any config loading (covers uvicorn reload path)

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from .approvals import router as approvals_router  # noqa: E402
from .approvals import set_session_manager as set_approvals_session_manager  # noqa: E402
from .metrics import router as metrics_router  # noqa: E402
from .metrics import set_session_manager as set_metrics_session_manager  # noqa: E402
from .router import router, session_manager  # noqa: E402
from .sessions import init_session_store  # noqa: E402
from .sessions import router as sessions_router  # noqa: E402
from .speakers import router as speakers_router  # noqa: E402
from .speakers import set_session_manager  # noqa: E402

# Configure logging to output to console
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ApiServer")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("API Server starting up")
    yield
    # Shutdown
    logger.info("API Server shutting down")
    await session_manager.close_all()


app = FastAPI(title="Tank Voice Assistant API", version="0.1.0", lifespan=lifespan)

app.include_router(router)
app.include_router(speakers_router)
app.include_router(metrics_router)
app.include_router(approvals_router)
app.include_router(sessions_router)
set_session_manager(session_manager)
set_metrics_session_manager(session_manager)
set_approvals_session_manager(session_manager)

# Initialize session store for the REST sessions API
try:
    from ..plugin import AppConfig
    from ..plugin.manager import PluginManager

    _pm = PluginManager()
    _reg = _pm.load_all()
    _cfg = AppConfig(registry=_reg)
    _ctx_raw = _cfg.get_section("context", {})
    init_session_store(
        store_type=_ctx_raw.get("store_type", "file"),
        store_path=_ctx_raw.get("store_path", "~/.tank/sessions"),
    )
except Exception:
    logger.warning("Failed to init session store for REST API", exc_info=True)


@app.get("/health")
async def health_check(detail: bool = False):
    if not detail:
        return {"status": "ok"}

    # Deep health check: aggregate across all active sessions
    components: dict = {}
    overall = "healthy"

    for session_id, assistant in session_manager.iter_sessions():
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
