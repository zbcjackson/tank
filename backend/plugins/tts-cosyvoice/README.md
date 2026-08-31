# CosyVoice TTS Plugin

CosyVoice TTS plugin for Tank Voice Assistant — self-hosted server or Alibaba
DashScope cloud.

## Overview

Implements the `TTSEngine` interface from `tank_contracts.tts` with two
providers (selected by the `provider` config key):

- **`local`** (default) — POSTs to a self-hosted CosyVoice FastAPI server and
  streams the response body. Supports `sft`, `zero_shot`, and `instruct2`
  modes. With `docker: true`, the plugin builds the image, starts the
  container, waits for health (up to `docker_health_timeout` seconds), and
  stops it via an `atexit` hook.
- **`dashscope`** — Alibaba DashScope CosyVoice API over a duplex WebSocket
  (`run-task` → `continue-task` → `finish-task`), requesting raw PCM.

**Streaming**: both providers stream audio incrementally — the local provider
reads the HTTP response in 4 KB blocks, the DashScope provider yields binary
WebSocket frames as they arrive.

## Language support

Bilingual (zh/en). Language maps to a speaker/voice via the `voices` map with
prefix matching (`zh-CN` → `zh`) and a default fallback. In DashScope mode the
per-language voice is sent to the API; in `sft` mode the per-language speaker ID
is sent.

## Installation

```bash
cd backend
uv sync
```

For the `local` provider with Docker, build the image once (~4 GB; see
`docker/Dockerfile`):

```bash
docker build -t tank-cosyvoice:latest docker/
```

## Configuration

Configure in `backend/core/config.yaml` (see `config.example.yaml`):

```yaml
tts:
  enabled: true
  extension: tts-cosyvoice:tts
  config:
    docker: true                       # auto-manage Docker container
    docker_image: tank-cosyvoice:latest
    docker_container: tank-cosyvoice
    port: 50000
    model_dir: iic/CosyVoice-300M-SFT
    mode: sft                          # "sft", "zero_shot", or "instruct2"
    spk_id_en: 英文女
    spk_id_zh: 中文女
    sample_rate: 22050
    timeout_s: 120
    # zero_shot mode only:
    # prompt_text: "Hello, this is a test."
    # prompt_wav_path: /path/to/prompt.wav
```

| Key | Default | Notes |
|-----|---------|-------|
| `provider` | `local` | `local` or `dashscope` |
| `base_url` | `http://localhost:50000` | Local server URL (set automatically in Docker mode) |
| `mode` | `sft` | `sft` / `zero_shot` / `instruct2` |
| `spk_id_en` / `spk_id_zh` | `英文女` / `中文女` | sft speaker IDs (legacy keys, still honored) |
| `default_voice` | `spk_id_en` | Fallback when language is unknown |
| `prompt_text` / `prompt_wav_path` | `""` | zero_shot prompt transcript + WAV |
| `instruct_text` | `""` | instruct2 style instruction |
| `sample_rate` | `22050` | Output PCM rate (server emits 22050 Hz) |
| `timeout_s` | `120` | HTTP timeout |
| `docker` / `docker_image` / `docker_container` / `port` / `model_dir` / `docker_health_timeout` | `false` / `tank-cosyvoice:latest` / `tank-cosyvoice` / `50000` / `iic/CosyVoice-300M-SFT` / `300` | Docker management |
| `dashscope_api_key` | — (required for dashscope) | DashScope API key |
| `dashscope_model` | `cosyvoice-v3-flash` | DashScope model |
| `dashscope_voice_en` / `dashscope_voice_zh` | `longanyang` | DashScope voices |
| `dashscope_region` | `intl` | `intl` (Singapore) or `cn` (Beijing) |

## Dependencies

- **httpx>=0.27.0** — local server HTTP streaming client
- **websockets>=12.0** — DashScope WebSocket client
- **numpy>=1.24.0**, **sounddevice>=0.4.6** — used by the `cosyvoice-say` CLI
- **tank-contracts** (workspace)
- **Docker** + the `tank-cosyvoice:latest` image — only for `docker: true`

## Usage

Loaded automatically via the `tts-cosyvoice:tts` extension. A standalone CLI
is also installed for quick checks:

```bash
cosyvoice-say "你好，世界" --url http://localhost:50000 --lang auto
```

`task-failed` events in DashScope mode raise `DashScopeError`; HTTP errors in
local mode raise via `response.raise_for_status()`.

## Testing

```bash
cd backend/plugins/tts-cosyvoice
uv run pytest
```

`pytest.ini` sets `asyncio_mode = "auto"`. Suites (`tests/`): engine factory +
mode routing (`test_engine.py`), DashScope protocol (`test_dashscope_client.py`),
Docker lifecycle (`test_server.py`), and end-to-end function tests
(`test_function.py`). Servers and HTTP calls are mocked; no Docker or network
is needed.
