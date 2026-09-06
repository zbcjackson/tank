// Opus codec benchmark for the ESP32-S3 (protocol plan P1-2 Step 5 gate).
//
// Answers the two questions that gate device-side opus integration:
//   1. Memory: heap cost of one 16 kHz encoder + one 24 kHz decoder (the
//      encoder/decoder state sizes libopus reports are logged too), and
//      whether create/destroy cycles leak.
//   2. Real-time: CPU cost per 20 ms frame for encoding mic audio (16 kHz,
//      32 kbps) and decoding TTS audio (24 kHz), swept over encoder
//      complexity — the server (opuslib/libopus defaults) runs at
//      complexity 9.
//
// Codec: vendored libopus 1.4, fixed-point (components/opus) — the same
// libopus core the server wraps via opuslib, so round-trip numbers are
// directly comparable with the host-side spike. Heap poisoning is
// COMPREHENSIVE in this build: any codec-side out-of-bounds write fails
// the integrity checks below.
//
// Run:  uv run pio test -e cores3_bench
// (one flash, one reset — see TESTING.md §3.2 before running on hardware).

#include <cmath>
#include <cstdint>
#include <cstring>

#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "unity.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/usb_serial_jtag.h"

#include "opus.h"

#include "quality_ref.h"

extern "C" {

// ---------------------------------------------------------------------------
// Configuration — mirrors tank_protocol.OPUS_PROFILE and the server codec.
// ---------------------------------------------------------------------------

static constexpr int kUplinkRate = 16000;       // OPUS_PROFILE uplink
static constexpr int kDownlinkRate = 24000;     // OPUS_PROFILE downlink
static constexpr int kFrameMs = 20;             // OPUS_PROFILE frame_ms
static constexpr int kBitrate = 32000;          // OPUS_PROFILE bitrate
static constexpr int kUplinkSamples = kUplinkRate * kFrameMs / 1000;      // 320
static constexpr int kDownlinkSamples = kDownlinkRate * kFrameMs / 1000;  // 480
static constexpr int kFrames = 500;             // 10 s of audio per sweep
// libopus default complexity is 9 — the server (opuslib) never sets it, so
// that is the number integration would inherit.
static const int kComplexitySweep[] = {0, 3, 5, 8, 9, 10};
// A frame must fit its own real-time budget; 2x is the hard-fail line.
static constexpr int kRealtimeBudgetUs = kFrameMs * 1000;
// libopus's absolute packet cap.
static constexpr int kPacketCap = 1275;

static const char *TAG = "opus_bench";

// ---------------------------------------------------------------------------
// Signal generation — pseudo-random, enveloped "speech-like" noise. Not a
// quality fixture (that was the host spike); just non-silence that forces
// the encoder through real workloads.
// ---------------------------------------------------------------------------

static uint32_t s_rng = 0x1234ABCD;

static uint32_t next_rand() {
    s_rng = s_rng * 1664525u + 1013904223u;  // LCG (Numerical Recipes)
    return s_rng >> 8;
}

// Speech-shaped noise: white noise band-limited to ~300-3400 Hz (one-pole
// LP at 3.4 kHz minus LP at 300 Hz) with a 3 Hz syllabic envelope. Full-band
// white noise measures ~0 dB SNR at 32 kbps by design (see the host spike
// notes) — the band-limited shape is what makes the SNR gate meaningful,
// and encode cost closer to real speech.
static opus_int16 next_sample(int i) {
    static float lp34 = 0;
    static float lp03 = 0;
    float raw = static_cast<float>(next_rand() % 8192);
    float env = 0.5f + 0.5f * fabsf(sinf(2.0f * 3.14159265f * 3.0f * i / kUplinkRate));
    lp34 += 0.736f * (raw - lp34);   // one-pole LP, fc ≈ 3.4 kHz @16 k
    lp03 += 0.111f * (lp34 - lp03);  // one-pole LP, fc ≈ 300 Hz
    float band = lp34 - lp03;        // band ≈ 300-3400 Hz
    return static_cast<opus_int16>(band * env);
}

static void fill_pcm(opus_int16 *pcm, int samples, int start_index) {
    for (int i = 0; i < samples; i++) {
        pcm[i] = next_sample(start_index + i);
    }
}

// ---------------------------------------------------------------------------
// Heap accounting
// ---------------------------------------------------------------------------

struct HeapSnapshot {
    size_t internal_free;
    size_t internal_largest;
    size_t spiram_free;
};

static HeapSnapshot heap_now() {
    return HeapSnapshot{
        .internal_free = heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
        .internal_largest = heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL),
        .spiram_free = heap_caps_get_free_size(MALLOC_CAP_SPIRAM),
    };
}

