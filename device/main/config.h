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

// ─── Interaction ──────────────────────────────────────────────────────────────
// The device always supports two ways to start a turn, at any time:
//   - Wake word: an on-device WakeNet engine (esp-sr, stock "Hi ESP") listens
//     while idle. On detection the device sends `interrupt` + `wake`, streams
//     the utterance, and ends the turn on trailing silence (SilenceDetector).
//   - Push-to-talk: the on-screen button streams while held; release sends
//     `end_of_utterance`.

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

// ─── AEC (CoreS3 only) ────────────────────────────────────────────────────────
// The AFE (esp-sr Audio Front End) does acoustic echo cancellation: given the
// mic signal and a reference of what the speaker is playing, it subtracts the
// echo. It needs that reference from somewhere. Two sources:
//
//   Software reference (CONFIG_AEC_HW_REF=0, default): AudioPlayback copies each
//   frame it sends to the speaker into a ring buffer; the AFE feed path pairs
//   the live mic frame with the matching playback frame as the reference. This
//   is the digital signal *before* the amp — no extra wiring, works on any unit.
//   The mic stays on the simple standard-I2S mono path.
//
//   Hardware reference (CONFIG_AEC_HW_REF=1): the CoreS3 schematic wires the amp
//   output (AW88298) through a 150K attenuator (R40/R42, nets AEC_P/AEC_N) into
//   the ES7210's MIC3 ADC. Reading MIC3 needs 4-slot TDM (standard I2S exposes
//   only MIC1/MIC2). Verified on 2026-07-09: R40/R42 are NOT populated on this
//   board — MIC3 reads noise floor during playback (ref_peak_hold ≈ mic noise,
//   erle ≈ 2dB). Only enable this if you solder the resistors. See
//   [[cores3-aec-hardware-reference]].
//
// AEC is CoreS3-only: the Pyramid has a different codec chain (ES8311 + AW87559)
// and keeps the standard mono capture + WakeNet + echo-hangover path.
#if defined(TARGET_CORES3)
#define CONFIG_AEC_ENABLE          1     // Build the AFE echo-cancellation path
#else
#define CONFIG_AEC_ENABLE          0
#endif
#define CONFIG_AEC_HW_REF          0     // 1 = analog MIC3 ref via TDM (needs R40/R42 soldered)
#define CONFIG_AEC_DIAG            1     // Update JTAG-readable g_aec_diag (mic/ref/out power, ERLE)
#define CONFIG_AEC_TEST_TONE       0     // 1 = play a 1kHz tone at boot to self-test AEC (diagnostic)
#define CONFIG_AEC_TDM_SLOTS       4     // (HW ref only) ES7210 emits 4 TDM slots (MIC1..MIC4)
#define CONFIG_AEC_MIC_SLOT        0     // (HW ref only) Slot 0 = MIC1 (physical microphone)
#define CONFIG_AEC_REF_SLOT        2     // (HW ref only) Slot 2 = MIC3 (speaker echo reference)
#define CONFIG_AFE_MIC_NUM         1     // Physical microphones fed to the AFE
#define CONFIG_AFE_REF_NUM         1     // Reference channels fed to the AFE
#define CONFIG_AFE_TOTAL_CH        (CONFIG_AFE_MIC_NUM + CONFIG_AFE_REF_NUM)

#define CONFIG_SPK_SAMPLE_RATE   16000  // Unified with mic rate (full-duplex shared clock)
#define CONFIG_SPK_CHANNELS      1
#define CONFIG_SPK_BITS          16
#define CONFIG_SPK_FRAME_MS      20   // 20ms per playback frame

// Frame size in bytes: sample_rate * channels * (bits/8) * (frame_ms/1000)
#define CONFIG_MIC_FRAME_BYTES   (CONFIG_MIC_SAMPLE_RATE * CONFIG_MIC_CHANNELS * (CONFIG_MIC_BITS / 8) * CONFIG_MIC_FRAME_MS / 1000)
#define CONFIG_SPK_FRAME_BYTES   (CONFIG_SPK_SAMPLE_RATE * CONFIG_SPK_CHANNELS * (CONFIG_SPK_BITS / 8) * CONFIG_SPK_FRAME_MS / 1000)

// Bytes per mic_queue item. With the hardware reference the capture task pushes
// an interleaved [mic, ref] TDM frame (CONFIG_AFE_TOTAL_CH channels); with the
// software reference (default) it pushes a plain mono mic frame and the feed
// task pairs it with the buffered playback reference.
#if CONFIG_AEC_ENABLE && CONFIG_AEC_HW_REF
#define CONFIG_MIC_QUEUE_ITEM_BYTES  (CONFIG_MIC_FRAME_BYTES * CONFIG_AFE_TOTAL_CH)
#else
#define CONFIG_MIC_QUEUE_ITEM_BYTES  (CONFIG_MIC_FRAME_BYTES)
#endif

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
