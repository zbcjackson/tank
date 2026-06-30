# Tank Device Client

ESP32-S3 firmware for M5Stack hardware that connects to the Tank Voice Assistant backend.

## Hardware Targets

| Target | Board | Display | Audio |
|--------|-------|---------|-------|
| `cores3` | M5Stack CoreS3 | 2.0" 320×240 IPS + touch | ES7210 mic + AW88298 amp |
| `pyramid` | Voice Pyramid + AtomS3R | 0.85" 128×128 + 28 LEDs | ES7210 + ES8311 + AW87559 |

## Prerequisites

- Python 3.10+ with [uv](https://docs.astral.sh/uv/)
- USB-C cable connected to the device
- Tank backend running on your network

## Quick Start

```bash
cd device

# Install build tooling (PlatformIO, managed by uv)
uv sync

# Configure WiFi and backend (edit before first build)
# → main/config.h: CONFIG_WIFI_SSID, CONFIG_WIFI_PASSWORD, CONFIG_BACKEND_HOST

# Build for CoreS3
uv run pio run -e cores3

# Flash
uv run pio run -e cores3 -t upload

# Monitor serial output
uv run pio device monitor
```

## Configuration

Compile-time defaults live in `main/config.h` (used on first boot before anything is saved):

```c
#define CONFIG_WIFI_SSID      "YOUR_SSID"
#define CONFIG_WIFI_PASSWORD  "YOUR_PASSWORD"
#define CONFIG_BACKEND_HOST   "192.168.1.100"
#define CONFIG_BACKEND_PORT   8000
```

### Runtime configuration

**Volume** — adjust on-device via the Settings screen (tap the gear icon, then the
`-` / `+` buttons). The level is saved to NVS and restored on the next boot.

**Network** — configure WiFi and backend over the USB serial monitor using AT
commands. Values are saved to NVS; `AT+SAVE` reboots the device to apply them:

```
AT+SSID=MyNetwork      # set WiFi SSID
AT+PASS=secret         # set WiFi password
AT+HOST=192.168.1.50   # set backend host
AT+PORT=8000           # set backend port
AT+INFO                # print current config (password masked)
AT+SAVE                # reboot and apply
AT+RESET               # factory reset (erase NVS, reboot)
```

NVS-stored values override the `config.h` defaults.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design.

```
[Mic] → I2S → capture_task → mic_queue → ws_send_task → WebSocket → [Backend]
[Backend] → WebSocket → ws_recv_task → spk_queue → playback_task → I2S → [Speaker]
                                     → event_queue → ui_task → [Display]
```

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for full guide.

```bash
# Build
uv run pio run -e cores3

# Build + flash + monitor (all-in-one)
uv run pio run -e cores3 -t upload && uv run pio device monitor

# Clean build
uv run pio run -e cores3 -t clean

# Build for Pyramid target
uv run pio run -e pyramid
```

## Project Status

- [x] Project skeleton, build system
- [x] WiFi connection with auto-reconnect
- [x] WebSocket client (binary audio + JSON)
- [x] Audio capture (I2S mic → PCM → WebSocket)
- [x] Audio playback (WebSocket → PCM → I2S speaker)
- [x] LCD display UI framework (CoreS3 + Pyramid)
- [x] Touch controls (mute, interrupt)
- [ ] Bitmap font rendering (or LVGL integration)
- [ ] Pyramid hardware validation (ES8311, LED ring animations)
- [ ] NVS-based WiFi provisioning