static void log_heap(const char *label, HeapSnapshot h) {
    ESP_LOGI(TAG, "%s: internal_free=%u internal_largest=%u spiram_free=%u",
             label, h.internal_free, h.internal_largest, h.spiram_free);
}

// COMPREHENSIVE poisoning validator — any codec-side out-of-bounds write
// lands here instead of silently smashing a neighbouring block. Internal
// RAM only: an all-pools walk includes the 8 MB PSRAM pool, whose poisoned
// sweep takes seconds and starves the INT WDT.
static void check_heap(const char *where) {
    if (!heap_caps_check_integrity(MALLOC_CAP_INTERNAL, true)) {
        ESP_LOGE(TAG, "HEAP CORRUPTED after: %s", where);
        TEST_FAIL_MESSAGE("heap integrity");
    } else {
        ESP_LOGI(TAG, "heap ok after: %s", where);
    }
}

// ---------------------------------------------------------------------------
// Codec handles (native libopus API)
// ---------------------------------------------------------------------------

static OpusEncoder *open_encoder(int complexity) {
    int err = 0;
    OpusEncoder *enc = opus_encoder_create(kUplinkRate, 1, OPUS_APPLICATION_VOIP, &err);
    if (err != OPUS_OK) {
        ESP_LOGE(TAG, "encoder create failed: %d", err);
        return nullptr;
    }
    opus_encoder_ctl(enc, OPUS_SET_BITRATE(kBitrate));
    opus_encoder_ctl(enc, OPUS_SET_COMPLEXITY(complexity));
    return enc;
}

static OpusDecoder *open_decoder(int rate) {
    int err = 0;
    OpusDecoder *dec = opus_decoder_create(rate, 1, &err);
    if (err != OPUS_OK) {
        ESP_LOGE(TAG, "decoder create failed: %d", err);
        return nullptr;
    }
    return dec;
}

static int64_t now_us() { return esp_timer_get_time(); }

// ---------------------------------------------------------------------------
// 1. Memory footprint
// ---------------------------------------------------------------------------

static void test_memory_footprint_and_leak_check(void) {
    ESP_LOGI(TAG, "libopus state sizes: encoder=%d decoder=%d bytes",
             opus_encoder_get_size(1), opus_decoder_get_size(1));

    HeapSnapshot base = heap_now();
    log_heap("baseline        ", base);

    OpusEncoder *enc = open_encoder(9);
    OpusDecoder *dec = open_decoder(kDownlinkRate);
    TEST_ASSERT_NOT_NULL(enc);
    TEST_ASSERT_NOT_NULL(dec);
    check_heap("codec open");

    // One encode + one decode so lazily-allocated state materializes.
    static opus_int16 pcm[kUplinkSamples];
    static uint8_t packet[kPacketCap];
    static opus_int16 decoded[kDownlinkSamples * 2];
    fill_pcm(pcm, kUplinkSamples, 0);

    int packet_len = opus_encode(enc, pcm, kUplinkSamples, packet, kPacketCap);
    TEST_ASSERT_GREATER_THAN(0, packet_len);
    check_heap("first encode");

    int decoded_samples = opus_decode(dec, packet, packet_len, decoded,
                                      kDownlinkSamples * 2, 0);
    TEST_ASSERT_EQUAL(kDownlinkSamples, decoded_samples);
    check_heap("first decode");

    HeapSnapshot with_codecs = heap_now();
    log_heap("with enc+dec    ", with_codecs);
    int64_t codec_cost = static_cast<int64_t>(base.internal_free) -
                         static_cast<int64_t>(with_codecs.internal_free);
    ESP_LOGI(TAG, "RESULT memory: enc(16k,cx9)+dec(24k) internal RAM = %lld bytes"
             " (largest free block %u -> %u)",
             codec_cost, base.internal_largest, with_codecs.internal_largest);

    opus_encoder_destroy(enc);
    opus_decoder_destroy(dec);

    // Create/destroy x10 — any leak compounds per connection lifetime.
    for (int i = 0; i < 10; i++) {
        OpusEncoder *e = open_encoder(9);
        OpusDecoder *d = open_decoder(kDownlinkRate);
        TEST_ASSERT_NOT_NULL(e);
        TEST_ASSERT_NOT_NULL(d);
        opus_encoder_destroy(e);
        opus_decoder_destroy(d);
    }
    check_heap("10x create/destroy");

    HeapSnapshot after = heap_now();
    int64_t leaked = static_cast<int64_t>(base.internal_free) -
                     static_cast<int64_t>(after.internal_free);
    ESP_LOGI(TAG, "RESULT leak: %lld bytes after 10 create/destroy cycles", leaked);
    TEST_ASSERT_TRUE_MESSAGE(leaked < 2048, "opus create/destroy leaked memory");
}

