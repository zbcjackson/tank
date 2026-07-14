#include "Assistant.h"
#include "ui/Cores3Display.h"
#include "config.h"

#include "esp_log.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include "nvs_flash.h"
#include <cstring>
#if CONFIG_AEC_ENABLE
#include "audio/AecDiag.h"
#include <cmath>
#endif

static const char* TAG = "Assistant";

// Forward declare display factory
extern Display* createDisplay();

bool Assistant::init(BoardHAL* hal) {
    ESP_LOGI(TAG, "Initializing Tank Device Client");
    hal_ = hal;

    // Initialize NVS up front so we can read saved settings before WiFi init.
    // (WiFiManager::init also calls nvs_flash_init, but it is idempotent.)
    esp_err_t nvs_err = nvs_flash_init();
    if (nvs_err == ESP_ERR_NVS_NO_FREE_PAGES || nvs_err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }
    nvs_.init();

    // Session
    session_.init();
    session_.setState(Session::State::IDLE);

    // Display
    display_ = createDisplay();

    // Wire HAL and NVS to display if it's a Cores3Display
#ifdef TARGET_CORES3
    auto* cores3_disp = static_cast<Cores3Display*>(display_);
    cores3_disp->setHAL(hal_);
    cores3_disp->setNvsSettings(&nvs_);
    cores3_disp->setPlayback(&playback_);
#endif

    if (!display_->init()) {
        ESP_LOGE(TAG, "Display init failed");
        return false;
    }
    display_->showStatus("Initializing...");

    // Apply saved volume (software scaling in playback task)
    uint8_t vol = nvs_.getVolume();
    playback_.setVolume(vol);
    ESP_LOGI(TAG, "Volume set to %d%%", vol);

    // Create queues / stream buffers
    mic_queue_ = xQueueCreate(CONFIG_MIC_QUEUE_LEN, CONFIG_MIC_QUEUE_ITEM_BYTES);
    // Speaker stream: 512KB buffer holds ~16s of 16kHz mono 16-bit audio.
    // Allocated from PSRAM (CoreS3 has 8MB). Must be large enough to absorb
    // full TTS responses without blocking the WebSocket callback for too long.
    spk_stream_ = xStreamBufferCreateWithCaps(512 * 1024, CONFIG_SPK_FRAME_BYTES, MALLOC_CAP_SPIRAM);
    if (!spk_stream_) {
        // Fallback to internal RAM with smaller buffer if PSRAM unavailable
        ESP_LOGW(TAG, "PSRAM stream buffer failed, using 64KB internal");
        spk_stream_ = xStreamBufferCreate(64 * 1024, CONFIG_SPK_FRAME_BYTES);
    }
    event_queue_ = xQueueCreate(CONFIG_EVENT_QUEUE_LEN, sizeof(WsMessage));

    if (!mic_queue_ || !spk_stream_ || !event_queue_) {
        ESP_LOGE(TAG, "Failed to create queues/buffers");
        return false;
    }

#if CONFIG_AEC_ENABLE
    // Echo-cancelled mono audio: AFE fetch task → ws_send. Same 20ms frame size
    // as a single mic channel (AFE output is single-channel).
    clean_queue_ = xQueueCreate(CONFIG_MIC_QUEUE_LEN, CONFIG_MIC_FRAME_BYTES);
    if (!clean_queue_) {
        ESP_LOGE(TAG, "Failed to create clean audio queue");
        return false;
    }
#if !CONFIG_AEC_HW_REF
    // Software echo reference: playback writes each speaker frame here; the AFE
    // feed task pairs it with the mic. Hold ~200ms so a brief scheduling lag
    // between playback and feed doesn't starve the reference.
    ref_stream_ = xStreamBufferCreate(CONFIG_MIC_FRAME_BYTES * CONFIG_MIC_QUEUE_LEN,
                                      CONFIG_MIC_FRAME_BYTES);
    if (!ref_stream_) {
        ESP_LOGE(TAG, "Failed to create AEC reference stream");
        return false;
    }
    playback_.setRefStream(ref_stream_);
#endif
#endif

    // Resolve WiFi + backend config from NVS, falling back to compile-time defaults.
    char wifi_ssid[64] = {};
    char wifi_pass[64] = {};
    char backend_host[128] = {};

    if (!nvs_.getWifiSSID(wifi_ssid, sizeof(wifi_ssid))) {
        strncpy(wifi_ssid, CONFIG_WIFI_SSID, sizeof(wifi_ssid) - 1);
    }
    if (!nvs_.getWifiPassword(wifi_pass, sizeof(wifi_pass))) {
        strncpy(wifi_pass, CONFIG_WIFI_PASSWORD, sizeof(wifi_pass) - 1);
    }
    if (!nvs_.getBackendHost(backend_host, sizeof(backend_host))) {
        strncpy(backend_host, CONFIG_BACKEND_HOST, sizeof(backend_host) - 1);
    }
    int backend_port = nvs_.getBackendPort();
    ESP_LOGI(TAG, "WiFi SSID=%s, backend=%s:%d", wifi_ssid, backend_host, backend_port);

    // WebSocket client
    ws_.init(backend_host, backend_port, session_.getId());
    ws_.onAudio([this](const int16_t* pcm, size_t samples, uint32_t sr) {
        onWsAudio(pcm, samples, sr);
    });
    ws_.onMessage([this](const WsMessage& msg) {
        onWsMessage(msg);
    });
    ws_.onConnected([this]() { onWsConnected(); });
    ws_.onDisconnected([this]() { onWsDisconnected(); });

    // Audio
    if (!capture_.init(mic_queue_)) {
        ESP_LOGE(TAG, "Audio capture init failed");
        return false;
    }
    if (!playback_.init(spk_stream_, capture_.getTxChannel())) {
        ESP_LOGE(TAG, "Audio playback init failed");
        return false;
    }

    // Load the on-device speech front end. If it fails, log and continue — the
    // device still connects, it just won't wake on speech (the PTT button and
    // any other trigger still work).
#if CONFIG_AEC_ENABLE
    // Two AFE front-ends. SR (WakeNet + AEC) is created now — it's the default,
    // used for PTT/wake. VC (stronger AEC, no WakeNet) is created lazily on the
    // first call-mode entry (ensureVcAfe), NOT here: allocating it at boot
    // consumes enough internal DRAM that the subsequent esp_wifi_init() fails
    // with ESP_ERR_NO_MEM and aborts (boot loop). By first call, WiFi is already
    // up, so the allocation no longer contends with the WiFi driver's buffers.
    if (!afe_sr_.init(AfeProcessor::Type::SR)) {
        ESP_LOGE(TAG, "SR AFE init failed — wake word + AEC inactive");
    }
    active_afe_ = &afe_sr_;

    ESP_LOGI(TAG, "AFE init: SR=%s VC=deferred, free PSRAM=%u",
             afe_sr_.ready() ? "ok" : "FAIL",
             (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
#else
    if (!wake_word_.init()) {
        ESP_LOGE(TAG, "Wake word init failed — wake word inactive");
    }
#endif

    // WiFi callbacks — register BEFORE init so onConnected isn't missed if the
    // connection comes up quickly.
    wifi_.onConnected([this]() { onWiFiConnected(); });
    wifi_.onDisconnected([this]() { onWiFiDisconnected(); });

    if (!wifi_.init(wifi_ssid, wifi_pass)) {
        ESP_LOGE(TAG, "WiFi init failed");
        return false;
    }

    // Serial config handler
    serial_config_.init(&nvs_, &wifi_, &ws_);

    ESP_LOGI(TAG, "Initialization complete");
    display_->showStatus("Connecting WiFi...");
    session_.setState(Session::State::CONNECTING);
    return true;
}

void Assistant::start() {
    running_ = true;

    // Start audio tasks
    capture_.start();
    playback_.start();

#if CONFIG_AEC_ENABLE
    // AFE feed task on the audio core (near capture); fetch task on the net core
    // (it hands clean audio to ws_send and raises wake events).
    xTaskCreatePinnedToCore(
        afeFeedTask, "afe_feed",
        CONFIG_AUDIO_TASK_STACK, this,
        CONFIG_AUDIO_TASK_PRIORITY - 1, &afe_feed_task_,
        CONFIG_AUDIO_TASK_CORE
    );
    xTaskCreatePinnedToCore(
        afeFetchTask, "afe_fetch",
        CONFIG_NET_TASK_STACK, this,
        CONFIG_NET_TASK_PRIORITY, &afe_fetch_task_,
        CONFIG_NET_TASK_CORE
    );
#endif

    // Start WS send task
    xTaskCreatePinnedToCore(
        wsSendTask, "ws_send",
        CONFIG_NET_TASK_STACK, this,
        CONFIG_NET_TASK_PRIORITY, &ws_send_task_,
        CONFIG_NET_TASK_CORE
    );

    // Start UI task
    xTaskCreatePinnedToCore(
        uiTask, "ui",
        CONFIG_UI_TASK_STACK, this,
        CONFIG_UI_TASK_PRIORITY, &ui_task_,
        CONFIG_UI_TASK_CORE
    );

#if CONFIG_AEC_ENABLE && CONFIG_AEC_TEST_TONE
    // Boot self-test: play a 1kHz tone out the speaker for ~3s so the AEC path
    // has a known, room-coupled echo to cancel. A JTAG read of g_aec_diag during
    // this window shows ref_peak rising (MIC3 wired) and erle_db (echo removed).
    xTaskCreatePinnedToCore(
        testToneTask, "aec_tone",
        CONFIG_AUDIO_TASK_STACK, this,
        CONFIG_UI_TASK_PRIORITY, nullptr,
        CONFIG_AUDIO_TASK_CORE
    );
#endif

    // Start serial config listener
    serial_config_.start();

    ESP_LOGI(TAG, "All tasks started");
}

void Assistant::stop() {
    running_ = false;
    capture_.stop();
    playback_.stop();
    ws_.disconnect();
    wifi_.disconnect();
}

// ─── Callbacks ──────────────────────────────────────────────────────────────

void Assistant::onWiFiConnected() {
    ESP_LOGI(TAG, "WiFi connected, starting WebSocket");
    display_->showStatus("Connecting to Tank...");
    ws_.connect();
}

void Assistant::onWiFiDisconnected() {
    ESP_LOGW(TAG, "WiFi disconnected");
    session_.setState(Session::State::CONNECTING);
    display_->showStatus("WiFi lost, reconnecting...");
}

void Assistant::onWsConnected() {
    // Fired on initial connect and on every automatic reconnect (backend
    // restart, transient network drop). The esp_websocket_client library
    // handles the reconnect loop; we just resync UI/session state here.
    // The backend sends a "ready" signal after the pipeline is built,
    // which drives the READY transition. Pipeline init takes 2-4s on
    // first connect (ASR/TTS/MCP loading); reattach to an existing
    // session is instant.
    ESP_LOGI(TAG, "WebSocket connected, awaiting pipeline ready");
    session_.setState(Session::State::CONNECTING);
    display_->showStatus("Loading...");
}

void Assistant::onWsDisconnected() {
    // Backend restarted or the link dropped. The library will keep retrying
    // (reconnect_timeout_ms). Reset transient turn state so a stale utterance
    // doesn't finalize against the new connection, and stop any playback.
    ESP_LOGW(TAG, "WebSocket disconnected, awaiting reconnect");
    talking_ = false;
    eou_pending_ = false;
    drain_frames_ = 0;
    wake_turn_ = false;
    call_mode_ = false;
#if CONFIG_AEC_ENABLE
    // Return to the SR front-end so wake word works after reconnect.
    active_afe_ = &afe_sr_;
#endif
    playback_.flush();
    session_.setState(Session::State::CONNECTING);
    display_->showStatus("Reconnecting to Tank...");
}

void Assistant::onWsAudio(const int16_t* pcm, size_t samples, uint32_t sample_rate) {
    if (!spk_stream_) return;

    size_t bytes = samples * sizeof(int16_t);
    // Block until space is available. The playback task drains at 32KB/s, so
    // even a full 512KB buffer clears in ~16s. Using portMAX_DELAY ensures no
    // frames are ever dropped — the WebSocket callback just waits, creating
    // natural backpressure. This eliminates the blast noise on long responses.
    xStreamBufferSend(spk_stream_, pcm, bytes, portMAX_DELAY);

    if (session_.getState() != Session::State::SPEAKING) {
        session_.setState(Session::State::SPEAKING);
    }
}

void Assistant::onWsMessage(const WsMessage& msg) {
    // Route message to UI task via event queue
    xQueueSend(event_queue_, &msg, 0);

    // Handle state transitions
    if (strcmp(msg.type, "signal") == 0) {
        if (strcmp(msg.content, "ready") == 0 ||
            strcmp(msg.content, "conversation_ready") == 0 ||
            strcmp(msg.content, "conversation_created") == 0) {
            session_.setState(Session::State::READY);
        } else if (strcmp(msg.content, "processing_started") == 0) {
            session_.setState(Session::State::PROCESSING);
        } else if (strcmp(msg.content, "processing_ended") == 0) {
            session_.setState(Session::State::READY);
        }
    }
}

// ─── Tasks ──────────────────────────────────────────────────────────────────

#if CONFIG_AEC_ENABLE
// Lazily create the VC (Voice Communication) AFE on the first call-mode entry.
// Deferred from boot on purpose: allocating VC's internal-DRAM buffers before
// esp_wifi_init() runs starved the WiFi driver of RX buffers → ESP_ERR_NO_MEM →
// abort → boot loop. By the first call, WiFi is already initialized, so the
// allocation no longer contends with it.
//
// One-shot: afe_vc_attempted_ guards against retrying a known-failed alloc on
// every call entry. Once created, VC is kept resident and reused by later calls.
// Runs on the UI task (core 1); the caller flips active_afe_ only after this
// returns, so the feed/fetch tasks never see a half-built VC.
void Assistant::ensureVcAfe() {
    if (afe_vc_attempted_) {
        return;
    }
    afe_vc_attempted_ = true;
    afe_vc_ready_ = afe_vc_.init(AfeProcessor::Type::VC);
    if (afe_vc_ready_) {
        ESP_LOGI(TAG, "VC AFE created (lazy), free PSRAM=%u",
                 (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
    } else {
        ESP_LOGW(TAG, "VC AFE init failed — call mode falls back to SR + mute");
    }
}

// Builds the interleaved [mic, ref] stream the AFE expects and feeds it in
// AFE-sized chunks. The mic frame comes from the capture queue every 20ms; the
// reference comes from one of two sources depending on build config:
//   - HW ref: capture already interleaved [mic, ref] from the TDM MIC3 slot.
//   - SW ref (default): pair the mono mic frame with the matching playback frame
//     drained from ref_stream_; substitute silence when nothing is playing
//     (silence is the correct "speaker quiet" reference).
void Assistant::afeFeedTask(void* arg) {
    auto* self = static_cast<Assistant*>(arg);

    if (!self->afe_sr_.ready()) {
        ESP_LOGE(TAG, "AFE not ready — feed task exiting");
        vTaskDelete(nullptr);
        return;
    }

    constexpr size_t CAP_SAMPLES = CONFIG_MIC_SAMPLE_RATE * CONFIG_MIC_FRAME_MS / 1000;
    constexpr size_t CH = CONFIG_AFE_TOTAL_CH;

    // Frame buffers live on the heap, not the task stack — together they exceed
    // the 4KB audio-task stack and would overflow it (caught as a stack-overflow
    // panic in afeFeedTask otherwise).
    // feed_buf is sized to the LARGER of the two AFEs' chunk sizes so switching
    // active_afe_ mid-stream can never overflow it. The active chunk total is
    // re-read every loop (cheap) so the flush boundary matches the live AFE.
    int feed_cap = self->afe_sr_.feedChunkTotal();
    if (self->afe_vc_ready_ && self->afe_vc_.feedChunkTotal() > feed_cap) {
        feed_cap = self->afe_vc_.feedChunkTotal();
    }
    auto* interleaved = static_cast<int16_t*>(malloc(CAP_SAMPLES * CH * sizeof(int16_t)));
    auto* feed_buf = static_cast<int16_t*>(malloc(feed_cap * sizeof(int16_t)));
#if CONFIG_AEC_HW_REF
    auto* cap_frame = static_cast<int16_t*>(malloc(CAP_SAMPLES * CH * sizeof(int16_t)));
    if (!interleaved || !feed_buf || !cap_frame) {
#else
    auto* mic_frame = static_cast<int16_t*>(malloc(CAP_SAMPLES * sizeof(int16_t)));
    auto* ref_frame = static_cast<int16_t*>(malloc(CAP_SAMPLES * sizeof(int16_t)));
    if (!interleaved || !feed_buf || !mic_frame || !ref_frame) {
#endif
        ESP_LOGE(TAG, "AFE feed buffer alloc failed");
        vTaskDelete(nullptr);
        return;
    }
    size_t fill = 0;
    AfeProcessor* fed_afe = self->active_afe_;  // AFE the accumulator is filling for

    ESP_LOGI(TAG, "AFE feed task started (frame=%d, feed_cap=%d, %s ref)",
             (int)(CAP_SAMPLES * CH), feed_cap,
             CONFIG_AEC_HW_REF ? "HW" : "SW");

    while (self->running_) {
#if CONFIG_AEC_HW_REF
        if (xQueueReceive(self->mic_queue_, cap_frame, pdMS_TO_TICKS(100)) != pdTRUE) {
            continue;
        }
        memcpy(interleaved, cap_frame, CAP_SAMPLES * CH * sizeof(int16_t));
#else
        if (xQueueReceive(self->mic_queue_, mic_frame, pdMS_TO_TICKS(100)) != pdTRUE) {
            continue;
        }
        // Pull the matching playback reference. If less than a full frame is
        // available (speaker idle or mid-gap), pad the remainder with silence.
        size_t got = 0;
        if (self->ref_stream_) {
            got = xStreamBufferReceive(self->ref_stream_, ref_frame,
                                       CAP_SAMPLES * sizeof(int16_t), 0);
        }
        size_t got_samples = got / sizeof(int16_t);
        if (got_samples < CAP_SAMPLES) {
            memset(ref_frame + got_samples, 0,
                   (CAP_SAMPLES - got_samples) * sizeof(int16_t));
        }
        // Interleave: [mic0, ref0, mic1, ref1, ...] (mic first, reference last).
        for (size_t i = 0; i < CAP_SAMPLES; i++) {
            interleaved[i * CH + 0] = mic_frame[i];
            interleaved[i * CH + 1] = ref_frame[i];
        }
#endif

#if CONFIG_AEC_DIAG
        // Sample raw mic/ref power so a JTAG read of g_aec_diag shows whether the
        // reference carries the speaker signal and how much echo AEC removes.
        aecDiagInput(interleaved, CAP_SAMPLES, CH, 0, 1);
#endif

        // Snapshot the active AFE for this iteration. If it changed since we
        // started accumulating a chunk, drop the partial chunk — feeding SR-era
        // samples into VC (or vice-versa) would desync the pipeline. Also re-read
        // the flush boundary from the live AFE (VC and SR may differ).
        AfeProcessor* afe = self->active_afe_;
        if (afe != fed_afe) {
            fill = 0;
            fed_afe = afe;
            // VC is created lazily (after this task started), so it may not have
            // been accounted for when feed_buf was sized. If the now-active AFE
            // needs a larger chunk than the buffer holds, grow it. Rare (only on
            // call enter/exit), so the realloc cost is irrelevant.
            const int need = afe->feedChunkTotal();
            if (need > feed_cap) {
                auto* grown = static_cast<int16_t*>(
                    realloc(feed_buf, (size_t)need * sizeof(int16_t)));
                if (grown) {
                    feed_buf = grown;
                    feed_cap = need;
                } else {
                    ESP_LOGE(TAG, "feed_buf regrow failed (%d→%d) — keeping SR",
                             feed_cap, need);
                    // Can't safely feed the larger AFE; stay on SR this iteration.
                    afe = &self->afe_sr_;
                    fed_afe = afe;
                }
            }
        }
        const size_t feed_total = (size_t)afe->feedChunkTotal();

        // Append to the feed buffer, flushing a full chunk whenever it fills.
        size_t src = 0;
        const size_t avail = CAP_SAMPLES * CH;
        while (src < avail) {
            size_t take = feed_total - fill;
            if (take > avail - src) take = avail - src;
            memcpy(feed_buf + fill, interleaved + src, take * sizeof(int16_t));
            fill += take;
            src += take;
            if (fill == feed_total) {
                afe->feed(feed_buf);
                fill = 0;
            }
        }
    }

    free(feed_buf);
    free(interleaved);
#if CONFIG_AEC_HW_REF
    free(cap_frame);
#else
    free(mic_frame);
    free(ref_frame);
#endif
    ESP_LOGI(TAG, "AFE feed task stopped");
    vTaskDelete(nullptr);
}

// Blocks on AFE fetch, dispatching echo-cancelled audio to the clean queue and
// raising a wake event when WakeNet fires. With AEC the reference is subtracted
// before WakeNet, so detection works during playback — no echo hangover needed.
void Assistant::afeFetchTask(void* arg) {
    auto* self = static_cast<Assistant*>(arg);

    if (!self->afe_sr_.ready()) {
        ESP_LOGE(TAG, "AFE not ready — fetch task exiting");
        vTaskDelete(nullptr);
        return;
    }

    constexpr size_t FRAME_SAMPLES = CONFIG_MIC_SAMPLE_RATE * CONFIG_MIC_FRAME_MS / 1000;
    int16_t out_frame[FRAME_SAMPLES];
    size_t out_fill = 0;

    ESP_LOGI(TAG, "AFE fetch task started");

    while (self->running_) {
        AfeProcessor::FetchResult r = self->active_afe_->fetch();
        if (!r.valid) {
            vTaskDelay(1);
            continue;
        }

        // Diagnostics: sample post-AEC output power for ERLE measurement.
        aecDiagOutput(r.data, r.samples);

        if (r.wake_detected && !self->talking_) {
            // Raise the wake edge for wsSendTask to open the turn. Don't touch
            // session/WS state from here — keep all turn control in one task.
            self->wake_pending_ = true;
        }

        // Re-chunk the AFE output (its fetch chunk may differ from 20ms) into
        // 320-sample frames for the clean queue.
        int consumed = 0;
        while (consumed < r.samples) {
            size_t take = FRAME_SAMPLES - out_fill;
            if (take > (size_t)(r.samples - consumed)) take = r.samples - consumed;
            memcpy(out_frame + out_fill, r.data + consumed, take * sizeof(int16_t));
            out_fill += take;
            consumed += take;
            if (out_fill == FRAME_SAMPLES) {
                // Only queue while a turn is active; otherwise drop (the clean
                // stream is continuous but we only uplink during talking_).
                if (self->talking_) {
                    xQueueSend(self->clean_queue_, out_frame, 0);
                }
                out_fill = 0;
            }
        }
    }

    ESP_LOGI(TAG, "AFE fetch task stopped");
    vTaskDelete(nullptr);
}

#if CONFIG_AEC_TEST_TONE
// Boot self-test: generate a 1kHz sine tone at ~50% amplitude for 3 seconds,
// push it through the speaker stream. This gives the AEC a known echo to cancel
// while the mic is picking it up — halt over JTAG and read g_aec_diag.
void Assistant::testToneTask(void* arg) {
    auto* self = static_cast<Assistant*>(arg);

    // Wait briefly for the AFE pipeline to spin up (needs a few feed cycles to
    // initialize its filter coefficients).
    vTaskDelay(pdMS_TO_TICKS(500));

    g_aec_diag.tone_playing = true;
    ESP_LOGI(TAG, "AEC test tone: playing 1kHz for 3s");

    constexpr int SAMPLE_RATE = CONFIG_SPK_SAMPLE_RATE;
    constexpr int TONE_HZ = 1000;
    constexpr int DURATION_MS = 6000;
    constexpr int FRAME_MS = CONFIG_SPK_FRAME_MS;
    constexpr int FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS / 1000;
    constexpr int TOTAL_FRAMES = DURATION_MS / FRAME_MS;
    constexpr int16_t AMPLITUDE = 16000;  // ~50% of full scale

    int16_t frame[FRAME_SAMPLES];
    int sample_idx = 0;
    const float w = 2.0f * (float)M_PI * TONE_HZ / SAMPLE_RATE;

    for (int f = 0; f < TOTAL_FRAMES; f++) {
        for (int i = 0; i < FRAME_SAMPLES; i++) {
            frame[i] = (int16_t)(AMPLITUDE * sinf(w * sample_idx));
            sample_idx++;
        }
        // Push into the speaker stream buffer — AudioPlayback reads from here.
        xStreamBufferSend(self->spk_stream_, frame,
                          FRAME_SAMPLES * sizeof(int16_t), pdMS_TO_TICKS(50));
    }

    g_aec_diag.tone_playing = false;
    ESP_LOGI(TAG, "AEC test tone: done. Read g_aec_diag over JTAG.");
    vTaskDelete(nullptr);
}
#endif

// AEC build: mic uplink comes from the echo-cancelled clean_queue_; wake events
// come from afeFetchTask via wake_pending_. No inline WakeNet, no echo hangover.
void Assistant::wsSendTask(void* arg) {
    auto* self = static_cast<Assistant*>(arg);

    constexpr size_t SAMPLES = CONFIG_MIC_SAMPLE_RATE * CONFIG_MIC_FRAME_MS / 1000;
    int16_t frame[SAMPLES];

    SilenceDetector silence({
        CONFIG_WAKE_SPEECH_RMS,
        CONFIG_WAKE_SILENCE_FRAMES,
        CONFIG_WAKE_MIN_SPEECH_FRAMES,
        CONFIG_WAKE_MAX_FRAMES,
    });
    bool was_playing = false;
    // Call-mode playback mute hangover (frames). The software-reference AEC
    // (~17 dB) can't fully cancel echo, so in call mode we drop the uplink while
    // the assistant plays. Two effects require a hangover rather than a bare
    // isPlaying() check:
    //   1. playing_ briefly drops to false in the network gaps BETWEEN TTS
    //      chunks — a bare check unmutes mid-response and leaks echo.
    //   2. AFE latency: frames pulled from clean_queue_ were captured ~100-200ms
    //      earlier, so the echo tail keeps arriving after playing_ goes false.
    // Holding the mute for ~600ms past the last "playing" frame covers both.
    constexpr int MUTE_HANGOVER_FRAMES = 30;  // 30 × 20ms = 600ms
    int mute_hangover = 0;

    ESP_LOGI(TAG, "WS send task started (AEC)");

    while (self->running_) {
        // Open a wake turn on the edge raised by afeFetchTask. AEC removes the
        // speaker echo, so this is safe to fire even during playback (barge-in).
        if (self->wake_pending_) {
            self->wake_pending_ = false;
            if (self->ws_.isConnected() && !self->talking_) {
                ESP_LOGI(TAG, "Wake word detected (AFE)");
                self->ws_.sendInterrupt();
                self->playback_.flush();
                self->ws_.sendJson("signal", "wake");
                silence.reset();
                xQueueReset(self->clean_queue_);
                self->talking_ = true;
                self->wake_turn_ = true;
                self->session_.setState(Session::State::LISTENING);
                self->display_->showTalkState(true);
                self->display_->showStatus("Listening...");
                self->display_->showAssistantText("");
            }
        }

        if (xQueueReceive(self->clean_queue_, frame, pdMS_TO_TICKS(100)) == pdTRUE) {
            if (self->talking_) {
                // Call mode with the VC front-end active: its stronger AEC cancels
                // the echo, so stream continuously through playback → full-duplex
                // barge-in (the user can talk over the assistant).
                //
                // Fallback path (VC init failed → still on the SR front-end): the
                // SR AEC (~17 dB ERLE) can't fully cancel echo, so mute the uplink
                // while the assistant plays. A hangover covers two effects that a
                // bare isPlaying() check misses:
                //   1. playing_ briefly drops false in gaps BETWEEN TTS chunks.
                //   2. AFE latency: frames from clean_queue_ were captured
                //      ~100-200ms earlier, so the echo tail arrives late.
                const bool vc_active = (self->active_afe_ == &self->afe_vc_);
                if (self->call_mode_ && !vc_active) {
                    if (self->playback_.isPlaying()) {
                        mute_hangover = MUTE_HANGOVER_FRAMES;
                    } else if (mute_hangover > 0) {
                        mute_hangover--;
                    }
                } else {
                    mute_hangover = 0;
                }
                const bool mute_for_playback =
                    self->call_mode_ && !vc_active && mute_hangover > 0;
                if (self->ws_.isConnected() && !mute_for_playback) {
                    self->ws_.sendAudio(frame, SAMPLES);
                }
                // In call mode: no device-side silence detection or EOU — the
                // backend's VAD handles endpointing.
                // Wake/PTT turns: end on trailing silence or button release.
                if (!self->call_mode_ && self->wake_turn_ && silence.update(frame, SAMPLES)) {
                    self->talking_ = false;
                    self->wake_turn_ = false;
                    if (self->ws_.isConnected()) {
                        self->ws_.sendEndOfUtterance();
                    }
                    ESP_LOGI(TAG, "EOU sent (%s)",
                             silence.endedByCap() ? "max-listen cap" : "silence");
                    self->session_.setState(Session::State::PROCESSING);
                    self->display_->showTalkState(false);
                    self->display_->showStatus("Processing...");
                }
            } else if (self->eou_pending_ && self->drain_frames_ > 0) {
                // Drain the PTT tail still in flight through the AFE pipeline.
                if (self->ws_.isConnected()) {
                    self->ws_.sendAudio(frame, SAMPLES);
                }
                self->drain_frames_--;
                if (self->drain_frames_ == 0) {
                    self->eou_pending_ = false;
                    if (self->ws_.isConnected()) {
                        self->ws_.sendEndOfUtterance();
                        ESP_LOGI(TAG, "EOU sent (drain complete)");
                    }
                }
            }
        } else if (self->eou_pending_) {
            // Clean queue drained before the counter hit zero — finalize now.
            self->eou_pending_ = false;
            self->drain_frames_ = 0;
            if (self->ws_.isConnected()) {
                self->ws_.sendEndOfUtterance();
                ESP_LOGI(TAG, "EOU sent (queue empty)");
            }
        }

        // Reset the display to "Ready" once the assistant's playback finishes.
        // In call mode, talking_ stays true so this edge never fires — the
        // session cycles between LISTENING/PROCESSING/SPEAKING driven by server
        // signals and onWsAudio. After playback ends in call mode, revert to
        // LISTENING (the mic is still streaming).
        const bool playing_now = self->playback_.isPlaying();
        if (playing_now) {
            was_playing = true;
        } else if (was_playing && !self->talking_) {
            was_playing = false;
            self->session_.setState(Session::State::READY);
            self->display_->showStatus("Ready");
            self->display_->showThinking(false);
        } else if (was_playing && self->call_mode_) {
            was_playing = false;
            self->session_.setState(Session::State::LISTENING);
        }
    }

    ESP_LOGI(TAG, "WS send task stopped");
    vTaskDelete(nullptr);
}

#else  // !CONFIG_AEC_ENABLE — original inline-WakeNet + echo-hangover path

void Assistant::wsSendTask(void* arg) {
    auto* self = static_cast<Assistant*>(arg);

    constexpr size_t SAMPLES = CONFIG_MIC_SAMPLE_RATE * CONFIG_MIC_FRAME_MS / 1000;
    int16_t frame[SAMPLES];

    SilenceDetector silence({
        CONFIG_WAKE_SPEECH_RMS,
        CONFIG_WAKE_SILENCE_FRAMES,
        CONFIG_WAKE_MIN_SPEECH_FRAMES,
        CONFIG_WAKE_MAX_FRAMES,
    });
    // Timestamp (µs) of the last frame during which playback was active. Used
    // to hold off wake detection through the echo hangover window.
    int64_t last_playing_us = 0;
    // Track playback→idle edge to reset display to "Ready" once.
    bool was_playing = false;

    ESP_LOGI(TAG, "WS send task started");

    while (self->running_) {
        if (xQueueReceive(self->mic_queue_, frame, pdMS_TO_TICKS(100)) == pdTRUE) {
            if (self->talking_) {
                if (self->wake_turn_ && self->playback_.isPlaying()) {
                    // The assistant's response has started playing before our
                    // SilenceDetector closed the turn (the backend endpointed on
                    // its own VAD). This board has no AEC, so continuing to stream
                    // would send the speaker echo back to the backend, and the
                    // loud echo would stop SilenceDetector from ever seeing
                    // silence — hanging the turn until the 15s cap. Close the
                    // wake turn and stop streaming; onWsAudio already moved the
                    // session to SPEAKING, and the idle branch resets to Ready
                    // once playback ends.
                    self->talking_ = false;
                    self->wake_turn_ = false;
                    if (self->ws_.isConnected()) {
                        self->ws_.sendEndOfUtterance();
                    }
                    ESP_LOGI(TAG, "EOU sent (assistant responding)");
                    self->display_->showTalkState(false);
                } else {
                    // Streaming the utterance (started by PTT press or wake word).
                    if (self->ws_.isConnected()) {
                        self->ws_.sendAudio(frame, SAMPLES);
                    }
                    // Only wake-initiated turns end on trailing silence. PTT turns
                    // end on button release (uiTask), so skip silence for them.
                    if (self->wake_turn_ && silence.update(frame, SAMPLES)) {
                        self->talking_ = false;
                        self->wake_turn_ = false;
                        if (self->ws_.isConnected()) {
                            self->ws_.sendEndOfUtterance();
                        }
                        ESP_LOGI(TAG, "EOU sent (%s)",
                                 silence.endedByCap() ? "max-listen cap" : "silence");
                        self->session_.setState(Session::State::PROCESSING);
                        self->display_->showTalkState(false);
                        self->display_->showStatus("Processing...");
                    }
                }
            }
            else if (self->eou_pending_ && self->drain_frames_ > 0) {
                // Draining the tail of PTT speech (queued + DMA pipeline frames).
                if (self->ws_.isConnected()) {
                    self->ws_.sendAudio(frame, SAMPLES);
                }
                self->drain_frames_--;
                if (self->drain_frames_ == 0) {
                    // All speech frames sent — finalize the utterance.
                    self->eou_pending_ = false;
                    if (self->ws_.isConnected()) {
                        self->ws_.sendEndOfUtterance();
                        ESP_LOGI(TAG, "EOU sent (drain complete)");
                    }
                }
            }
            else if (!self->ws_.isConnected()) {
                // Not connected yet: skip WakeNet entirely. There is nowhere to
                // send the `wake` signal, and running inference on Core 1 here
                // starves WiFi/DHCP and the WS handshake during connection —
                // which left the UI stuck on "Connecting WiFi". Drop buffered
                // audio; the loop-end delay yields the core.
                self->wake_word_.reset();
            } else {
                // Idle and connected. Suppress wake detection while the speaker
                // is active, through the fixed hangover window, AND until the
                // mic level drops below the speech threshold — so residual echo
                // from the assistant's response can't self-trigger WakeNet.
                const int64_t now_us = esp_timer_get_time();
                const bool playing_now = self->playback_.isPlaying();
                if (playing_now) {
                    last_playing_us = now_us;
                    was_playing = true;
                }
                const bool in_hangover =
                    (now_us - last_playing_us) <
                    ((int64_t)CONFIG_WAKE_ECHO_HANGOVER_MS * 1000);

                // Compute frame energy to gate detection on actual silence.
                // Reuse SilenceDetector's static RMS method isn't accessible,
                // so inline a quick energy check against the speech threshold.
                int32_t energy = 0;
                for (size_t i = 0; i < SAMPLES; i++) {
                    int32_t s = frame[i];
                    energy += (s * s) >> 16;
                }
                const bool frame_is_loud =
                    (energy / (int32_t)SAMPLES) >
                    ((int32_t)CONFIG_WAKE_SPEECH_RMS * CONFIG_WAKE_SPEECH_RMS >> 16);

                // Suppress if: still in hangover, OR the hangover just ended but
                // the mic is still loud (echo tail reverberating in the room).
                const bool suppress = in_hangover ||
                    (last_playing_us > 0 && frame_is_loud);

                // Response finished: playback stopped, hangover passed, room
                // quiet. Reset the display to "Ready" once (the backend sends no
                // end-of-audio signal, so the device closes the turn itself).
                if (was_playing && !playing_now && !suppress) {
                    was_playing = false;
                    self->session_.setState(Session::State::READY);
                    self->display_->showStatus("Ready");
                    self->display_->showThinking(false);
                }

                if (suppress) {
                    self->wake_word_.reset();
                } else {
                    if (self->wake_word_.feed(frame, SAMPLES)) {
                        ESP_LOGI(TAG, "Wake word detected");
                        self->ws_.sendInterrupt();
                        self->playback_.flush();
                        self->ws_.sendJson("signal", "wake");
                        silence.reset();
                        self->talking_ = true;
                        self->wake_turn_ = true;
                        self->session_.setState(Session::State::LISTENING);
                        self->display_->showTalkState(true);
                        self->display_->showStatus("Listening...");
                        self->display_->showAssistantText("");
                    }
                }
            }
        } else {
            // Queue timeout — if a PTT turn is still draining, all frames have
            // been consumed. Send EOU now (handles the case where the queue
            // empties before drain_frames_ reaches zero, e.g. a mostly-empty DMA).
            if (self->eou_pending_) {
                self->eou_pending_ = false;
                self->drain_frames_ = 0;
                if (self->ws_.isConnected()) {
                    self->ws_.sendEndOfUtterance();
                    ESP_LOGI(TAG, "EOU sent (queue empty)");
                }
            }
        }

        // WakeNet inference runs inline in this task (priority 18, Core 1). The
        // mic queue is almost always non-empty, so xQueueReceive rarely blocks —
        // without an explicit yield this task starves the lower-priority UI task
        // and the event loop that processes the WiFi "connected" callback on the
        // same core, freezing the UI on "Connecting WiFi". A 1-tick yield frees
        // Core 1 while frames buffer in the queue.
        vTaskDelay(1);
    }

    ESP_LOGI(TAG, "WS send task stopped");
    vTaskDelete(nullptr);
}

#endif  // CONFIG_AEC_ENABLE

void Assistant::uiTask(void* arg) {
    auto* self = static_cast<Assistant*>(arg);

    WsMessage msg;
    bool was_pressed = false;
    ESP_LOGI(TAG, "UI task started");

    while (self->running_) {
        // ─── Call mode handling ─────────────────────────────────────────────
        // Enter call mode: LVGL timer detected the call button tap and set the
        // flag. We handle the audio/session logic here in the uiTask.
        if (self->display_->consumeCallModeRequest() && self->ws_.isConnected()) {
            ESP_LOGI(TAG, "Call mode entered");
            self->ws_.sendInterrupt();
            self->playback_.flush();
            if (self->eou_pending_) {
                self->eou_pending_ = false;
                self->drain_frames_ = 0;
                if (self->ws_.isConnected()) {
                    self->ws_.sendEndOfUtterance();
                }
            }
            self->ws_.sendJson("signal", "wake");
#if CONFIG_AEC_ENABLE
            // Create the VC front-end on first use (deferred from boot to keep
            // WiFi init from OOMing), then switch to it for stronger AEC →
            // full-duplex barge-in. The feed/fetch tasks pick up the new
            // active_afe_ on their next iteration; the clean-queue reset below
            // drops any SR-era frames still in flight. If VC is unavailable
            // (init failed), stay on SR — the send task mutes the uplink during
            // playback as a fallback.
            self->ensureVcAfe();
            if (self->afe_vc_ready_) {
                self->active_afe_ = &self->afe_vc_;
            }
            xQueueReset(self->clean_queue_);
#else
            xQueueReset(self->mic_queue_);
#endif
            self->call_mode_ = true;
            self->talking_ = true;
            self->wake_turn_ = false;
            self->session_.setState(Session::State::LISTENING);
        }

        // Exit call mode: hang-up button tapped.
        if (self->display_->consumeHangupRequest()) {
            ESP_LOGI(TAG, "Call mode exited (hang up)");
            // Clear call state FIRST so the send task stops streaming and no
            // more audio reaches the backend.
            self->call_mode_ = false;
            self->talking_ = false;
            self->eou_pending_ = false;
            self->drain_frames_ = 0;
            self->wake_turn_ = false;
            // Send interrupt (NOT end_of_utterance) to cancel any in-flight
            // processing. end_of_utterance would force-finalize the pending
            // speech and the backend would generate a response that lands back
            // on the main screen after hang-up. interrupt cancels it outright.
            if (self->ws_.isConnected()) {
                self->ws_.sendInterrupt();
            }
            self->playback_.flush();
#if CONFIG_AEC_ENABLE
            // Switch back to the SR front-end (WakeNet) for PTT/wake. The
            // feed/fetch tasks pick this up next iteration; drop any VC-era frames.
            self->active_afe_ = &self->afe_sr_;
            xQueueReset(self->clean_queue_);
#endif
            self->session_.setState(Session::State::READY);
            self->display_->showStatus("Ready");
        }

        // ─── PTT handling (skipped in call mode) ────────────────────────────
        // Poll PTT button (LVGL event-driven via pollPressed)
        bool pressed = self->call_mode_ ? false : self->display_->pollPressed();
        // Ignore presses while audio is playing. The FT6336U touch controller
        // reports phantom touches during playback (speaker amp coupling on the
        // shared board), which would start a spurious PTT session and stream the
        // speaker echo back to the backend. The user doesn't press the button to
        // talk over the response, so gating on playback is safe. (Wake word can
        // still barge in during playback — it has its own echo suppression.)
        if (self->playback_.isPlaying()) {
            pressed = false;
        }
        if (pressed && !was_pressed) {
            ESP_LOGI(TAG, "PTT pressed — start streaming");
            self->ws_.sendInterrupt();
            self->playback_.flush();
            // If the previous turn's EOU hasn't been sent yet, force it now.
            if (self->eou_pending_) {
                self->eou_pending_ = false;
                self->drain_frames_ = 0;
                if (self->ws_.isConnected()) {
                    self->ws_.sendEndOfUtterance();
                }
            }
            // No discard window — capture runs continuously so the DMA always
            // holds fresh audio (ambient/silence), not stale speech from a
            // previous turn. Discarding would clip the start of the user's speech.
#if CONFIG_AEC_ENABLE
            // The uplink reads from the echo-cancelled clean queue; reset that.
            // Leave mic_queue_/AFE pipeline running so the AEC filter stays
            // converged (a reset would drop its adaptation state).
            xQueueReset(self->clean_queue_);
#else
            xQueueReset(self->mic_queue_);
#endif
            self->talking_ = true;
            // A button-initiated turn ends on release, not trailing silence —
            // even if a wake-word turn was already active when the user pressed.
            self->wake_turn_ = false;
            self->session_.setState(Session::State::LISTENING);
            self->display_->showTalkState(true);
            self->display_->showStatus("Listening...");
            // Clear stale text from last turn so it doesn't flash at start.
            self->display_->showAssistantText("");
        } else if (!pressed && was_pressed) {
            // Drain the I2S DMA pipeline latency only — the ~120ms of audio
            // captured BEFORE release but not yet read from the DMA ring buffer.
            // 8 frames = 160ms covers that without capturing speech the user
            // says AFTER releasing (which would bleed into the next turn).
            self->drain_frames_ = 8;
            self->talking_ = false;
            self->eou_pending_ = true;
            self->display_->showTalkState(false);
            self->display_->showStatus("Processing...");
            self->session_.setState(Session::State::PROCESSING);
        }
        was_pressed = pressed;

        // New-conversation button: tell the backend to start a fresh
        // conversation (empty history). Stop any current response first and
        // clear transient turn state so nothing leaks into the new session.
        if (!self->call_mode_ && self->display_->consumeNewConversationRequest() && self->ws_.isConnected()) {
            ESP_LOGI(TAG, "New conversation requested");
            // Stop any current response and clear transient turn state so nothing
            // leaks into the fresh conversation.
            self->ws_.sendInterrupt();
            self->playback_.flush();
            self->talking_ = false;
            self->eou_pending_ = false;
            self->drain_frames_ = 0;
            self->wake_turn_ = false;
            self->ws_.sendJson("signal", "new_conversation");
            // Status feedback; the backend's conversation_created reply flips it
            // back to "Ready". (Transcript text isn't rendered on this display.)
            self->display_->showStatus("New conversation");
        }

        if (xQueueReceive(self->event_queue_, &msg, pdMS_TO_TICKS(20)) == pdTRUE) {
            if (strcmp(msg.type, "signal") == 0) {
                if (strcmp(msg.content, "ready") == 0 ||
                    strcmp(msg.content, "conversation_ready") == 0 ||
                    strcmp(msg.content, "conversation_created") == 0) {
                    self->display_->showStatus("Ready");
                } else if (strcmp(msg.content, "processing_started") == 0) {
                    self->display_->showThinking(true);
                } else if (strcmp(msg.content, "processing_ended") == 0) {
                    self->display_->showThinking(false);
                }
            } else if (strcmp(msg.type, "transcript") == 0) {
                if (msg.is_user) {
                    self->display_->showUserText(msg.content);
                }
            } else if (strcmp(msg.type, "text") == 0) {
                self->display_->showAssistantText(msg.content);
            } else if (strcmp(msg.type, "error") == 0) {
                self->display_->showError(msg.content);
            }
        }

        // Persist volume to NVS from uiTask context (not LVGL task, which
        // crashes on flash writes). The dirty flag is set when leaving settings.
#ifdef TARGET_CORES3
        {
            auto* d = static_cast<Cores3Display*>(self->display_);
            // Gear-tap → settings navigation is handled by an LVGL timer
            // (pollSettingsFromLvglTask), not here — lv_scr_load must run in the
            // LVGL task context.
            if (d->consumeVolumeDirty()) {
                uint8_t vol = d->getSettingsVolume();
                self->nvs_.setVolume(vol);
                ESP_LOGI(TAG, "Volume persisted to NVS: %d%%", vol);
            }
        }
#endif
    }

    ESP_LOGI(TAG, "UI task stopped");
    vTaskDelete(nullptr);
}
