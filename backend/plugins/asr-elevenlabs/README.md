# ElevenLabs ASR Plugin

Realtime cloud streaming ASR plugin for Tank Voice Assistant.

## Overview

Uses the ElevenLabs WebSocket STT API (`wss://api.elevenlabs.io/v1/speech-to-text/realtime`,
model `scribe_v2_realtime`) with the **manual** commit strategy — the
pipeline's Silero VAD owns turn boundaries, so the engine runs no competing
server-side VAD. A background asyncio loop maintains the WebSocket; the
synchronous `process_pcm` interface bridges into it. Implements
`ASREngine` / `ASRStream` from `tank_contracts.asr`.

Note: the engine holds a single shared WebSocket — concurrent utterances race
on the same connection.

## Features

- **Streaming partials** — `partial_transcript` messages update the partial text per chunk
- **Lazy connect + warm socket** — no socket until the first session `start()`; kept warm across back-to-back turns; closed after `idle_close_secs` of inactivity (avoids ElevenLabs dropping idle sessions and idle billing)
- **Forced commit on stop** — sends an empty chunk with `commit: true` and waits (bounded, 2s — under the ASRProcessor's 5s stop timeout) for the `committed_transcript` handshake rather than sleeping blindly
- **Audio as base64** — float32 PCM → int16 → base64 JSON frames

## Language support

- `language_code: ""` (default) — auto-detect, ElevenLabs identifies the language per utterance
- Set an ISO code (`en`, `zh`, …) to pin the language
- `detected_language` is not overridden — the pipeline falls back to text-based detection

## Installation

Installed automatically as part of the Tank backend uv workspace (`plugins/*`):

```bash
cd backend
uv sync
```

Assign it to the ASR slot in `backend/core/config.yaml` (API key from `.env`):

```yaml
asr:
  enabled: true
  extension: asr-elevenlabs:asr
  config:
    api_key: ${ELEVENLABS_API_KEY}
    language_code: "" # Empty for auto-detect, or ISO code like "en" or "zh"
    sample_rate: 16000
```

## Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `api_key` | *(required)* | ElevenLabs API key (`config["api_key"]`, missing key raises `KeyError`) |
| `language_code` | `""` | ISO code to pin the language; empty = auto-detect |
| `sample_rate` | `16000` | Audio sample rate (Hz) |
| `idle_close_secs` | `30.0` | Idle seconds before the warm socket is closed |

## Dependencies

- **websockets>=13.0** — realtime WebSocket client
- **numpy>=1.24.0**, **tank-contracts** (workspace dependency)

## Usage

Loaded automatically by the backend. Programmatic use:

```python
from asr_elevenlabs import create_engine

engine = create_engine({"api_key": "...", "language_code": ""})
stream = engine.create_stream()
stream.start()
partial = stream.process_pcm(pcm_float32)   # current partial transcript
final = stream.stop()                        # committed transcript
stream.close()
```

## Testing

```bash
cd backend/plugins/asr-elevenlabs
uv run pytest
```

Tests cover partial/committed message handling, commit-unblock and
input-error unblock of the stop waiter, connect-on-start vs already-warm,
forced commit on stop with partial fallback on timeout, and factory
defaults including `idle_close_secs`.
