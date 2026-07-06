# Device Client Features

This document describes what the Tank device firmware does and how each feature
is implemented. For component wiring and task layout, see
[ARCHITECTURE.md](ARCHITECTURE.md).

## Feature Summary

| Feature | Status | Where |
|---------|--------|-------|
| WiFi connect + auto-reconnect | ✅ | `net/WiFiManager` |
| WebSocket transport (binary audio + JSON) | ✅ | `net/WsClient`, `net/WsProtocol` |
| Microphone capture (I2S → PCM → WS) | ✅ | `audio/AudioCapture` |
| Speaker playback (WS → PCM → I2S) | ✅ | `audio/AudioPlayback` |
| Push-to-talk interaction | ✅ | `app/Assistant` (UI + ws_send tasks) |
| Continuous listening mode | ✅ | `app/Assistant` (compile-time toggle) |
| On-device wake word ("Hi ESP") | ✅ | `audio/WakeWordDetector` (esp-sr WakeNet9) |
| Interruption (barge-in) | ✅ | `app/Assistant`, `WsClient::sendInterrupt` |
| LCD status/transcript UI | ✅ | `ui/Display` + per-board impls |
| Volume control + persistence | ✅ | `ui/screens/SettingsScreen`, `NvsSettings` |
| Runtime network config (serial AT) | ✅ | `settings/SerialConfig`, `NvsSettings` |
| Session state machine | ✅ | `app/Session` |
| Bitmap font / rich text rendering | ⬜ planned | — |
| Pyramid LED ring animations | ⬜ planned | `hal/pyramid` |

## Voice Conversation

The core loop streams audio both directions over one WebSocket:

```
[Mic] → I2S → capture_task → mic_queue → ws_send_task → WebSocket → [Backend]
[Backend] → WebSocket → ws_recv → spk_stream → playback_task → I2S → [Speaker]
                                → event_queue → ui_task → [Display]
```

- **Capture**: `AudioCapture` reads 20 ms frames (320 samples @ 16 kHz mono
  Int16) from the I2S mic via DMA and pushes them to `mic_queue`.
- **Uplink**: `ws_send_task` pulls frames and sends them as raw Int16 PCM binary
  frames (no header) to the backend.
- **Downlink**: the backend sends TTS audio as binary frames with an 8-byte
  header (magic `0x544B` + sample_rate + channels) followed by Int16 PCM.
  `WsClient` parses the header, reassembles fragmented frames, and hands PCM to
  `AudioPlayback` via a byte stream buffer.
- **Playback backpressure**: `onWsAudio` writes to the speaker stream buffer with
  `portMAX_DELAY`, so the WebSocket callback blocks until space frees up rather
  than dropping frames. This is deliberate — dropping frames caused audible blast
  noise on long responses.

## Interaction Modes

Selected at compile time via `CONFIG_PUSH_TO_TALK` in `main/config.h`
(a runtime settings page is planned).

### Push-to-talk (default, `CONFIG_PUSH_TO_TALK=1`)

The mic streams only while the on-screen button is held:

1. **Press** → send `interrupt`, flush any pending playback, reset `mic_queue`,
   set `talking_ = true`, state → `LISTENING`, show the talk cue.
   Capture runs continuously, so the DMA already holds fresh ambient audio —
   there is no discard window that would clip the start of speech.
2. **Hold** → `ws_send_task` forwards every mic frame while `talking_` is set.
3. **Release** → set `talking_ = false`, `eou_pending_ = true`,
   `drain_frames_ = 8`, state → `PROCESSING`. The send task keeps forwarding the
   tail frames still queued in the DMA/pipeline, then sends `end_of_utterance`.
   If the queue empties before the drain counter reaches zero, EOU is sent
   immediately on the next queue timeout.
4. Frames received while neither talking nor draining are discarded (silence/echo).

**Phantom-touch guard**: the FT6336U touch controller reports spurious touches
during playback (speaker-amp coupling on the shared board). The UI task ignores
button presses while `AudioPlayback::isPlaying()` is true. In PTT mode the user
does not talk over the response, so gating on playback is safe.

### Continuous (`CONFIG_PUSH_TO_TALK=0`)

The send task forwards every captured frame whenever the WebSocket is connected.
The backend's own VAD/echo-guard handles endpointing. No on-device PTT gating.

### Wake word (`CONFIG_WAKE_WORD=1`, requires `CONFIG_PUSH_TO_TALK=0`)

An on-device wake word engine listens while idle and opens a turn hands-free.
The two flags are mutually exclusive (a `#error` guards this) — there is no
button to gate streaming.

- **Engine**: Espressif [esp-sr](https://github.com/espressif/esp-sr) WakeNet9,
  running the bundled stock word **"Hi ESP"** (`CONFIG_SR_WN_WN9_HIESP`). No
  custom-model cost. `audio/WakeWordDetector` wraps the `esp_srmodel` /
  `esp_wn_iface` C API; `audio/FrameChunker` re-buffers the 320-sample (20ms)
  capture frames into WakeNet's native chunk size (480 samples).
- **Model storage**: flashed to a dedicated `model` data partition (1MB, see
  `partitions_*.csv`) as `srmodels.bin`. `idf.py`/`pio run -t upload` flashes it
  alongside the app; only the WakeNet model is included (MultiNet stays at its
  `NONE` default), so the payload is ~0.5MB.
- **Flow** (all in `ws_send_task`):
  1. **Idle** → each mic frame is fed to `WakeWordDetector`. Detection is
     suppressed while: (a) the WebSocket isn't connected yet (frees Core 1 for
     WiFi/DHCP), (b) the speaker is playing, (c) the 700ms echo hangover after
     playback stops, or (d) the mic frame energy is still above the speech
     threshold (residual room echo).
  2. **Detected** → send `interrupt`, flush playback, send `wake` signal (the
     backend compacts the session and replies `conversation_ready`), set
     `talking_ = true`, state → `LISTENING`.
  3. **Streaming** → forward every frame while watching `audio/SilenceDetector`
     (energy-based). The turn ends on ~800ms of trailing silence after speech,
     or a 15s max-listen cap, whichever comes first.
  4. **End** → send `end_of_utterance`, state → `PROCESSING`.
  5. **Response** → backend streams audio, playback runs. Once playback finishes
     and the echo hangover + energy gate pass, state → `READY`.
