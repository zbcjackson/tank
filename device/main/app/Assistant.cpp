#include "Assistant.h"
#include "ui/Cores3Display.h"
#include "config.h"

#include "esp_log.h"
#include "nvs_flash.h"
#include <cstring>

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
    mic_queue_ = xQueueCreate(CONFIG_MIC_QUEUE_LEN, CONFIG_MIC_FRAME_BYTES);
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

    // Audio
    if (!capture_.init(mic_queue_)) {
        ESP_LOGE(TAG, "Audio capture init failed");
        return false;
    }
    if (!playback_.init(spk_stream_, capture_.getTxChannel())) {
        ESP_LOGE(TAG, "Audio playback init failed");
        return false;
    }

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

void Assistant::onWsAudio(const int16_t* pcm, size_t samples, uint32_t sample_rate) {
    if (!spk_stream_) return;

    size_t bytes = samples * sizeof(int16_t);
    // Use a short blocking timeout so we don't drop frames when the buffer is
    // temporarily full (causes audible glitches/blasts on long responses).
    // The playback task drains ~32KB/s; a 50ms wait lets it clear one frame.
    xStreamBufferSend(spk_stream_, pcm, bytes, pdMS_TO_TICKS(50));

    if (session_.getState() != Session::State::SPEAKING) {
        session_.setState(Session::State::SPEAKING);
    }
}

void Assistant::onWsMessage(const WsMessage& msg) {
    // Route message to UI task via event queue
    xQueueSend(event_queue_, &msg, 0);

    // Handle state transitions
    if (strcmp(msg.type, "signal") == 0) {
        if (strcmp(msg.content, "ready") == 0) {
            session_.setState(Session::State::READY);
        } else if (strcmp(msg.content, "processing_started") == 0) {
            session_.setState(Session::State::PROCESSING);
        } else if (strcmp(msg.content, "processing_ended") == 0) {
            session_.setState(Session::State::READY);
        }
    }
}

// ─── Tasks ──────────────────────────────────────────────────────────────────

void Assistant::wsSendTask(void* arg) {
    auto* self = static_cast<Assistant*>(arg);

    constexpr size_t SAMPLES = CONFIG_MIC_SAMPLE_RATE * CONFIG_MIC_FRAME_MS / 1000;
    int16_t frame[SAMPLES];

    ESP_LOGI(TAG, "WS send task started");

    while (self->running_) {
        if (xQueueReceive(self->mic_queue_, frame, pdMS_TO_TICKS(100)) == pdTRUE) {
#if CONFIG_PUSH_TO_TALK
            if (self->talking_) {
                if (self->ws_.isConnected()) {
                    self->ws_.sendAudio(frame, SAMPLES);
                }
            } else if (self->flush_frames_ > 0) {
                if (self->ws_.isConnected()) {
                    self->ws_.sendAudio(frame, SAMPLES);
                }
                self->flush_frames_--;
            }
#else
            if (self->ws_.isConnected()) {
                self->ws_.sendAudio(frame, SAMPLES);
            }
#endif
        }

#if CONFIG_PUSH_TO_TALK
        if (self->eou_pending_ && !self->talking_ && self->flush_frames_ == 0) {
            self->eou_pending_ = false;
            if (self->ws_.isConnected()) {
                self->ws_.sendEndOfUtterance();
            }
        }
#endif
    }

    ESP_LOGI(TAG, "WS send task stopped");
    vTaskDelete(nullptr);
}

void Assistant::uiTask(void* arg) {
    auto* self = static_cast<Assistant*>(arg);

    WsMessage msg;
    bool was_pressed = false;
    ESP_LOGI(TAG, "UI task started");

    while (self->running_) {
#if CONFIG_PUSH_TO_TALK
        // Poll PTT button (LVGL event-driven via pollPressed)
        bool pressed = self->display_->pollPressed();
        if (pressed && !was_pressed) {
            ESP_LOGI(TAG, "PTT pressed — start streaming");
            self->ws_.sendInterrupt();
            self->playback_.flush();
            self->capture_.resume();
            // Small delay to let the capture task's current iteration finish
            // (it may have a stale frame mid-push from before pause took effect).
            vTaskDelay(pdMS_TO_TICKS(25));
            // Now drain any stale frames that accumulated.
            xQueueReset(self->mic_queue_);
            self->talking_ = true;
            self->session_.setState(Session::State::LISTENING);
            self->display_->showTalkState(true);
            self->display_->showStatus("Listening...");
            // Clear stale text from last turn so it doesn't flash at start.
            self->display_->showAssistantText("");
        } else if (!pressed && was_pressed) {
            self->flush_frames_ = uxQueueMessagesWaiting(self->mic_queue_);
            ESP_LOGI(TAG, "PTT released — flushing %d frames then EOU", self->flush_frames_);
            self->eou_pending_ = true;
            self->talking_ = false;
            self->capture_.pause();
            self->session_.setState(Session::State::PROCESSING);
            self->display_->showTalkState(false);
            self->display_->showStatus("Processing...");
        }
        was_pressed = pressed;
#endif

        if (xQueueReceive(self->event_queue_, &msg, pdMS_TO_TICKS(20)) == pdTRUE) {
            if (strcmp(msg.type, "signal") == 0) {
                if (strcmp(msg.content, "ready") == 0) {
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
