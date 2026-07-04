# Device Firmware Tests

## Native Tests (host-side, no hardware needed)

Runs on your development machine using GoogleTest + GMock:

```bash
cd device

# Run all native tests (66 test cases)
uv run pio test -e native

# Run a single suite
uv run pio test -e native -f test_native/test_session
```

### Native Test Suites

| Suite | Coverage |
|-------|----------|
| `test_session` | Session state machine transitions, session ID generation from MAC |
| `test_audio_protocol` | Audio frame header parsing (magic, sample rate, channels, length checks) |
| `test_ws_message` | WebSocket JSON message parsing (all fields, truncation, malformed input) |
| `test_nvs_settings` | NVS-backed settings: volume, WiFi creds, backend host/port, factory reset |
| `test_serial_config` | AT command parsing (`AT+SSID`, `AT+PORT`, `AT+RESET`, etc.) |
| `test_ws_routing` | Integration: `WsClient::handleData` routing, fragment reassembly |
| `test_mocks` | Smoke test for the GMock `Display`/`BoardHAL` headers |

### How Native Tests Work

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

### Adding a Native Test

1. Create `test_native/test_<name>/test_<name>.cpp`.
2. `#include` the production `.cpp` files and any stubs it needs.
3. Provide `int main(argc, argv)` calling `RUN_ALL_TESTS()`.
4. Run `uv run pio test -e native -f test_native/test_<name>`.

Note: two source files that both define a `static TAG` cannot be included in
the same translation unit without a `#define TAG ...` / `#undef TAG` guard
around each include (see `test_serial_config.cpp`).

---

## On-Device Tests (requires CoreS3 via USB)

Flashes a single test firmware binary to the ESP32-S3, runs all hardware test
cases in one boot via the Unity framework, and reads results over serial.
Verifies the hardware actually works.

```bash
cd device
uv run pio test -e cores3_test
```

All 25 hardware test cases live in ONE binary (`test/test_device/test_all/`).
This is deliberate — see "Why one binary" below.

### On-Device Test Groups (all in test_all)

| Group | Coverage |
|-------|----------|
| HAL I2C | Bus probing (AXP2101, AW9523B, ES7210, AW88298), full `Cores3HAL::init()` |
| Audio I2S | Full-duplex init, mic delivers frames (I2S clock/DMA), speaker TX, playback |
| NVS flash | Real-flash write/read roundtrip, persistence, defaults, factory reset |
| Memory | PSRAM availability, 512KB alloc, stream buffer + queue allocation |
| WiFi | Driver init + scan finds APs (proves radio works) |
| Boot | Full boot sequence: HAL + `Assistant::init()` reaches CONNECTING state |

### Requirements

- CoreS3 device connected via USB (built-in USB-JTAG)
- No WiFi AP or backend needed (tests are self-contained), but the WiFi scan
  test expects at least one AP visible in the area
- First run after connect may need a manual reset (press reset button when
  prompted by "If you don't see any output...")

### Why one binary (not one per group)

PlatformIO's Unity runner flashes and **resets the chip once per test folder**.
On the ESP32-S3 the USB-Serial-JTAG endpoint drops and re-enumerates on every
reset. In a VM with USB passthrough (e.g. Parallels), rapid consecutive
re-enumerations wedge the endpoint, so a multi-folder run hangs on serial read
after the first suite.

Consolidating all cases into one folder means **one flash, one reset, one
serial session** — no repeated re-enumeration, so the whole suite runs
consecutively without unplugging the cable.

The cost is that global peripheral state persists between cases, so tests must
tear down shared hardware (I2C driver, I2S channels, WiFi netif + event loop)
at group boundaries. See the teardown helpers and `ensure_*` guards in
`test_all.cpp`.

### Environmental / VM notes

- **Serial read still occasionally misses the window** in the VM if the port
  re-enumerates to a new `ttyACM*` number mid-run. The firmware runs fine; only
  the host read is affected. Re-run, or unplug/replug once.
- If output never appears, confirm no other process holds the port
  (`ps aux | grep "pio device monitor"`), and that `platformio_local.ini`
  points `test_port`/`monitor_port` at the stable `/dev/serial/by-id/...` path.

### How On-Device Tests Work

The `[env:cores3_test]` environment extends `[env:cores3]` and adds:
- `test_framework = unity` — ESP-IDF's native test framework
- `test_filter = test_device/test_all` — the single consolidated binary
- `test_build_src = true` — compiles production `main/` sources
- `-DDEVICE_TEST` — gates out `app_main` in `main.cpp`

`test_all.cpp` provides `app_main`, which runs `UNITY_BEGIN()`, all `RUN_TEST(...)`
cases grouped by subsystem, then `UNITY_END()`. PlatformIO flashes the binary,
resets the device, and parses Unity output from serial.

To run a subset while debugging, comment out `RUN_TEST(...)` lines in
`test_all.cpp`'s `app_main`.
