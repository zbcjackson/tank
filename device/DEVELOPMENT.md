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
