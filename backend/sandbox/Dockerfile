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

# Node.js 20 LTS (binary tarball — avoids NodeSource TLS issues)
ARG NODE_VERSION=20.18.1
RUN ARCH=$(dpkg --print-architecture) \
    && if [ "$ARCH" = "arm64" ]; then NODE_ARCH=arm64; else NODE_ARCH=x64; fi \
    && curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz" \
       | tar -xJ --strip-components=1 -C /usr/local

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
