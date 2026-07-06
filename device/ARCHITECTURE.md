# Device Client Architecture

## Overview

The device firmware is a C++ application built on ESP-IDF v5.3+ that turns M5Stack hardware into a Tank voice assistant client. It streams bidirectional audio over WebSocket and displays conversation state on the LCD.

## Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Assistant                             │
│  (orchestrator: owns queues, creates tasks, routes messages) │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────┐    mic_queue    ┌───────────┐                 │
│  │AudioCapture├──────────────►│ ws_send   │                 │
│  │(I2S RX)   │               │ task      │                 │
│  └──────────┘               └─────┬─────┘                 │
│                                    │ WebSocket binary       │
│                                    ▼                        │
│                            ┌──────────────┐                 │
│                            │   WsClient    │◄── WiFiManager │
│                            └──────┬───────┘                 │
│                                    │                        │
│                    ┌───────────────┼───────────────┐        │
│                    │ binary        │ JSON           │        │
│                    ▼               ▼                │        │
│  ┌──────────┐  spk_queue   ┌───────────┐         │        │
│  │AudioPlay- │◄─────────────┤ ws_recv   │         │        │
│  │back (I2S) │              │ task      │         │        │
│  └──────────┘              └─────┬─────┘         │        │
│                                   │ event_queue   │        │
│                                   ▼               │        │
│                            ┌──────────────┐       │        │
│                            │   UI task     │       │        │
│                            │  (Display)    │       │        │
│                            └──────────────┘       │        │
└─────────────────────────────────────────────────────────────┘
```

## FreeRTOS Task Layout

| Task | Core | Priority | Purpose |
|------|------|----------|---------|
| `audio_capture` | 0 | 22 | I2S DMA read → mic_queue |
| `audio_playback` | 0 | 22 | spk_queue → I2S DMA write |
| `ws_send` | 1 | 18 | mic_queue → WebSocket binary; in wake-word mode also runs WakeNet detection + silence-based turn end |
| `ws_recv` | 1 | 18 | WebSocket → spk_queue / event_queue |
| `ui` | 1 | 5 | event_queue → display updates |

Core 0 handles all audio I/O (close to hardware, latency-critical).
Core 1 handles networking and UI (can tolerate jitter).

## Hardware Abstraction

`BoardHAL` is an abstract C++ class with per-target implementations:

```
hal/
├── BoardHAL.h              ← interface
├── cores3/
│   ├── Cores3HAL.h/.cpp    ← ES7210 + AW88298 + ILI9342C
│   └── Cores3Pins.h        ← GPIO definitions
└── pyramid/
    ├── PyramidHAL.h/.cpp   ← ES7210 + ES8311 + AW87559 + Si5351
    └── PyramidPins.h       ← GPIO definitions
```

Target selection is compile-time via `-DTARGET_CORES3` or `-DTARGET_PYRAMID`.

## WebSocket Protocol

Follows the same protocol as web/CLI clients:

**Client → Server:**
- Binary frames: raw Int16 PCM, 16kHz, mono (mic audio)
- JSON: `{"type":"signal","content":"interrupt"}`
- JSON: `{"type":"signal","content":"end_of_utterance"}` (PTT release / wake-word turn end)
- JSON: `{"type":"signal","content":"wake"}` (wake-word mode, on local detection)
- JSON: `{"type":"input","content":"text message"}`

**Server → Client:**
- Binary: 8-byte header (magic 0x544B + sample_rate + channels) + Int16 PCM
- JSON: signal, transcript, text, update, error messages

## State Machine

```
IDLE → CONNECTING → READY → LISTENING → PROCESSING → SPEAKING
  ↑                   ↑                                  │
  └───── ERROR ◄──────┴─────────────────────────────────┘
```

Transitions driven by WiFi events, WebSocket connection, and server signals.
