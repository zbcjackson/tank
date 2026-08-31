# Cartesia TTS Plugin

Cartesia Sonic realtime streaming TTS plugin for Tank Voice Assistant.

## Overview

This plugin implements the `TTSEngine` interface from `tank_contracts.tts`
using the Cartesia Sonic WebSocket API (`wss://api.cartesia.ai/tts/websocket`).
A new WebSocket is opened per `generate_stream` call; the full transcript is
sent in one message and audio comes back as base64-encoded raw PCM (s16le)
chunks.

**Streaming**: audio is streamed — PCM chunks are yielded as they arrive over
the WebSocket, so playback can start before the whole utterance is synthesized.

## Features

- **Realtime streaming** — low-latency PCM chunks over WebSocket
- **Per-language voice UUIDs** — `voices` map + `default_voice` fallback
- **Emotion controls** — optional `emotion` list via `generation_config`
- **Interruptible** — `is_interrupted()` stops the stream and closes the socket
- **Raw PCM output** — no decode step (s16le, mono, default 24 kHz)

## Language support

Bilingual (zh/en). Voice is chosen via the `voices` map with prefix matching
(`zh-CN` → `zh`), falling back to `default_voice`. When the language is known
(not `auto`), its ISO prefix is also sent to Cartesia in the request.

## Installation

Installed automatically as part of the Tank backend uv workspace:

```bash
cd backend
uv sync
```

## Configuration

Configure in `backend/core/config.yaml` (see `config.example.yaml`):

```yaml
tts:
  enabled: true
  extension: tts-cartesia:tts
  config:
    api_key: ${CARTESIA_API_KEY}
    model_id: sonic-3
    voices:
      en: "a0e99841-438c-4a64-b679-ae501e7d6091"
      zh: "a0e99841-438c-4a64-b679-ae501e7d6091"
    default_voice: "a0e99841-438c-4a64-b679-ae501e7d6091"
    sample_rate: 24000
    # emotion: []                # optional Cartesia emotion controls
    # cartesia_version: "2026-03-01"
```

| Key | Default | Notes |
|-----|---------|-------|
| `api_key` | — (required) | Cartesia API key; set `CARTESIA_API_KEY` in `backend/.env` |
| `model_id` | `sonic-3` | Sonic model |
| `voices` | `{}` | language → voice UUID map |
| `default_voice` | `""` | Fallback; if empty, the first entry of `voices` is used |
| `sample_rate` | `24000` | Output PCM sample rate |
| `emotion` | unset | Optional emotion controls passed as `generation_config` |
| `cartesia_version` | `2026-03-01` | `cartesia_version` query parameter |

## Dependencies

- **websockets>=13.0** — WebSocket client
- **tank-contracts** — `TTSEngine` / `AudioChunk` / `select_voice` (workspace)

## Usage

The plugin is loaded automatically by the backend via the
`tts-cartesia:tts` extension factory. Programmatic use:

```python
from tts_cartesia import create_engine

engine = create_engine({"api_key": "...", "default_voice": "<uuid>"})
async for chunk in engine.generate_stream("Hello", language="en"):
    print(f"{len(chunk.data)} bytes at {chunk.sample_rate} Hz")
```

Server messages handled: `chunk` (audio data), `done` (end), `error`
(logged as a warning and stops the stream). An odd trailing byte is trimmed to
keep int16 alignment.

## Testing

```bash
cd backend/plugins/tts-cartesia
uv run pytest
```

Tests mock the WebSocket connection (`tests/test_engine.py`): factory creation,
language→voice selection, basic streaming, mid-stream interruption, and
error-message handling. No network access is needed.
