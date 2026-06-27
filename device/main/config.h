#pragma once

// ─── Network ────────────────────────────────────────────────────────────────
// These are set via build flags in platformio.ini (from environment variables).
// Override at build time:
//   TANK_WIFI_SSID=MyNetwork TANK_WIFI_PASSWORD=secret TANK_BACKEND_HOST=192.168.1.100 uv run pio run -e cores3
#ifndef CONFIG_WIFI_SSID
#define CONFIG_WIFI_SSID         "changeme"
#endif

#ifndef CONFIG_WIFI_PASSWORD
#define CONFIG_WIFI_PASSWORD     "changeme"
#endif

#ifndef CONFIG_BACKEND_HOST
#define CONFIG_BACKEND_HOST      "192.168.1.100"
#endif

#ifndef CONFIG_BACKEND_PORT
#define CONFIG_BACKEND_PORT      8000
#endif

#ifndef CONFIG_SESSION_ID
#define CONFIG_SESSION_ID        "device_001"
#endif

// ─── Interaction mode ─────────────────────────────────────────────────────────
// Push-to-talk: mic only streams while the on-screen button is held; release
// sends end_of_utterance. Set to 0 for continuous (always-streaming) mode.
// A runtime mode-switching setting page is planned for later.
#ifndef CONFIG_PUSH_TO_TALK
#define CONFIG_PUSH_TO_TALK      1
#endif

// ─── Audio ──────────────────────────────────────────────────────────────────
#define CONFIG_MIC_SAMPLE_RATE   16000
#define CONFIG_MIC_CHANNELS      1
#define CONFIG_MIC_BITS          16
#define CONFIG_MIC_FRAME_MS      20   // 20ms per frame = 320 samples at 16kHz

#define CONFIG_SPK_SAMPLE_RATE   16000  // Unified with mic rate (full-duplex shared clock)
#define CONFIG_SPK_CHANNELS      1
#define CONFIG_SPK_BITS          16
#define CONFIG_SPK_FRAME_MS      20   // 20ms per playback frame

// Frame size in bytes: sample_rate * channels * (bits/8) * (frame_ms/1000)
#define CONFIG_MIC_FRAME_BYTES   (CONFIG_MIC_SAMPLE_RATE * CONFIG_MIC_CHANNELS * (CONFIG_MIC_BITS / 8) * CONFIG_MIC_FRAME_MS / 1000)
#define CONFIG_SPK_FRAME_BYTES   (CONFIG_SPK_SAMPLE_RATE * CONFIG_SPK_CHANNELS * (CONFIG_SPK_BITS / 8) * CONFIG_SPK_FRAME_MS / 1000)

// ─── Queues ─────────────────────────────────────────────────────────────────
#define CONFIG_MIC_QUEUE_LEN     10   // ~200ms of mic audio buffered
#define CONFIG_SPK_QUEUE_LEN     20   // ~400ms of playback buffered
#define CONFIG_EVENT_QUEUE_LEN   16

// ─── Tasks ──────────────────────────────────────────────────────────────────
#define CONFIG_AUDIO_TASK_CORE       0
#define CONFIG_AUDIO_TASK_PRIORITY   22
#define CONFIG_AUDIO_TASK_STACK      4096

#define CONFIG_NET_TASK_CORE         1
#define CONFIG_NET_TASK_PRIORITY     18
#define CONFIG_NET_TASK_STACK        8192

#define CONFIG_UI_TASK_CORE          1
#define CONFIG_UI_TASK_PRIORITY      5
#define CONFIG_UI_TASK_STACK         8192

// ─── Protocol ───────────────────────────────────────────────────────────────
#define AUDIO_FRAME_MAGIC        0x544B  // "TK" — Tank audio frame header
#define AUDIO_FRAME_HEADER_SIZE  8       // magic(2) + sample_rate(4) + channels(2)

// ─── Reconnection ───────────────────────────────────────────────────────────
#define CONFIG_WIFI_RETRY_MAX    10
#define CONFIG_WS_RECONNECT_MS   3000
#define CONFIG_WS_NETWORK_TIMEOUT_MS  30000
#define CONFIG_WS_PINGPONG_TIMEOUT_S  30
#define CONFIG_TANK_WS_BUFFER_SIZE    8192
