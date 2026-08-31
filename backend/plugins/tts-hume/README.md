# Hume TTS Plugin

Hume Octave emotionally-expressive streaming TTS plugin for Tank Voice
Assistant.

## Overview

This plugin implements the `TTSEngine` interface from `tank_contracts.tts`
using the Hume Octave streaming-input WebSocket API
(`wss://api.hume.ai/v0/tts/stream/input`). Octave adapts pitch, tempo, and
emphasis to the emotional intent of the text automatically; an optional
`description` prompt shapes the persona and emotional baseline (voice design by
prompt). A new WebSocket is opened per `generate_stream` call and one utterance
is sent.

**Streaming**: audio is streamed — base64 PCM snippets are decoded and yielded
as they arrive, ending on a terminal snippet marker (`is_last` / `isLast` /
`done`, parsed tolerantly because Hume's frame schema is validated empirically).

## Features

- **Emotionally adaptive** — Octave infers emotion from the text itself
- **Voice by description** — no voice ID required; a persona prompt shapes delivery
- **Predefined voices** — by `voice_id` (UUID) or `voice_name`, plus a
  `voices` language map
- **Instant mode** — enabled automatically when a voice reference is present
- **Interruptible** — `is_interrupted()` stops the stream and closes the socket
- **Error handling** — error envelopes are logged and stop the stream

## Language support

Language is used only to pick a voice from the `voices` map (prefix matching,
falling back to `default_voice`); no language code is sent to the API. With no
voice configured, Octave synthesizes purely from the `description` prompt.

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
  extension: tts-hume:tts
  config:
    api_key: ${HUME_API_KEY}
    description: "A warm, calm assistant with natural, empathetic delivery."
    # voice_name: "Ito"                       # optional predefined voice
    # voices: { en: "Ito", zh: "Ito" }
    # default_voice: "Ito"
    sample_rate: 24000
```

| Key | Default | Notes |
|-----|---------|-------|
| `api_key` | — (required) | Set `HUME_API_KEY` in `backend/.env` |
| `description` | unset | Persona/emotion prompt; becomes part of the utterance |
| `voice_id` | unset | Predefined voice by ID (sent as `{"id": ...}`) |
| `voice_name` | unset | Predefined voice by name (sent as `{"name": ...}`) |
| `voices` / `default_voice` | `{}` / `voice_name` | Per-language voice-name map + fallback |
| `sample_rate` | `24000` | Output PCM sample rate |

Voice resolution order: explicit `voice` argument → `voice_id` → per-language
name. When any voice reference exists, the request sets `instant_mode: true`.

## Dependencies

- **websockets>=13.0** — WebSocket client
- **tank-contracts** — `TTSEngine` / `AudioChunk` / `select_voice` (workspace)

## Usage

Loaded automatically via the `tts-hume:tts` extension factory:

```python
from tts_hume import create_engine

engine = create_engine({"api_key": "...", "description": "warm and calm"})
async for chunk in engine.generate_stream("Hello", language="en"):
    print(f"{len(chunk.data)} bytes at {chunk.sample_rate} Hz")
```

An odd trailing byte is trimmed to keep int16 alignment.

## Testing

```bash
cd backend/plugins/tts-hume
uv run pytest
```

Tests mock the WebSocket (`tests/test_engine.py`): factory creation, streaming
with `description` in the payload, mid-stream interruption, voice reference
enabling `instant_mode`, and error-envelope handling. No network access is
needed.
