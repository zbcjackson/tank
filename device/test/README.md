# Device Firmware Tests

Host-side (native) unit and integration tests for the device firmware. These run
on your development machine — no ESP32 hardware or ESP-IDF toolchain required.

## Running

```bash
cd device

# Run all native tests
uv run pio test -e native

# Run a single suite
uv run pio test -e native -f test_native/test_session
```

## Test Suites

| Suite | Coverage |
|-------|----------|
| `test_session` | Session state machine transitions, session ID generation from MAC |
| `test_audio_protocol` | Audio frame header parsing (magic, sample rate, channels, length checks) |
| `test_ws_message` | WebSocket JSON message parsing (all fields, truncation, malformed input) |
| `test_nvs_settings` | NVS-backed settings: volume, WiFi creds, backend host/port, factory reset |
| `test_serial_config` | AT command parsing (`AT+SSID`, `AT+PORT`, `AT+RESET`, etc.) |
| `test_ws_routing` | Integration: `WsClient::handleData` routing, fragment reassembly |
| `test_mocks` | Smoke test for the GMock `Display`/`BoardHAL` headers |

## How It Works

The native environment (`[env:native]` in `platformio.ini`) compiles firmware
logic for the host using GoogleTest. ESP-IDF dependencies are handled three ways:

- **Compat shims** (`test_native/compat/`) — minimal header stand-ins for
  `esp_log.h`, `nvs.h`, `freertos/*`, `esp_websocket_client.h`, etc. so
  production headers parse without the real SDK.
- **Stubs** (`test_native/stubs/`) — in-memory implementations: `nvs_stubs.cpp`
  (unordered_map-backed NVS), `esp_stubs.cpp` (fixed MAC, no-op restart),
  `freertos_stubs.cpp` (no-op tasks/queues).
- **GMock** (`test_native/mocks/`) — mocks for the abstract `Display` and
  `BoardHAL` interfaces.

Each test `.cpp` explicitly `#include`s the production source files it needs
(the native env uses `build_src_filter = -<*>` so nothing is auto-compiled).
Pure parsing logic lives in `main/net/WsProtocol.cpp`, extracted from `WsClient`
so it can be tested without the ESP WebSocket stack.

## Adding a Test

1. Create `test_native/test_<name>/test_<name>.cpp`.
2. `#include` the production `.cpp` files and any stubs it needs.
3. Provide `int main(argc, argv)` calling `RUN_ALL_TESTS()`.
4. Run `uv run pio test -e native -f test_native/test_<name>`.

Note: two source files that both define a `static TAG` cannot be included in
the same translation unit without a `#define TAG ...` / `#undef TAG` guard
around each include (see `test_serial_config.cpp`).
