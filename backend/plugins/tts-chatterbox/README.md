# Chatterbox TTS Plugin

Local offline Chatterbox (Resemble AI, MIT) in-process TTS plugin for Tank.

## Overview

This plugin runs the Chatterbox TTS model in-process (CPU or CUDA) and
implements the `TTSEngine` interface from `tank_contracts.tts`. Chatterbox is
an expressive local model with an `exaggeration` emotion control; all generated
audio carries Chatterbox's Perth neural watermark.

**Synthesis is whole-segment (batch)**: each call synthesizes the full waveform
first (blocking work is pushed off the event loop with `asyncio.to_thread`),
then the s16le PCM is yielded in fixed 4096-byte chunks. First-audio latency is
therefore the full synthesis time.

The heavy `chatterbox-tts` / `torch` dependencies are imported lazily, so a
default Tank install stays light.

## Features

- **Fully local/offline** — no cloud API, no network calls
- **Emotion control** — `exaggeration` intensity + `cfg_weight` pacing
- **Voice cloning** — optional reference WAV via `voice_prompt_path`
- **Interruptible** — checked before synthesis output is yielded and between chunks
- **Lazy model load** — model instantiated on first synthesis, then reused

## Language support

None in code: the `language` and `voice` arguments are accepted but ignored —
there is no per-language voice selection. Chatterbox is a single model.

## Installation

```bash
cd backend
uv sync

# The model deps are NOT installed by uv sync. To use this engine:
uv pip install chatterbox-tts
```

First run downloads the model from HuggingFace to the local cache.

## Configuration

Configure in `backend/core/config.yaml` (see `config.example.yaml`):

```yaml
tts:
  enabled: true
  extension: tts-chatterbox:tts
  config:
    device: cpu
    exaggeration: 0.5     # emotion intensity; raise (~0.7) for dramatic delivery
    cfg_weight: 0.5       # lower (~0.3) improves pacing for fast speech
    # voice_prompt_path: /path/to/reference_voice.wav   # optional voice cloning
    sample_rate: 24000    # emitted rate follows model.sr
```

| Key | Default | Notes |
|-----|---------|-------|
| `device` | `cpu` | `cpu` works with no GPU but is slow (several seconds per utterance); use `cuda` with an NVIDIA GPU |
| `exaggeration` | `0.5` | Emotion intensity |
| `cfg_weight` | `0.5` | Pacing/guidance weight |
| `voice_prompt_path` | unset | Reference WAV for voice cloning |
| `sample_rate` | `24000` | The model's native `sr` is used once loaded |

## Dependencies

- **numpy>=1.24.0**, **tank-contracts** (workspace) — declared
- **chatterbox-tts** (pulls in torch/torchaudio) — optional, lazy import;
  a missing install raises a clear `RuntimeError` with install instructions

## Testing

```bash
cd backend/plugins/tts-chatterbox
uv run pytest
```

Tests never import the real package — the model is mocked (`tests/test_engine.py`):
factory creation, emotion config defaults, int16 PCM conversion (numpy and
tensor-like waveforms), interruption, and the missing-dependency error path.
