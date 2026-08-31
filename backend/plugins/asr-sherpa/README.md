# Sherpa-ONNX ASR Plugin

Local streaming ASR plugin for Tank Voice Assistant.

## Overview

This plugin provides speech recognition using sherpa-onnx's `OnlineRecognizer`
(streaming zipformer transducer). It implements the `ASREngine` /
`ASRStream` interfaces from `tank_contracts.asr`.

Two layers:

- `SherpaASREngine` — process-global, loads the ONNX models once, creates cheap streams.
- `SherpaASRStream` — per-utterance decoding session (start → process_pcm → stop).

## Features

- **True streaming** — partial transcripts after every PCM chunk (`supports_streaming` defaults to True)
- **Local and offline** — no network calls, no API key
- **Fresh-stream sessions** — `start()` creates a new sherpa stream instead of resetting, so tokens from a previous utterance never bleed into the next one
- **Decoder flush on stop** — pads 0.3s of silence, marks input finished, and drains the decoder so trailing tokens are emitted before the final transcript is returned
- **VAD-owned turn endings** — sherpa's built-in endpoint detector is disabled; the Silero VAD segmenter upstream owns turn boundaries
- **macOS compatibility** — pre-loads the onnxruntime dylib on darwin before loading sherpa-onnx

## Language support

Bilingual zh/en by default: the model directory shipped in the default config
is the sherpa-onnx **bilingual zh-en streaming zipformer** (downloaded via
`backend/scripts/download_models.py`). The engine has no language parameter —
language capability is determined entirely by the model in `model_dir`.
`detected_language` is not overridden, so the pipeline falls back to
text-based language detection on the transcript.

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
  extension: asr-sherpa:asr
  config:
    model_dir: ../models/sherpa-onnx-zipformer-en-zh
    num_threads: 4
    sample_rate: 16000
```

Download the models (manual, one-time):

```bash
cd backend
uv run python scripts/download_models.py
```

## Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `model_dir` | `../models/sherpa-onnx-zipformer-en-zh` | Model directory (must contain `encoder-epoch-99-avg-1.onnx`, `decoder-epoch-99-avg-1.onnx`, `joiner-epoch-99-avg-1.onnx`, `tokens.txt`) |
| `num_threads` | `4` | Decoder threads |
| `sample_rate` | `16000` | Model sample rate (Hz) |

Raises `FileNotFoundError` at construction if `model_dir` does not exist.

## Dependencies

- **sherpa-onnx>=1.10.0** — ONNX speech runtime
- **numpy>=1.24.0** — audio buffers
- **tank-contracts** — `ASREngine` / `ASRStream` ABCs (workspace dependency)

## Usage

Loaded automatically by the backend. Programmatic use:

```python
from asr_sherpa import create_engine

engine = create_engine({"model_dir": "../models/sherpa-onnx-zipformer-en-zh"})
stream = engine.create_stream()
stream.start()
partial = stream.process_pcm(pcm_float32)   # current partial transcript
final = stream.stop()                        # final transcript
stream.close()
```

## Testing

```bash
cd backend/plugins/asr-sherpa
uv run pytest
```

Tests cover: endpoint detection disabled in the recognizer config, missing
model dir raising, fresh-stream session start, decoder flush on stop with
last-partial fallback, and the `create_engine` factory defaults.
