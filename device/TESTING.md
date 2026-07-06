# Device Firmware Testing

This document describes the automated test suites for the device firmware, how
to run them, and the issues encountered while building and running them
(especially on-device testing inside a VM).

There are two independent test layers:

| Layer | Where it runs | Framework | Hardware needed | Count |
|-------|---------------|-----------|-----------------|-------|
| **Native** | Host machine (x86/ARM) | GoogleTest + GMock | No | 77 cases / 8 suites |
| **On-device** | ESP32-S3 (CoreS3) | Unity | Yes (USB) | 25 cases / 1 binary |

Native tests are the day-to-day safety net (fast, deterministic, no hardware).
On-device tests verify the things only real hardware can prove (I2C peripherals,
I2S audio, PSRAM, WiFi radio, full boot).

---

## 1. Native Tests (host-side)

Run firmware logic on your development machine. No ESP32, no ESP-IDF toolchain.

```bash
cd device

# Run all native tests (~3 seconds)
uv run pio test -e native

# Run one suite
uv run pio test -e native -f test_native/test_session
```

### Suites

| Suite | Cases | Coverage |
|-------|-------|----------|
| `test_session` | 5 | Session state machine transitions; session ID generation from MAC |
| `test_audio_protocol` | 7 | Audio frame header parsing — magic `0x544B`, sample rate, channels, length guards |
| `test_ws_message` | 12 | WebSocket JSON parsing — all fields, truncation, malformed/empty/null input |
| `test_nvs_settings` | 17 | NVS-backed settings — volume, WiFi creds, host/port, defaults, factory reset |
| `test_serial_config` | 15 | AT command parsing — `AT+SSID`, `AT+PASS`, `AT+HOST`, `AT+PORT`, `AT+RESET`, invalid input |
| `test_ws_routing` | 8 | Integration: `WsClient::handleData` binary/text routing + fragment reassembly |
| `test_wake_word` | 11 | `FrameChunker` re-chunking (partials, boundaries, drain, reset) + `SilenceDetector` turn-end (silence-after-speech, speech floor, max cap) |
| `test_mocks` | 2 | Smoke test for the GMock `Display` / `BoardHAL` headers |

### How it works

The `[env:native]` environment (in `platformio.ini`) compiles firmware logic for
the host with GoogleTest. ESP-IDF dependencies are handled three ways:

- **Compat shims** (`test/test_native/compat/`) — minimal header stand-ins for
  `esp_log.h`, `nvs.h`, `freertos/*`, `esp_websocket_client.h`, `esp_wifi.h`,
  etc., so production headers parse without the real SDK.
- **Stubs** (`test/test_native/stubs/`) — in-memory implementations:
  - `nvs_stubs.cpp` — `unordered_map`-backed NVS
  - `esp_stubs.cpp` — fixed MAC, no-op `esp_restart`, `esp_err_to_name`
  - `freertos_stubs.cpp` — no-op tasks / queues / stream buffers
- **GMock** (`test/test_native/mocks/`) — mocks for the abstract `Display` and
  `BoardHAL` interfaces.

The env uses `build_src_filter = -<*>`, so **nothing is auto-compiled**. Each
test `.cpp` explicitly `#include`s the production source files it needs (and its
stubs). Pure parsing logic lives in `main/net/WsProtocol.cpp`, which was
extracted from `WsClient` specifically so it could be tested without the ESP
WebSocket stack.

`cJSON` is vendored under `test/test_native/libs/cJSON/` (with a `library.json`
whose `srcFilter` compiles only `cJSON.c`) so the suite builds from a clean
checkout with no network dependency.

### Adding a native test

1. Create `test/test_native/test_<name>/test_<name>.cpp`.
2. `#include` the production `.cpp` files and any stubs it needs.
3. Provide `int main(int argc, char** argv)` that calls `RUN_ALL_TESTS()`.
4. Run `uv run pio test -e native -f test_native/test_<name>`.

**Gotcha:** two source files that both define a `static const char* TAG` cannot
be included in the same translation unit without a `#define TAG ...` /
`#undef TAG` guard around each include (see `test_serial_config.cpp`).

---

## 2. On-Device Tests (CoreS3 via USB)

All 25 hardware cases live in **one** binary: `test/test_device/test_all/`.

