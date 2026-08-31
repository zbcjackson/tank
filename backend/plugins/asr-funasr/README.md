# FunASR ASR Plugin

Streaming ASR plugin for Tank Voice Assistant — self-hosted FunASR server or Alibaba DashScope cloud.

## Overview

One `ASREngine` implementation with two backends, auto-detected by config:
if `api_key` is set, the DashScope SDK (`dashscope.audio.asr.Recognition`) is
used; otherwise the engine connects to a self-hosted FunASR WebSocket server.
Implements `ASREngine` / `ASRStream` from `tank_contracts.asr`.

Note: both backends hold a single shared connection, so recognition is
serialized — `create_stream()` returns a thin stream that routes to it.

## Features

- **Streaming partials** — online/2pass modes return partial text per chunk
- **Dual backend** — self-hosted (free, your server) or DashScope cloud (managed)
- **DashScope resilience** — watchdog detects the SDK's silent self-kill after its 23s silence timeout, `stop()` is protected by a 5s timeout, audio is sent in ~100ms strides
- **Hotwords + ITN** — self-hosted hotword weighting and inverse text normalization
- **Auto-reconnect** — the self-hosted WebSocket reconnects in a background thread

## Language support

- **DashScope mode**: recognition is started with `language_hints=["zh", "en"]` (hardcoded) — bilingual zh/en.
- **Self-hosted mode**: no language parameter is sent; capability follows the model deployed on your FunASR server.
- `detected_language` is not overridden — the pipeline falls back to text-based detection.

## Installation

Installed automatically as part of the Tank backend uv workspace (`plugins/*`):

```bash
cd backend
uv sync
```

DashScope mode in `backend/core/config.yaml` (API key from `.env`):

```yaml
asr:
  enabled: true
  extension: asr-funasr:asr
  config:
    api_key: ${DASHSCOPE_API_KEY}
    model: fun-asr-realtime-2026-02-28
    sample_rate: 16000
```

Self-hosted mode:

```yaml
asr:
  enabled: true
  extension: asr-funasr:asr
  config:
    host: localhost
    port: 10095
    mode: 2pass          # "online", "offline", or "2pass"
    sample_rate: 16000
    chunk_size: "5,10,5"
    hotwords: ""
    itn: true
```

## Configuration

**Common:** `sample_rate` (16000), `itn` (True)

**Self-hosted (no `api_key`):**

| Key | Default | Description |
|-----|---------|-------------|
| `host` | `127.0.0.1` | FunASR server host |
| `port` | `"10095"` | FunASR server port |
| `mode` | `"2pass"` | `online`, `offline`, or `2pass` |
| `is_ssl` | `False` | Use `wss://` |
| `chunk_size` | `[5, 10, 5]` | `[look-back, chunk, look-ahead]` stride |
| `hotwords` | `{}` | Dict of hotword → weight |

**DashScope (`api_key` set):**

| Key | Default | Description |
|-----|---------|-------------|
| `api_key` | `""` | DashScope API key (required for cloud mode) |
| `model` | `paraformer-realtime-v2` | Recognition model |
| `dashscope_url` | `""` | Endpoint override (empty = default China endpoint) |

## Dependencies

- **websockets>=13.0** — self-hosted WebSocket client
- **dashscope>=1.25.15** — DashScope SDK (cloud mode)
- **numpy>=1.24.0**, **tank-contracts** (workspace)

## Testing

```bash
cd backend/plugins/asr-funasr
uv run pytest
```

Tests cover the factory for both modes, session lifecycle, FunASR message
handling (`2pass`/`online`/`offline` partial vs final), DashScope result
handling, URL construction (ws/wss), and the send-stride calculation.
