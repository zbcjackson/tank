# ElevenLabs TTS Plugin

ElevenLabs realtime streaming TTS plugin for Tank Voice Assistant.

## Overview

This plugin implements the `TTSEngine` interface from `tank_contracts.tts`
using the ElevenLabs WebSocket `stream-input` API
(`wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input`). A new
WebSocket is opened per `generate_stream` call: an init message carries the API
key and voice settings, the full text is sent with `flush` to trigger
generation, and an empty text message closes the input.

**Streaming**: audio is streamed — base64 PCM chunks are decoded and yielded as
they arrive, ending on the `isFinal` marker.

## Features

- **Realtime streaming** — lowest-latency ElevenLabs endpoint
- **Model choice** — `eleven_flash_v2_5` (fastest, default), `eleven_turbo_v2_5`,
  or `eleven_v3` (most expressive)
- **Per-language voices** — `voices` map + legacy `voice_id`/`voice_id_zh`
- **Expressive controls** — optional `style`, `use_speaker_boost`, `speed`
- **Interruptible** — `is_interrupted()` stops the stream mid-flight

## Language support

Bilingual (zh/en) via per-language voice selection. The `language` argument is
used only to pick a voice (prefix matching, e.g. `zh-CN` → `zh`, falling back to
`default_voice`); it is not sent to the API — ElevenLabs infers language from
the text.

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
  extension: tts-elevenlabs:tts
  config:
    api_key: ${ELEVENLABS_API_KEY}
    voice_id: "ulmOxiH84jmsJurmeFBi"   # default voice (used for English)
    model_id: eleven_flash_v2_5        # eleven_flash_v2_5 | eleven_turbo_v2_5 | eleven_v3
    sample_rate: 24000
    stability: 0.5
    similarity_boost: 0.75
    # style: 0.5                       # 0-1, higher = more stylistic/emotional
    # use_speaker_boost: true
    # speed: 1.0
    voices:
      en: "ulmOxiH84jmsJurmeFBi"
      zh: "ulmOxiH84jmsJurmeFBi"       # replace with a Chinese voice ID
    default_voice: "ulmOxiH84jmsJurmeFBi"
```

| Key | Default | Notes |
|-----|---------|-------|
| `api_key` | — (required) | Set `ELEVENLABS_API_KEY` in `backend/.env` |
| `voice_id` | — (required) | Default voice; also the `en` entry of the legacy map |
| `voice_id_zh` | falls back to `voice_id` | Legacy Chinese voice key |
| `voices` / `default_voice` | `{}` / `voice_id` | Preferred per-language map |
| `model_id` | `eleven_flash_v2_5` | Sent as a URL query parameter |
| `sample_rate` | `24000` | Sent as `output_format=pcm_<rate>` |
| `stability` / `similarity_boost` | `0.5` / `0.75` | Core voice settings |
| `style` / `use_speaker_boost` / `speed` | unset | Omitted from the payload when unset |

For `eleven_v3`, emotion audio tags go inline in the text the LLM produces
(e.g. `[whispers] hello [laughs]`) — no API parameter needed.

## Dependencies

- **websockets>=13.0** — WebSocket client
- **tank-contracts** — `TTSEngine` / `AudioChunk` / `select_voice` (workspace)

## Usage

Loaded automatically via the `tts-elevenlabs:tts` extension factory:

```python
from tts_elevenlabs import create_engine

engine = create_engine({"api_key": "...", "voice_id": "<voice-id>"})
async for chunk in engine.generate_stream("Hello", language="en"):
    print(f"{len(chunk.data)} bytes at {chunk.sample_rate} Hz")
```

## Testing

```bash
cd backend/plugins/tts-elevenlabs
uv run pytest
```

Tests mock the WebSocket (`tests/test_engine.py`): factory creation, the
three-message send sequence, v3 voice-settings passthrough, mid-stream
interruption, and language→voice selection. No network access is needed.