```bash
cd device
uv run pio test -e cores3_test
```

### Groups (all inside `test_all`)

| Group | Coverage |
|-------|----------|
| HAL I2C | Bus probing (AXP2101 `0x34`, AW9523B `0x58`, ES7210 `0x40`, AW88298 `0x36`), full `Cores3HAL::init()`, volume/mic-gain writes |
| Audio I2S | Full-duplex init, mic delivers frames (proves I2S clock + DMA), speaker TX write, playback state |
| NVS flash | Real-flash write/read roundtrip, persistence across reopen, defaults, factory reset |
| Memory | PSRAM present, 512 KB alloc + pattern verify, stream buffer + queue allocation, internal RAM headroom |
| WiFi | Driver init + scan finds ≥1 AP (proves radio works) |
| Boot | Full boot: `Cores3HAL::init()` → `Assistant::init()` reaches `CONNECTING` |

### Requirements

- CoreS3 connected via USB (built-in USB-JTAG).
- No WiFi AP or backend required — but the WiFi scan expects at least one AP
  visible in the area.
- First run after connect may prompt for a manual reset (press the reset button
  when you see "If you don't see any output...").

### Why one binary (not one folder per group)

This is the single most important design decision, and it exists because of the
issues in §3.

PlatformIO's Unity runner flashes and **resets the chip once per test folder**.
On the ESP32-S3 the USB-Serial-JTAG endpoint drops and re-enumerates on every
reset. In a VM with USB passthrough, rapid consecutive re-enumerations wedge the
endpoint, so a multi-folder run hangs on serial read after the first suite.

Consolidating every case into one folder gives **one flash, one reset, one
serial session** — no repeated re-enumeration, so the whole suite runs
consecutively without unplugging the cable.

The cost: global peripheral state persists between cases, so tests must tear
down shared hardware at group boundaries. See the `ensure_*` guards and
teardown helpers in `test_all.cpp`.

### Running a subset

To debug one group, comment out the unwanted `RUN_TEST(...)` lines in
`app_main()` inside `test_all.cpp` and re-run.

### How it works

`[env:cores3_test]` extends `[env:cores3]` and adds:

- `test_framework = unity` — ESP-IDF's native test framework
- `test_filter = test_device/test_all` — the single consolidated binary
- `test_build_src = true` — compiles the production `main/` sources
- `-DDEVICE_TEST` — gates out the real `app_main` in `main/main.cpp` so the
  test's `app_main` is used instead

`test_all.cpp` provides `app_main`: it runs `UNITY_BEGIN()`, all `RUN_TEST(...)`
cases grouped by subsystem, then `UNITY_END()`. PlatformIO flashes the binary,
resets the device, and parses Unity output from the serial console.

---

## 3. Issues Encountered

### 3.1 Native build

- **cJSON test files collided with the test `main()`.** The upstream cJSON repo
  ships `test.c` and `fuzzing/*.c`, each with their own `main()`, which fought
  GoogleTest's `main()` at link time. Fixed by vendoring cJSON into
  `test/test_native/libs/cJSON/` with a `library.json` that compiles only
  `cJSON.c`. This also removed the runtime git dependency so the suite builds
  from a clean checkout.
- **`framework = espidf` was inherited by the native env**, causing PlatformIO
  to demand a `board`. Fixed by clearing `framework =` and `extra_scripts =` in
  `[env:native]`.
- **Duplicate `static TAG` symbols** when one test includes two production
  `.cpp` files. Resolved with `#define TAG ... / #undef TAG` guards around the
  includes.
- **GoogleTest `main()` not auto-linked** — each native test provides its own
  `main()` calling `RUN_ALL_TESTS()`.

### 3.2 On-device — the big one: serial read hangs

