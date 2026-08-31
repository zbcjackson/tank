# Deepgram ASR Plugin

Realtime cloud streaming ASR plugin for Tank Voice Assistant.

## Overview

Uses the Deepgram WebSocket STT API (`wss://api.deepgram.com/v1/listen`) with
interim results and smart formatting. A background asyncio loop maintains the
WebSocket; the synchronous `process_pcm` interface bridges into it. Implements
`ASREngine` / `ASRStream` from `tank_contracts.asr`.

Note: the engine holds a single shared WebSocket — concurrent utterances race
on the same connection.

## Features

- **Streaming partials** — interim results update the partial text; `is_final` segments accumulate into the committed text across the utterance
- **Lazy connect + warm socket** — no socket until the first session `start()`; kept warm across turns; closed after `idle_close_secs` of inactivity (avoids reconnect churn and idle billing)
- **Finalize on stop** — sends `{"type": "Finalize"}` to flush buffered audio, then briefly waits (0.2s) for pending transcripts
- **Raw linear16 audio** — float32 PCM → int16 binary frames
- **Graceful close** — sends `CloseStream` on engine shutdown

## Language support

- Default `language: en`
- Set `language: multi` for Deepgram's multilingual mode (zh and other languages)
- `detected_language` is not overridden (always `None`) — the pipeline falls
  back to text-based language detection

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
  extension: asr-deepgram:asr
  config:
    api_key: ${DEEPGRAM_API_KEY}
    model: nova-3
    language: en        # ISO code like "en", or "multi" for multilingual
    sample_rate: 16000
```

## Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `api_key` | *(required)* | Deepgram API key (`config["api_key"]`, missing key raises `KeyError`) |
| `model` | `nova-3` | Deepgram model |
| `language` | `en` | ISO code, or `multi` for multilingual |
| `sample_rate` | `16000` | Audio sample rate (Hz) |
| `idle_close_secs` | `30.0` | Idle seconds before the warm socket is closed |

The connection is opened with `encoding=linear16`, `channels=1`,
`interim_results=true`, `smart_format=true`, and the configured model,
language, and sample rate.

## Dependencies

- **websockets>=13.0** — realtime WebSocket client
- **numpy>=1.24.0**, **tank-contracts** (workspace dependency)

## Testing

```bash
cd backend/plugins/asr-deepgram
uv run pytest
```

Tests cover the factory defaults, interim/final result handling and committed
accumulation, empty-session guards, `detected_language` being None, and
connect-on-start vs already-warm session start.
