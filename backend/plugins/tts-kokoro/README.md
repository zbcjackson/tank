# Kokoro TTS Plugin

Local offline Kokoro-82M in-process TTS plugin for Tank Voice Assistant (CPU).

## Overview

This plugin runs the Kokoro-82M model in-process via `KPipeline` and implements
the `TTSEngine` interface from `tank_contracts.tts`. Kokoro is a tiny (82M)
open-weight model that runs on CPU.

**Synthesis is whole-segment (batch)**: each call synthesizes all audio
segments first (blocking work runs off the event loop with `asyncio.to_thread`),
then the float32 segments are converted to s16le PCM and yielded in fixed
4096-byte chunks. First-audio latency is therefore the full synthesis time.
One `KPipeline` is created per language code on demand and cached.

The heavy `kokoro` dependency is imported lazily, so a default Tank install
stays light.

## Features

- **Fully local/offline** — no cloud API, no network calls
- **CPU-friendly** — small 82M model
- **Voice presets** — per-language Kokoro voice names + `speed` control
- **Interruptible** — checked between segments and between chunks
- **Lazy pipeline load** — `KPipeline` instantiated on first synthesis per language

## Language support

English-focused. ISO 639-1 codes map to Kokoro `lang_code` values: `en` → `a`
(American English), `zh` → `z` (Mandarin), `es` → `e`, `fr` → `f`, `hi` → `h`,
`it` → `i`, `pt` → `p`, `ja` → `j`. Unknown languages and `auto` fall back to
`a` (English). Chinese quality is limited and requires the `misaki[zh]` extra
(`ja` needs `misaki[ja]`); CosyVoice remains the better local bilingual pick.

## Installation

```bash
cd backend
uv sync

# Model deps are NOT installed by uv sync. To use this engine:
uv pip install "kokoro>=0.9.4" soundfile
# plus the espeak-ng system package (e.g. apt-get install espeak-ng)
# Chinese: uv pip install "misaki[zh]"
```

## Configuration

Configure in `backend/core/config.yaml` (see `config.example.yaml`):

```yaml
tts:
  enabled: true
  extension: tts-kokoro:tts
  config:
    voices:
      en: af_heart
      zh: zf_xiaobei
    default_voice: af_heart
    speed: 1.0
    sample_rate: 24000
```

| Key | Default | Notes |
|-----|---------|-------|
| `voices` | `{en: af_heart}` | language → Kokoro voice preset map |
| `default_voice` | `af_heart` | Fallback voice |
| `speed` | `1.0` | Speaking rate multiplier |
| `sample_rate` | `24000` | Kokoro emits 24 kHz |

## Dependencies

- **numpy>=1.24.0**, **tank-contracts** (workspace) — declared
- **kokoro>=0.9.4**, **soundfile**, **torch** — optional, lazy import; a
  missing install raises a clear `RuntimeError` with install instructions
- **espeak-ng** — system package required by Kokoro
- **misaki[zh]** / **misaki[ja]** — optional extras for Chinese / Japanese

## Usage

Loaded automatically via the `tts-kokoro:tts` extension factory:

```python
from tts_kokoro import create_engine

engine = create_engine({"default_voice": "af_heart"})
async for chunk in engine.generate_stream("Hello", language="en"):
    print(f"{len(chunk.data)} bytes at {chunk.sample_rate} Hz")
```

An odd trailing byte is trimmed to keep int16 alignment.

## Testing

```bash
cd backend/plugins/tts-kokoro
uv run pytest
```

Tests never import the real package — the pipeline is mocked
(`tests/test_engine.py`): factory creation, language-code mapping, voice
selection, int16 PCM conversion, interruption, and the missing-dependency
error path.
