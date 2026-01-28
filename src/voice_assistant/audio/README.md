# Audio Subsystem Architecture

## Overview

Audio subsystem handles microphone capture and utterance segmentation. It does NOT handle ASR or voiceprint recognition (those are handled by `core/Perception`).

## Module Structure

```
audio/
├── __init__.py          # Public exports
├── audio.py             # Audio facade (main entry point)
├── mic.py               # Mic thread: sounddevice capture -> frames_queue
├── segmenter.py         # UtteranceSegmenter thread: frames_queue -> utterance_queue
└── types.py             # Data types and configuration
```

## Data Flow

```
Mic (thread)
  ↓ AudioFrame
frames_queue
  ↓
UtteranceSegmenter (thread)
  ↓ Utterance
utterance_queue
  ↓
Perception (thread) [in core/]
  ↓ BrainInputEvent
brain_input_queue
```

## Key Classes

- **`Audio`**: Facade for audio subsystem. Exposes `utterance_queue` for Perception consumption.
- **`Mic`**: Captures audio frames from microphone using sounddevice.
- **`UtteranceSegmenter`**: Uses VAD (silero-vad) to segment audio frames into complete utterances.
- **`AudioFrame`**: Single frame of audio (20ms typically).
- **`Utterance`**: Complete utterance segment (from speech start to silence timeout).

## Thread Responsibilities

### Mic Thread
- Continuously capture audio from sounddevice
- Push `AudioFrame` to `frames_queue`
- **MUST be lightweight** (no VAD/ASR here)

### UtteranceSegmenter Thread
- Consume `AudioFrame` from `frames_queue`
- Run VAD (silero-vad torch/ONNX) to detect speech
- Implement endpointing logic (min_silence, pre_roll, max_utterance)
- Push complete `Utterance` to `utterance_queue`

### Perception Thread (in core/)
- Consume `Utterance` from `utterance_queue`
- **Parallel execution**: Run ASR (Whisper) and voiceprint recognition concurrently
  - ASR is required and must complete
  - Voiceprint recognition has timeout protection (falls back to default user if slow/fails)
- Emit `BrainInputEvent` to `brain_input_queue` with text, language, user, confidence

## Configuration

All configuration is in `types.py`:
- `AudioFormat`: sample_rate, channels, dtype
- `FrameConfig`: frame_ms, max_frames_queue
- `SegmenterConfig`: VAD thresholds, silence timeout, etc.

## Usage in core/Assistant

```python
from voice_assistant.audio import Audio, AudioConfig

audio = Audio(shutdown_signal, AudioConfig())
perception = Perception(shutdown_signal, utterance_queue=audio.utterance_queue)

audio.start()
perception.start()
```