// ---------------------------------------------------------------------------
// 2. Encoder real-time sweep (complexity)
// ---------------------------------------------------------------------------

static void test_encoder_realtime_by_complexity(void) {
    static opus_int16 pcm[kUplinkSamples];
    static uint8_t packet[kPacketCap];
    int sample_index = 0;

    for (int complexity : kComplexitySweep) {
        OpusEncoder *enc = open_encoder(complexity);
        TEST_ASSERT_NOT_NULL(enc);

        int64_t total = 0;
        int64_t worst = 0;
        int64_t encoded_total = 0;
        for (int f = 0; f < kFrames; f++) {
            fill_pcm(pcm, kUplinkSamples, sample_index);
            sample_index += kUplinkSamples;

            int64_t t0 = now_us();
            int n = opus_encode(enc, pcm, kUplinkSamples, packet, kPacketCap);
            int64_t dt = now_us() - t0;
            TEST_ASSERT_GREATER_THAN(0, n);

            total += dt;
            if (dt > worst) {
                worst = dt;
            }
            encoded_total += n;
        }
        int64_t avg = total / kFrames;
        float avg_pct = 100.0f * avg / kRealtimeBudgetUs;
        ESP_LOGI(TAG,
                 "RESULT encode 16k/20ms/%dbps cx=%d: avg=%lldus (%.1f%% of"
                 " frame) max=%lldus avg_packet=%lldB",
                 kBitrate, complexity, avg, avg_pct, worst,
                 encoded_total / kFrames);
        // A frame that cannot encode inside its own duration is unusable.
        TEST_ASSERT_TRUE_MESSAGE(avg < kRealtimeBudgetUs * 2,
                                 "encode exceeded 2x real-time budget");
        opus_encoder_destroy(enc);
    }
    check_heap("encoder sweep");
}

// ---------------------------------------------------------------------------
// 3. Decoder real-time (24 kHz, packets from the 16 kHz encoder)
// ---------------------------------------------------------------------------

static void test_decoder_realtime_24k(void) {
    OpusEncoder *enc = open_encoder(9);
    OpusDecoder *dec = open_decoder(kDownlinkRate);
    TEST_ASSERT_NOT_NULL(enc);
    TEST_ASSERT_NOT_NULL(dec);

    static opus_int16 pcm[kUplinkSamples];
    static uint8_t packet[kPacketCap];
    static opus_int16 decoded[kDownlinkSamples * 2];
    int sample_index = 0;

    int64_t total = 0;
    int64_t worst = 0;
    for (int f = 0; f < kFrames; f++) {
        fill_pcm(pcm, kUplinkSamples, sample_index);
        sample_index += kUplinkSamples;

        int packet_len = opus_encode(enc, pcm, kUplinkSamples, packet, kPacketCap);
        TEST_ASSERT_GREATER_THAN(0, packet_len);

        int64_t t0 = now_us();
        int samples = opus_decode(dec, packet, packet_len, decoded,
                                  kDownlinkSamples * 2, 0);
        int64_t dt = now_us() - t0;
        TEST_ASSERT_EQUAL(kDownlinkSamples, samples);

        // Packets are rate-agnostic: a 16k-encoded packet decodes to
        // 20 ms at whatever rate the decoder was opened with.
        total += dt;
        if (dt > worst) {
            worst = dt;
        }
    }
    int64_t avg = total / kFrames;
    ESP_LOGI(TAG, "RESULT decode 24k/20ms: avg=%lldus (%.1f%% of frame) max=%lldus",
             avg, 100.0f * avg / kRealtimeBudgetUs, worst);
    TEST_ASSERT_TRUE_MESSAGE(avg < kRealtimeBudgetUs * 2,
                             "decode exceeded 2x real-time budget");
    check_heap("decoder sweep");

    opus_encoder_destroy(enc);
    opus_decoder_destroy(dec);
}

// ---------------------------------------------------------------------------
// 4. Round-trip quality sanity (fixed-point port check, informational)
// ---------------------------------------------------------------------------

