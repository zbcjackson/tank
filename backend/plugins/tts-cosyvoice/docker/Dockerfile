# CosyVoice CPU-only Docker image (ARM64 / x86_64)
#
# Build:
#   docker build -t tank-cosyvoice:latest .
#
# Run:
#   docker run -d -p 50000:50000 --name tank-cosyvoice tank-cosyvoice:latest
#
# The image is ~4 GB due to PyTorch + model weights.

FROM python:3.10-slim AS base

ARG MODEL_DIR=iic/CosyVoice-300M-SFT

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    MODEL_DIR=${MODEL_DIR}

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        git-lfs \
        sox \
        libsox-dev \
        build-essential \
    && git lfs install \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/cosyvoice

# Clone CosyVoice with submodules
RUN git clone --depth 1 --recurse-submodules \
        https://github.com/FunAudioLLM/CosyVoice.git . \
    && rm -rf .git

# Pin pip<25 — pip 26+ removed vendored pkg_resources which breaks
# openai-whisper's setup.py. setuptools is needed for pkg_resources.
RUN pip install --no-cache-dir "pip<25" setuptools \
    && pip install --no-cache-dir \
        torch torchaudio \
        --index-url https://download.pytorch.org/whl/cpu

# Strip GPU/CUDA packages and problematic packages from requirements.txt,
# then install the remaining CPU-compatible deps.
# openai-whisper is installed separately with --no-build-isolation because
# its setup.py uses pkg_resources which newer setuptools ships as a
# separate package not available inside pip's build isolation env.
RUN sed -i \
        -e '/^--extra-index-url/d' \
        -e '/onnxruntime-gpu/d' \
        -e '/onnxruntime==/d' \
        -e '/tensorrt/d' \
        -e '/^torch==/d' \
        -e '/^torchaudio==/d' \
        -e '/deepspeed/d' \
        -e '/openai-whisper/d' \
        requirements.txt \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --no-build-isolation openai-whisper==20231117 \
    && pip install --no-cache-dir onnxruntime

# Pre-download model at build time (optional — comment out to download at first run)
RUN python3 -c "\
from modelscope import snapshot_download; \
snapshot_download('${MODEL_DIR}', local_dir='pretrained_models/${MODEL_DIR}')" \
    || echo "Model download skipped (will download at first run)"

EXPOSE 50000

CMD python3 runtime/python/fastapi/server.py --port 50000 --model_dir ${MODEL_DIR}
