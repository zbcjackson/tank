"""Main API Server entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .router import router, session_manager

# Configure logging to output to console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ApiServer")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("API Server starting up")
    yield
    # Shutdown
    logger.info("API Server shutting down")
    session_manager.close_all()

app = FastAPI(
    title="Tank Voice Assistant API",
    version="0.1.0",
    lifespan=lifespan
)

app.include_router(router)

@app.get("/health")
async def health_check():
    return {"status": "ok"}
