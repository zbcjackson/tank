# Faster-Whisper ASR Plugin

Local offline batch ASR plugin for Tank Voice Assistant.

## Overview

Uses Faster-Whisper, the CTranslate2 reimplementation of OpenAI Whisper, to
transcribe a complete utterance in one pass. It is **not** a streaming engine:
the stream sets `supports_streaming = False`, so the pipeline buffers the full
utterance and hands it to `process_pcm` in a single call after VAD END_SPEECH,
and `stop()` returns the transcript. Implements `ASREngine` / `ASRStream`
from `tank_contracts.asr`.

The model is loaded once at the engine level and shared across streams.

## Features

- **Local and offline** — no API key, no network after the first model download
- **Batch accuracy** — full-utterance decoding with beam search (`beam_size`)
- **Language reporting** — exposes Whisper's acoustic language ID via `detected_language` (ISO 639-1), which the pipeline uses in preference to text-based detection
- **Multi-segment join** — all segments of a transcription are concatenated into one transcript
- **Configurable runtime** — model size, device (cpu/cuda), and compute type

## Language support

Multilingual (zh/en and other Whisper languages):

- `language: ""` (default) — auto-detect per utterance; the detected ISO 639-1
  code is reported through `detected_language`
- Set an ISO code (`en`, `zh`, …) to force a language

## Installation

Installed automatically as part of the Tank backend uv workspace (`plugins/*`):

```bash
cd backend
uv sync
```

Assign it to the ASR slot in `backend/core/config.yaml`:

```yaml
asr:
  enabled: true
  extension: asr-faster-whisper:asr
  config:
    model_size: base          # tiny | base | small | medium | large-v3
    device: cpu               # cpu | cuda
    compute_type: int8        # int8 (cpu) | float16 (cuda)
    language: ""              # empty for auto-detect, or ISO code like "en"/"zh"
    beam_size: 5
    sample_rate: 16000
```

The model is downloaded from HuggingFace to the local cache on first start.

## Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `model_size` | `base` | Whisper model size (`tiny`, `base`, `small`, `medium`, `large-v3`) |
| `device` | `cpu` | `cpu` or `cuda` |
| `compute_type` | `int8` | Quantization (`int8` for cpu, `float16` for cuda) |
| `language` | `""` | ISO code, or empty for auto-detect |
| `beam_size` | `5` | Decoding beam width |
| `sample_rate` | `16000` | Audio sample rate (Hz) |

## Dependencies

- **faster-whisper>=1.0.0** — CTranslate2 Whisper runtime
- **numpy>=1.24.0**, **tank-contracts** (workspace dependency)

## Testing

```bash
cd backend/plugins/asr-faster-whisper
uv run pytest
```

Tests cover the factory defaults, `supports_streaming` being False, the
`sample_rate` property, batch transcription with detected language,
multi-segment joining, and empty-audio `stop()` returning an empty string.
