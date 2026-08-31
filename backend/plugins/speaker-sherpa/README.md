# Sherpa-ONNX Speaker ID Plugin

Sherpa-ONNX speaker embedding plugin for Tank Voice Assistant.

## Overview

This plugin provides speaker identification via voiceprint embeddings. It implements the `SpeakerEmbeddingExtractor` interface from `tank_contracts` and wraps sherpa-onnx's `SpeakerEmbeddingExtractor`, so it works with ONNX speaker models such as 3D-Speaker (Alibaba) and WeSpeaker.

## Features

- **Local inference** — ONNX on CPU, no network calls
- **Language-agnostic** — embeddings are voice-based, not text-based (zh/en both work)
- **Automatic normalization** — rescales audio whose peak exceeds 1.0 before embedding
- **macOS compatibility** — pre-loads the onnxruntime dylib to avoid sherpa-onnx load failures on macOS

## Installation

This plugin is installed automatically as part of the Tank backend workspace:

```bash
cd backend
uv sync
```

## Configuration

Configure in `backend/core/config.yaml`:

```yaml
speaker:
  enabled: true
  extension: speaker-sherpa:speaker_id
  config:
    model_path: ../models/speaker/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx
    num_threads: 1
    provider: cpu
    threshold: 0.6
    default_user: Unknown
```

### Available Configuration Options

- **model_path** (required) — path to the ONNX speaker embedding model. Raises `FileNotFoundError` at instantiation when missing
- **num_threads** — ONNX threads (default: `1`)
- **provider** — execution provider (default: `cpu`)

The `threshold` and `default_user` keys are consumed by the backend's speaker-identification layer, not by this plugin — the engine itself only extracts embeddings (`embedding_dim` is read from the loaded model).

### Model Download

```bash
cd backend
uv run python scripts/download_models.py
```

## Dependencies

- **sherpa-onnx>=1.10.0** — speaker embedding runtime
- **numpy>=1.24.0** — audio arrays (float32 in/out)

## Testing

```bash
cd plugins/speaker-sherpa
uv run pytest
```

## Related

- [Speaker enrollment & REST API](../../DEVELOPMENT.md#speaker-identification)
- [tank_contracts speaker interface](../../contracts/tank_contracts/)
