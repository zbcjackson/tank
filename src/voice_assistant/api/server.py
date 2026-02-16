"""Main API Server entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .router import router, session_manager

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