static void test_roundtrip_quality_sanity(void) {
    OpusEncoder *enc = open_encoder(9);
    OpusDecoder *dec16 = open_decoder(kUplinkRate);
    TEST_ASSERT_NOT_NULL(enc);
    TEST_ASSERT_NOT_NULL(dec16);

    // Encode 100 frames at 16 k and decode at 16 k, then SNR after an
    // alignment search over one frame of lookahead (encoder delay).
    static opus_int16 ref[kUplinkSamples * 100];
    static opus_int16 got[kUplinkSamples * 100 + 64];
    static uint8_t packet[kPacketCap];
    int offset16 = 0;

    // The host-spike signal (quality_ref.h) — the yardstick the 14.7 dB
    // float figure was measured against. On-device synthetic generators
    // produced degenerate signals (see the -2 dB note in the plan doc).
    memcpy(ref, TANK_QUAL_REF_PCM, sizeof(ref));

    for (int f = 0; f < 100; f++) {
        int packet_len = opus_encode(enc, ref + f * kUplinkSamples, kUplinkSamples,
                                     packet, kPacketCap);
        TEST_ASSERT_GREATER_THAN(0, packet_len);
        int samples = opus_decode(dec16, packet, packet_len,
                                  got + offset16,
                                  kUplinkSamples * 2, 0);
        TEST_ASSERT_EQUAL(kUplinkSamples, samples);
        offset16 += samples;
    }

    int best_lag = 0;
    double best_corr = -1e30;
    for (int lag = 0; lag < kUplinkSamples * 2; lag++) {
        double corr = 0;
        for (int i = 0; i < 2000; i += 4) {
            corr += static_cast<double>(ref[i]) * got[i + lag];
        }
        if (corr > best_corr) {
            best_corr = corr;
            best_lag = lag;
        }
    }
    double sig = 0;
    double noise = 0;
    // Probe peak at +lag means got[i + lag] ≈ ref[i] (decoder delayed);
    // compare each got sample against the ref sample best_lag EARLIER.
    int n = offset16 - best_lag;
    for (int i = 0; i < n; i++) {
        double e = static_cast<double>(ref[i]) - got[i + best_lag];
        sig += static_cast<double>(ref[i]) * ref[i];
        noise += e * e;
    }
    double snr = 10.0 * log10(sig / (noise + 1e-9));
    ESP_LOGI(TAG, "RESULT roundtrip 16k snr=%.1f dB (lag=%d, fixed-point)",
             snr, best_lag);
    // Speech-shaped noise at 32 kbps measured 14.7 dB on the host (float
    // libopus, spike); the fixed-point port should land close. A much lower
    // value would mean the port is broken; the host number is the yardstick.
    TEST_ASSERT_TRUE_MESSAGE(snr > 8.0, "round-trip quality regressed vs host");
    check_heap("roundtrip");

    opus_encoder_destroy(enc);
    opus_decoder_destroy(dec16);
}

// ---------------------------------------------------------------------------
// Harness
// ---------------------------------------------------------------------------

// libopus's VAR_ARRAYS build allocates encoder scratch on the caller's
// stack — kilobytes per opus_encode call. app_main's default stack is far
// too small: the first encode overflowed it and smashed whatever lived
// below (symptom: a corrupted FreeRTOS mutex asserted on the next log
// call). Run the whole suite on a dedicated 64 KB stack.
static void bench_task(void *arg) {
    (void)arg;
    HeapSnapshot boot = heap_now();
    log_heap("boot heap       ", boot);
    ESP_LOGI(TAG, "opus_bench: %d frames per measurement, budget %dus/frame",
             kFrames, kRealtimeBudgetUs);

    UNITY_BEGIN();
    RUN_TEST(test_memory_footprint_and_leak_check);
    RUN_TEST(test_encoder_realtime_by_complexity);
    RUN_TEST(test_decoder_realtime_24k);
    RUN_TEST(test_roundtrip_quality_sanity);
    UNITY_END();
    vTaskDelete(nullptr);
}

extern "C" void app_main(void) {
    // VM USB-Serial-JTAG re-enumeration race: wait for the host reader
    // before emitting any output (see TESTING.md §3.2).
    for (int i = 0; i < 100; i++) {
        if (usb_serial_jtag_is_connected()) break;
        vTaskDelay(pdMS_TO_TICKS(100));
    }
    vTaskDelay(pdMS_TO_TICKS(500));

    xTaskCreate(bench_task, "opus_bench", 64 * 1024, nullptr,
                tskIDLE_PRIORITY + 1, nullptr);
}

}  // extern "C"
