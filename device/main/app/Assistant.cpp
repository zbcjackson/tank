#include "Assistant.h"
#include "config.h"

#include "esp_log.h"
#include <cstring>

static const char* TAG = "Assistant";

// Forward declare display factory
extern Display* createDisplay();

bool Assistant::init() {
    ESP_LOGI(TAG, "Initializing Tank Device Client");

    // Session
    session_.init();
    session_.setState(Session::State::IDLE);

    // Display (serial stub for now)
    display_ = createDisplay();
    if (!display_->init()) {
        ESP_LOGE(TAG, "Display init failed");
        return false;
    }
    display_->showStatus("Initializing...");

    // Create queues
    mic_queue_ = xQueueCreate(CONFIG_MIC_QUEUE_LEN, CONFIG_MIC_FRAME_BYTES);
    spk_queue_ = xQueueCreate(CONFIG_SPK_QUEUE_LEN, CONFIG_SPK_FRAME_BYTES);
    event_queue_ = xQueueCreate(CONFIG_EVENT_QUEUE_LEN, sizeof(WsMessage));

    if (!mic_queue_ || !spk_queue_ || !event_queue_) {
        ESP_LOGE(TAG, "Failed to create queues");
        return false;
    }

    // WebSocket client
    ws_.init(CONFIG_BACKEND_HOST, CONFIG_BACKEND_PORT, session_.getId());
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
    if (!playback_.init(spk_queue_, capture_.getTxChannel())) {
        ESP_LOGE(TAG, "Audio playback init failed");
        return false;
    }

    // WiFi
    wifi_.onConnected([this]() { onWiFiConnected(); });
    wifi_.onDisconnected([this]() { onWiFiDisconnected(); });

    if (!wifi_.init(CONFIG_WIFI_SSID, CONFIG_WIFI_PASSWORD)) {
        ESP_LOGE(TAG, "WiFi init failed");
        return false;
    }

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

    // Start WS send task (reads from mic_queue, sends to backend)
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
    if (!spk_queue_) return;

    constexpr size_t FRAME_SAMPLES = CONFIG_SPK_SAMPLE_RATE * CONFIG_SPK_FRAME_MS / 1000;  // 320
    size_t offset = 0;

    // Split incoming audio into fixed-size queue frames
    while (offset + FRAME_SAMPLES <= samples) {
        xQueueSend(spk_queue_, pcm + offset, 0);
        offset += FRAME_SAMPLES;
    }

    // Handle remaining samples: pad with silence and queue
    if (offset < samples) {
        int16_t tail[FRAME_SAMPLES];
        size_t remaining = samples - offset;
        memcpy(tail, pcm + offset, remaining * sizeof(int16_t));
        memset(tail + remaining, 0, (FRAME_SAMPLES - remaining) * sizeof(int16_t));
        xQueueSend(spk_queue_, tail, 0);
    }

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

    int16_t frame[CONFIG_MIC_SAMPLE_RATE * CONFIG_MIC_FRAME_MS / 1000];

    ESP_LOGI(TAG, "WS send task started");

    while (self->running_) {
        // Wait for a mic frame
        if (xQueueReceive(self->mic_queue_, frame, pdMS_TO_TICKS(100)) == pdTRUE) {
#if CONFIG_PUSH_TO_TALK
            // Push-to-talk: only stream while the button is held.
            if (!self->talking_) {
                continue;
            }
#endif
            if (self->ws_.isConnected()) {
                size_t samples = CONFIG_MIC_SAMPLE_RATE * CONFIG_MIC_FRAME_MS / 1000;
                self->ws_.sendAudio(frame, samples);
            }
        }
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
        // Poll push-to-talk button and detect press/release transitions.
        bool pressed = self->display_->pollPressed();
        if (pressed && !was_pressed) {
            // Press: interrupt any ongoing playback and start streaming mic.
            self->ws_.sendInterrupt();
            self->talking_ = true;
            self->session_.setState(Session::State::LISTENING);
            self->display_->showStatus("Listening...");
        } else if (!pressed && was_pressed) {
            // Release: stop streaming and force-finalize the utterance.
            self->talking_ = false;
            self->ws_.sendEndOfUtterance();
            self->session_.setState(Session::State::PROCESSING);
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
    }

    ESP_LOGI(TAG, "UI task stopped");
    vTaskDelete(nullptr);
}
