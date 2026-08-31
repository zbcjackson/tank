# AssemblyAI ASR Plugin

Realtime cloud streaming ASR plugin for Tank Voice Assistant.

## Overview

Uses the AssemblyAI Universal-Streaming v3 WebSocket API
(`wss://streaming.assemblyai.com/v3/ws`). A background asyncio loop maintains
the WebSocket; the synchronous `process_pcm` interface bridges into it.
Implements `ASREngine` / `ASRStream` from `tank_contracts.asr`.

Note: the engine holds a single shared WebSocket — concurrent utterances race
on the same connection.

## Features

- **Streaming partials** — `Turn` messages update the partial text; a turn with `end_of_turn` commits it
- **Lazy connect + warm socket** — no socket until the first session `start()`; kept warm across turns; closed after `idle_close_secs` of inactivity (avoids reconnect churn and idle billing)
- **Raw-key auth** — the API key is sent in `Authorization` with no `Token`/`Bearer` prefix, per AssemblyAI's v3 streaming API
- **Raw PCM audio** — float32 → int16 binary frames (mono 16-bit)
- **Clean billing** — sends `{"type": "Terminate"}` on engine shutdown to end the billed session

## Language support

The engine exposes **no language parameter** — the model's default language
behavior applies. `detected_language` is not overridden (always `None`), so
the pipeline falls back to text-based language detection on the transcript.

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
  extension: asr-assemblyai:asr
  config:
    api_key: ${ASSEMBLYAI_API_KEY}
    speech_model: universal-3-5-pro
    sample_rate: 16000
```

## Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `api_key` | *(required)* | AssemblyAI API key (`config["api_key"]`, missing key raises `KeyError`) |
| `speech_model` | `universal-3-5-pro` | Streaming speech model |
| `sample_rate` | `16000` | Audio sample rate (Hz) |
| `idle_close_secs` | `30.0` | Idle seconds before the warm socket is closed |

The connection URL carries `sample_rate` and `speech_model` as query parameters.

## Dependencies

- **websockets>=13.0** — realtime WebSocket client
- **numpy>=1.24.0**, **tank-contracts** (workspace dependency)

## Testing

```bash
cd backend/plugins/asr-assemblyai
uv run pytest
```

Tests cover the factory defaults, partial-turn and end-of-turn handling,
empty-session guards, `detected_language` being None, and connect-on-start
vs already-warm session start.
