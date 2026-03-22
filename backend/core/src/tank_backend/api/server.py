"""Main API Server entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # .env → os.environ before any config loading (covers uvicorn reload path)

from fastapi import FastAPI  # noqa: E402

from .metrics import router as metrics_router  # noqa: E402
from .metrics import set_session_manager as set_metrics_session_manager  # noqa: E402
from .router import router, session_manager  # noqa: E402
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
set_session_manager(session_manager)
set_metrics_session_manager(session_manager)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