- **Echo suppression** (`CONFIG_WAKE_ECHO_HANGOVER_MS`): this board has no
  hardware AEC (ES7210 + AW88298 share an I2S bus but no echo cancellation
  path). Detection is suppressed during playback plus a fixed hangover, and
  also gates on mic frame energy dropping below the speech threshold — so
  the assistant's own TTS response can't self-trigger a new turn.
- **Turn-end tuning** (`main/config.h`): `CONFIG_WAKE_SPEECH_RMS`,
  `CONFIG_WAKE_SILENCE_FRAMES`, `CONFIG_WAKE_MIN_SPEECH_FRAMES`,
  `CONFIG_WAKE_MAX_FRAMES` (all in 20ms frame units).
- **Memory**: WakeNet's runtime buffers compete with the WebSocket task for
  internal DRAM. `CONFIG_SPIRAM_TRY_ALLOCATE_WIFI_LWIP=y` moves WiFi/LWIP
  buffers to PSRAM, freeing internal RAM for task stacks.

If the model fails to load at boot, the device logs the error and continues to
connect normally — it just won't wake on speech.

## Interruption (Barge-in)

On PTT press (or any new user turn), `WsClient::sendInterrupt()` sends
`{"type":"signal","content":"interrupt"}` and `AudioPlayback::flush()` drops
buffered TTS so the response stops immediately.

## Display / UI

`Display` is an abstract interface implemented per board
(`Cores3Display`, `PyramidDisplay`) plus a serial-only stub fallback. It exposes:

- `showStatus` — connection/mode text ("Connecting…", "Listening…", …)
- `showUserText` / `showAssistantText` — transcript + streamed response
- `showThinking` — processing indicator
- `showError` — error text
- `showTalkState` — full-screen color cue for PTT (works without a font)
- `pollPressed` — polls the touch PTT button (false on non-touch displays)

Server `update`, `transcript`, and `text` messages are routed to the UI task via
`event_queue`; the task renders them and drives per-turn text clearing.

`MainScreen` and `SettingsScreen` (`ui/screens/`) provide the primary view and a
volume settings page.

## Session State Machine

`Session` tracks connection/turn state:

```
IDLE → CONNECTING → READY → LISTENING → PROCESSING → SPEAKING
  ↑                   ↑                                  │
  └───── ERROR ◄──────┴─────────────────────────────────┘
```

Transitions are driven by WiFi events, WebSocket connect/disconnect, PTT
press/release, and server `signal` messages (`ready`, `processing_started`,
`processing_ended`).

## Networking & Resilience

- **WiFi**: `WiFiManager` connects on boot and auto-reconnects on drop
  (`CONFIG_WIFI_RETRY_MAX`). On loss, state → `CONNECTING` and the UI shows
  "WiFi lost, reconnecting…".
- **WebSocket**: `esp_websocket_client` owns the reconnect loop
  (`CONFIG_WS_RECONNECT_MS`, `CONFIG_WS_NETWORK_TIMEOUT_MS`,
  `CONFIG_WS_PINGPONG_TIMEOUT_S`). `onConnected`/`onDisconnected` callbacks resync
  UI/session state. On disconnect, transient turn state (`talking_`,
  `eou_pending_`, `drain_frames_`) is reset so a stale utterance can't leak into
  the next connection.
- **Fragment reassembly**: binary payloads larger than the WS buffer arrive in
  multiple events; `WsClient` accumulates fragments until the full payload lands.

## Configuration & Persistence

Two layers, NVS overriding compile-time defaults:

- **Compile-time defaults** (`main/config.h`): WiFi SSID/password, backend
  host/port, session ID, audio rates/frame sizes, queue lengths, task
  cores/priorities/stacks, and reconnection timings. Network defaults can also be
  injected at build time via env vars (`TANK_WIFI_SSID`, etc., see
  `inject_env.py`).
- **NVS** (`NvsSettings`, namespace `tank_cfg`): volume (0–100), WiFi
  credentials, backend host/port. `hasNetworkConfig()` decides whether to use
  saved creds or the `config.h` defaults on boot.

### Runtime configuration (serial AT commands)

`SerialConfig` runs a task reading UART0 line-by-line and applies changes to NVS:

```
AT+SSID=<value>   Set WiFi SSID
AT+PASS=<value>   Set WiFi password
AT+HOST=<value>   Set backend host
AT+PORT=<value>   Set backend port
AT+INFO           Print current config (password masked)
AT+SAVE           Save and reconnect
AT+RESET          Factory reset (erase NVS, reboot)
```

### Volume

Adjusted on-device via `SettingsScreen` (gear icon → `-` / `+`). The level is
applied to the amplifier through the HAL and saved to NVS, restored on next boot.

## Hardware Abstraction

`BoardHAL` isolates board differences (codec init, I2C, volume, mic gain, pins)
behind one interface, selected at compile time (`-DTARGET_CORES3` /
`-DTARGET_PYRAMID`). See [ARCHITECTURE.md](ARCHITECTURE.md#hardware-abstraction)
for the layout and DEVELOPMENT.md for adding a new target.
