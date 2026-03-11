FROM python:3.12-slim

# System packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    curl \
    git \
    build-essential \
    jq \
    wget \
    unzip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Node.js 20 LTS
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Common Python packages
RUN pip install --no-cache-dir \
    requests \
    httpx \
    numpy \
    pandas

# Non-root user
RUN groupadd -r sandbox && useradd -r -g sandbox -m -s /bin/bash sandbox

# Workspace directory
RUN mkdir -p /workspace && chown sandbox:sandbox /workspace
WORKDIR /workspace

USER sandbox

# Keep container alive
CMD ["sleep", "infinity"]
