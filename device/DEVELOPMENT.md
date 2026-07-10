# Device Client Development Guide

## Prerequisites

- Python 3.10+ with [uv](https://docs.astral.sh/uv/) (package manager)
- USB-C cable
- M5Stack CoreS3 (or Voice Pyramid + AtomS3R)
- Tank backend running and accessible on your network

## Setup

```bash
cd device

# Install PlatformIO (managed by uv, same as backend/cli)
uv sync

# Configure WiFi and backend address
# Edit main/config.h:
#   CONFIG_WIFI_SSID, CONFIG_WIFI_PASSWORD, CONFIG_BACKEND_HOST
```

First build downloads the ESP-IDF toolchain automatically (~2-5 minutes). Subsequent builds are incremental (~10-30 seconds).

## Development Workflow

### Build → Flash → Monitor (typical loop)

```bash
# Build
uv run pio run -e cores3

# Flash via USB
uv run pio run -e cores3 -t upload

# Serial log (Ctrl+] to exit)
uv run pio device monitor

# All-in-one
uv run pio run -e cores3 -t upload && uv run pio device monitor
```

### Build for Pyramid target

```bash
uv run pio run -e pyramid
uv run pio run -e pyramid -t upload
```

### Clean build

```bash
uv run pio run -e cores3 -t clean
uv run pio run -e cores3
```

## Debugging

### Serial Monitor

The firmware logs extensively via ESP_LOG. Key log tags:
- `Assistant` — lifecycle events, state transitions
- `WiFiManager` — connection, disconnection, retries
- `WsClient` — WebSocket events, frame counts
- `AudioCapture` — I2S read stats
- `AudioPlayback` — I2S write stats, underruns
- `Cores3HAL` / `PyramidHAL` — hardware init

### Increase log verbosity

In `platformio.ini`, change `CORE_DEBUG_LEVEL`:
- `3` = INFO (default)
- `4` = DEBUG
- `5` = VERBOSE

### JTAG debugging (advanced)

```bash
uv run pio debug -e cores3
```

Requires a JTAG adapter connected to the ESP32-S3's debug pins.

## Common Tasks

### Add a new hardware target

1. Create `main/hal/newtarget/` with `NewTargetHAL.h/.cpp` and `NewTargetPins.h`
2. Implement `BoardHAL` interface
3. Add `#ifdef TARGET_NEWTARGET` factory block in the `.cpp`
4. Add `[env:newtarget]` section to `platformio.ini` with `-DTARGET_NEWTARGET`
5. Add source files to `main/CMakeLists.txt`

### Change audio parameters

All audio constants are in `main/config.h`:
- `CONFIG_MIC_SAMPLE_RATE` — mic capture rate (must be 16000 for Tank backend)
- `CONFIG_SPK_SAMPLE_RATE` — speaker playback rate (24000 to match server TTS)
- `CONFIG_MIC_FRAME_MS` — capture frame duration (20ms default)

### On-device wake word

The device always supports both the on-screen push-to-talk button and the
hands-free "Hi ESP" wake word (esp-sr WakeNet9) — there is no build-time mode
selection to configure.

The WakeNet model is flashed to the `model` partition automatically on
`pio run -t upload` (generated as `srmodels.bin`). Turn-end sensitivity is tuned
via the `CONFIG_WAKE_*` constants (frame counts / RMS threshold) in `config.h`.
To change the wake word itself, adjust the `CONFIG_SR_WN_*` option in
`sdkconfig.defaults` (a custom word requires Espressif's paid customization
service).

### Store WiFi credentials in NVS

For production, store credentials in non-volatile storage instead of hardcoding:

```cpp
#include "nvs_flash.h"
// Write once:
nvs_set_str(handle, "wifi_ssid", ssid);
// Read on boot:
nvs_get_str(handle, "wifi_ssid", buf, &len);
```

## Troubleshooting

### "No such file or directory" for ESP-IDF headers

PlatformIO downloads ESP-IDF on first build. If it fails:
```bash
uv run pio pkg update -e cores3
```

### Upload fails with "Permission denied"

```bash
# Linux: add user to dialout group
sudo usermod -aG dialout $USER
# Then logout/login

# macOS: usually works out of the box via /dev/cu.usbmodem*
```

### No serial output

- Check USB cable supports data (not charge-only)
- Verify monitor speed matches: `monitor_speed = 115200`
- Try pressing the reset button on the device

### WiFi won't connect

- Verify SSID/password in `config.h` (case-sensitive)
- Ensure 2.4 GHz network (ESP32 doesn't support 5 GHz)
- Check serial log for WiFi event details

### WebSocket won't connect

- Verify backend is running: `curl http://<host>:8000/health`
- Check `CONFIG_BACKEND_HOST` is the correct LAN IP (not localhost)
- Firewall: ensure port 8000 is accessible from the device's network

## CoreS3 UI / LVGL gotchas

The CoreS3 touch UI (`main/ui/Cores3Display.cpp`, `main/ui/screens/`) has three
hard-won constraints. Violating any of them presents as a "frozen UI" or "dead
button" that is hard to diagnose because unrelated tasks (audio streaming) keep
running. Read these before touching the display code.

### UI freezes on screen switch — SPI DMA can't reach PSRAM

**Symptom:** The UI freezes the first time a full-screen redraw happens (e.g.
switching to the settings screen). Serial shows:
```
E lcd_panel.io.spi: panel_io_spi_tx_color(...): spi transmit (queue) color failed
E lcd_panel.st7789: panel_st7789_draw_bitmap(...): io tx color failed
```
Partial updates (small status-text redraws) work fine; only a full repaint hangs.

**Root cause:** The ESP32-S3 SPI master **cannot DMA directly from PSRAM**. If
the LVGL draw buffers are in PSRAM (`buff_spiram = true`), the driver falls back
to allocating a temporary internal-SRAM buffer and copying per transaction. On a
full-screen swap that allocation fails under memory pressure (WiFi holds internal
RAM), the flush never completes, and the LVGL port task blocks forever.

**Fix:** Keep LVGL draw buffers in **internal DMA-capable RAM**, not PSRAM:
```cpp
.flags = { .buff_dma = true, .buff_spiram = false, ... }
```
Keep the buffer small (10 lines × 320 × 2 bytes × double buffer ≈ 12.8 KB) —
internal DMA RAM is scarce, and a larger buffer starves `xTaskCreate` for the
WebSocket client (`E websocket_client: Error create websocket task`). Also keep
`spi_bus_config_t.max_transfer_sz` in sync with the buffer size and
`trans_queue_depth` shallow (2–4). See Espressif's SPI LCD note:
https://docs.espressif.com/projects/esp-techpedia/en/latest/esp-friends/advanced-development/lcd-application-note/spi-qspi-summary.html

### `lv_scr_load` must run in the LVGL task context

**Symptom:** Screen navigation either freezes the UI or silently does nothing.

**Root cause:** `lv_scr_load` may only be called from the LVGL task. From another
task (e.g. `uiTask`) it deadlocks; `lv_async_call` scheduled from another task is
not reliably flushed in our `LV_INDEV_MODE_EVENT` setup.

**Fix:** Trigger screen loads only from an LVGL-task context — either an LVGL
event callback (the settings **back** button) or an `lv_timer` callback (the
gear, via `pollSettingsFromLvglTask`, which the touch handler flags).

### Header buttons use coordinate-based touch, and fire on release

**Symptom:** With more than one `lv_btn` on a screen, clicks stop registering; or
a button that switches screens freezes the UI when tapped.

**Root cause:** LVGL click/edge events are unreliable on this FT6336U panel (the
same reason PTT is level-based). And triggering a screen swap on touch-*press*
(finger still down) leaves LVGL's input device pointing at an object on the
now-inactive old screen → freeze on the next input read.

**Fix:** Header buttons (gear, new-conversation) are plain non-clickable
containers; taps are detected by coordinates in
`MainScreen::updateHeaderButtonsFromTouch` and fire on **release**, like a real
click. Only PTT (which does not switch screens) may act on press.
