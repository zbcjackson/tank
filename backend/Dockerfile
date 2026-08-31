# Tank backend service image.
#
# Build (from backend/):
#   docker build -t tank-backend .
# Run:
#   docker run -p 8000:8000 -e LLM_API_KEY=... tank-backend
#
# The image installs the whole uv workspace (core + contracts + plugins).
# ASR/TTS model files are NOT baked in — engine slots instantiate lazily per
# session, so /api/health works on a bare image. Mount models at runtime to
# enable voice sessions.

# ── Builder: compile wheels that need gcc (e.g. pilk in connector-wechat) ──
FROM python:3.12-slim AS builder
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.11.14

# Workspace sources (manifests first for layer caching).
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY contracts/ contracts/
COPY plugins/ plugins/
COPY core/ core/

# Install the whole workspace — runtime deps only, exactly as locked.
RUN uv sync --frozen --no-dev

# ── Runtime: slim image, no compiler toolchain ──────────────────────────────
FROM python:3.12-slim

# ffmpeg — TTS decode paths (pydub fallback); curl — container healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime; the unified DB (~/.tank/tank.db) and engine caches live
# under the user's home. Mount a volume at /home/tank/.tank to persist.
RUN useradd -m -s /bin/bash tank
COPY --from=builder --chown=tank:tank /app /app
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv
USER tank

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

# Dev runs from core/ too — config.yaml relative paths (../models, ...)
# resolve the same way. find_config_yaml() walks up to /app/core/config.yaml.
WORKDIR /app/core
CMD ["uv", "run", "--no-sync", "tank-backend", "--host", "0.0.0.0", "--port", "8000"]