**Symptom:** the test firmware flashed successfully ("Programming Finished /
Verify OK"), but PlatformIO then hung at `Testing...` with
`device reports readiness to read but returned no data`. The first suite after a
fresh USB connect always worked; the second and later ones hung.

**Environment:** Ubuntu on a **Parallels VM**, CoreS3 attached via **USB
passthrough**. Console is USB-Serial-JTAG (`CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y`),
flashed over the same built-in USB via OpenOCD (`upload_protocol = esp-builtin`).

**Root cause:** the ESP32-S3 USB-Serial-JTAG endpoint drops off the USB bus and
re-enumerates on every chip reset. PlatformIO resets the chip once per test
folder, then opens the serial port to read Unity output. In the VM, the
passthrough tolerates one or two rapid re-enumerations, then wedges the endpoint
until a physical replug — and the console prints its output once at boot without
buffering for an absent host, so any output printed before the host reader
re-attaches is lost.

**What made it worse:** interrupting a hung run mid-serial-read, and running
standalone OpenOCD sessions, further degraded the USB state. The runs that
succeeded were always immediately after a physical unplug/replug.

**Fixes applied:**

1. **Consolidated all suites into one binary** (§2) — the primary fix. One
   flash, one reset, one serial session eliminates the repeated re-enumeration
   that triggered the wedge.
2. **Stable serial port path.** `platformio_local.ini` points `monitor_port` /
   `test_port` at `/dev/serial/by-id/usb-Espressif_USB_JTAG_...` instead of
   `/dev/ttyACM0`. In the VM the `ttyACM<N>` number changes on re-enumeration;
   the `by-id` path always resolves to the right device.
3. **Wait for USB host before printing.** `test_all.cpp`'s `app_main` calls
   `usb_serial_jtag_is_connected()` (up to ~10 s) before `UNITY_BEGIN()`, so
   output is not emitted into a disconnected console.

**Residual limitation:** even with all three, the VM can still occasionally miss
the read window if the port re-enumerates to a new number mid-run. The firmware
runs correctly; only the host-side capture is affected. When it happens:

- Unplug/replug the USB cable once, then run again (this is the known-good
  condition).
- Make sure no other process holds the port:
  `ps aux | grep "pio device monitor"`.
- Run uninterrupted — killing a hung run tends to wedge the endpoint for the
  next attempt.

This is environmental to VM USB passthrough. On a bare-metal Linux/macOS host
(or with the board on a native USB port rather than passthrough) the
re-enumeration is fast enough that it does not occur.

### 3.3 On-device — bugs the consolidation exposed

Running every case in a single boot (instead of a fresh boot per folder)
surfaced real teardown/ordering bugs that per-folder isolation had hidden:

- **Boot loop.** The WiFi test created the default event loop and STA netif but
  never destroyed them. The later boot test's `WiFiManager::init()` then called
  `ESP_ERROR_CHECK(esp_event_loop_create_default())`, which **aborts** when the
  loop already exists → panic → reboot → Unity restarts from the top → infinite
  loop (this is what looked like an endless "hang"). Fixed by fully tearing down
  WiFi in the scan test: `esp_wifi_stop/deinit`, `esp_netif_destroy_default_wifi`,
  `esp_event_loop_delete_default`.
- **I2C double-install.** `Cores3HAL` installs the I2C driver in `init()` but has
  no destructor to release it, so the boot test's fresh HAL failed to re-install.
  Fixed by calling `i2c_driver_delete(I2C_NUM_0)` before the boot test re-inits.
- **I2S channel deleted out from under later tests.** The mic test originally
  called `AudioCapture::stop()`, which deletes the shared I2S channels; the
  following speaker/playback tests then reused the (now dead) capture object and
  failed with `I2S TX write failed`. Fixed by using `pause()` (which only gates
  frame queuing) instead of `stop()`, leaving the channels alive until the group
  boundary tears them down.
- **Flaky mic assertion.** The mic test asserted non-zero PCM samples, which
  depends on ambient room noise — a silent room legitimately reads all zeros on
  a working mic. Reworked to assert **frame delivery** (deterministic proof the
  I2S clock and DMA are running) and downgrade the non-zero check to a soft
  `ESP_LOGW` warning. A prior test also lowers mic gain via `setMicGain(50)`, so
  the mic test now restores `setMicGain(100)` first to avoid depending on
  earlier tests' side effects.

---

## 4. Quick Reference

```bash
cd device

# Native (fast, no hardware) — run this constantly
uv run pio test -e native

# On-device (needs CoreS3 over USB) — run before hardware-affecting changes
uv run pio test -e cores3_test

# Production builds (verify nothing broke)
uv run pio run -e cores3
uv run pio run -e pyramid
```

**If on-device hangs at `Testing...`:** unplug/replug the USB cable, ensure no
`pio device monitor` is running, and re-run uninterrupted. See §3.2.
