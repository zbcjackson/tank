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
#define CONFIG_PUSH_TO_TALK      0
#endif

// Wake word: an on-device WakeNet engine (esp-sr, stock "Hi ESP") listens
// while idle. On detection the device sends `interrupt` + `wake`, streams the
// utterance, and ends the turn on trailing silence (SilenceDetector). Mutually
// exclusive with push-to-talk — there is no button to gate streaming.
#ifndef CONFIG_WAKE_WORD
#define CONFIG_WAKE_WORD         1
#endif

#if CONFIG_WAKE_WORD && CONFIG_PUSH_TO_TALK
#error "CONFIG_WAKE_WORD and CONFIG_PUSH_TO_TALK are mutually exclusive — set CONFIG_PUSH_TO_TALK=0 to use wake-word mode."
#endif

// ─── Wake word turn-end (SilenceDetector) ─────────────────────────────────────
// Units are 20ms mic frames. Defaults: ~800ms trailing silence ends the turn,
// at least ~200ms of speech must occur first, and a 15s cap prevents a noisy
// room from streaming forever.
#define CONFIG_WAKE_SPEECH_RMS       800   // frame RMS above this counts as speech
#define CONFIG_WAKE_SILENCE_FRAMES   40    // 40 × 20ms = 800ms trailing silence
#define CONFIG_WAKE_MIN_SPEECH_FRAMES 10   // 10 × 20ms = 200ms speech floor
#define CONFIG_WAKE_MAX_FRAMES       750   // 750 × 20ms = 15s hard cap

// Echo hangover: this board has no acoustic echo cancellation and the speaker
// couples strongly into the mic, so the assistant's own TTS can self-trigger
// WakeNet. Suppress detection while playback is active AND for this long after
// it goes quiet, to cover the acoustic tail + I2S DMA drain. Frames captured
// during this window are dropped from the detector so a partial match spanning
// the boundary can't complete.
#define CONFIG_WAKE_ECHO_HANGOVER_MS 700


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
#define CONFIG_SPK_QUEUE_LEN     50   // ~1000ms of playback buffered (absorbs TTS burst delivery)
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
