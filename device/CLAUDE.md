# CLAUDE.md - Device

This file provides guidance to Claude Code when working with the Tank Device Client (ESP32-S3 firmware).

**Required Reading**: At the start of each session working on device code, you MUST read:
- @ARCHITECTURE.md [ARCHITECTURE.md](ARCHITECTURE.md) - Component architecture, tasks, protocol
- @FEATURES.md [FEATURES.md](FEATURES.md) - What the firmware does and how features are implemented
- @DEVELOPMENT.md [DEVELOPMENT.md](DEVELOPMENT.md) - Build, flash, monitor, debug commands
- @TESTING.md [TESTING.md](TESTING.md) - Native + on-device test suites

## Project Overview

Tank Device Client is C++ firmware built on ESP-IDF (v5.3+, via PlatformIO) that
turns M5Stack hardware into a Tank voice assistant client. It:

- Captures microphone audio (I2S) and streams it to the backend over WebSocket
- Plays back TTS audio (I2S) received from the backend
- Displays conversation state on the LCD
- Supports push-to-talk and continuous listening modes
- Persists volume and network config in NVS, configurable at runtime over serial

## Hardware Targets

| Target | Board | Display | Audio |
|--------|-------|---------|-------|
| `cores3` | M5Stack CoreS3 | 2.0" 320×240 IPS + touch | ES7210 mic + AW88298 amp |
| `pyramid` | Voice Pyramid + AtomS3R | 0.85" 128×128 + 28 LEDs | ES7210 + ES8311 + AW87559 |

Target selection is compile-time via `-DTARGET_CORES3` or `-DTARGET_PYRAMID`.

## Technology Stack

- **Language**: C++17
- **Framework**: ESP-IDF v5.3+
- **Build system**: PlatformIO (managed by uv, same as backend/cli)
- **RTOS**: FreeRTOS (dual-core ESP32-S3)
- **Transport**: `esp_websocket_client` (binary audio + JSON control)
- **Persistence**: NVS flash
- **Tests**: GoogleTest/GMock (native host), Unity (on-device)

## Build Commands

```bash
cd device

# Build / flash / monitor (CoreS3)
uv run pio run -e cores3
uv run pio run -e cores3 -t upload
uv run pio device monitor

# Build for Pyramid
uv run pio run -e pyramid

# Tests
uv run pio test -e native        # host-side, no hardware
uv run pio test -e cores3_test   # on-device (needs CoreS3 over USB)
```

## Verification Checklist

Run these before considering device work complete:

1. `cd device && uv run pio run -e cores3` — CoreS3 builds clean
2. `cd device && uv run pio run -e pyramid` — Pyramid builds clean
3. `cd device && uv run pio test -e native` — native suites pass (fast, no hardware)
4. `cd device && uv run pio test -e cores3_test` — on-device suites pass (only when
   a CoreS3 is connected and the change touches hardware/boot behavior)

Native tests are the day-to-day safety net. On-device tests verify things only
real hardware can prove (I2C peripherals, I2S audio, PSRAM, WiFi radio, boot).

## Development Notes

- **Config defaults** live in `main/config.h` (audio rates, queue lengths, task
  priorities/cores, reconnection timings). Network/volume defaults there are
  overridden by NVS values once saved.
- **Runtime config** is done over the USB serial monitor with AT commands
  (`AT+SSID`, `AT+PASS`, `AT+HOST`, `AT+PORT`, `AT+SAVE`, `AT+INFO`, `AT+RESET`).
- **Pure logic goes in testable units.** Protocol parsing lives in
  `main/net/WsProtocol.cpp` (no ESP-IDF deps) specifically so it can be covered
  by native tests without the WebSocket stack.
- **Adding a hardware target**: implement `BoardHAL` under `main/hal/<target>/`,
  add an `#ifdef TARGET_<NAME>` factory block, an `[env:<name>]` section in
  `platformio.ini`, and the source files to `main/CMakeLists.txt`.
- **Serial reads can be flaky in a VM** with USB passthrough — see the on-device
  notes in [TESTING.md](TESTING.md) §3 before debugging a "hang".

## Memory & Codec Traps (CoreS3, learned 2026-09)

- **Internal DRAM is fully budgeted** (~325 KB usable: 114 KB static + ~246 KB
  heap pool; steady-state free ~50 KB, largest block only 19-32 KB). Any new
  feature needing big contiguous runtime blocks must go to PSRAM — and there
  is no spare internal RAM to "make room" with.
- **LVGL's builtin allocator pool lives in PSRAM** (64 KB — formerly the
  largest internal consumer). Implemented via the `LV_MEM_POOL_ALLOC` hook:
  `main/lv_mem_psram_pool.h` force-included for all C/C++ TUs from
  `CMakeLists.txt`. Don't move it back; don't add a second static pool.
- **FreeRTOS kernel objects must live in internal RAM**:
  - A task whose **stack** is in PSRAM wild-PCs on first schedule (cache-off
    windows like NVS writes are fatal to external-stack tasks).
  - Queue/stream-buffer **control structs** in PSRAM crash the kernel
    (LoadProhibited inside xQueueReceive).
  - The reliable pattern for oversized stacks: static BSS member arrays +
    `xTaskCreateStatic` with an **internal** TCB (see `ws_send` in Assistant,
    32 KB for libopus).
- **libopus VAR_ARRAYS**: `opus_encode` allocates scratch on the caller's
  stack — 24 KB overflows on real speech, 32 KB works (`ws_send`). The
  opus_bench suite's 64 KB stack masks exact high-water marks; size stacks
  well above any guess and let the canary verify.
- **Codec states** (`components/opus`, vendored fixed-point libopus 1.4) are
  placement-inited from PSRAM (`opus_encoder_init` +
  `heap_caps_malloc(MALLOC_CAP_SPIRAM)`) — free with `heap_caps_free`, never
  the `opus_*_destroy` wrappers (they route through the internal heap).
  GCC 13's `stringop-overread` warnings on silk/NSQ are false positives
  (suppressed in the component's CMakeLists).
- **Heap integrity checks**: `heap_caps_check_integrity_all` walks the 8 MB
  PSRAM pool for seconds and starves the interrupt watchdog — scope checks
  with `heap_caps_check_integrity(MALLOC_CAP_INTERNAL, true)`.
