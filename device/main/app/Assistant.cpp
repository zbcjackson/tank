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

    // Create queues / stream buffers
    mic_queue_ = xQueueCreate(CONFIG_MIC_QUEUE_LEN, CONFIG_MIC_FRAME_BYTES);
    // Speaker stream: 256KB buffer holds ~8s of 16kHz mono 16-bit audio.
    // Allocated from PSRAM (CoreS3 has 8MB). Absorbs full TTS responses
    // without dropping data from the non-blocking WS callback.
    spk_stream_ = xStreamBufferCreateWithCaps(256 * 1024, CONFIG_SPK_FRAME_BYTES, MALLOC_CAP_SPIRAM);
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
    if (!playback_.init(spk_stream_, capture_.getTxChannel())) {
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
    if (!spk_stream_) return;

    // Write raw PCM bytes into the stream buffer. Non-blocking: if the buffer
    // is full, excess bytes are silently dropped (backpressure from playback
    // consuming at real-time rate means this rarely happens with a 32KB buffer).
    size_t bytes = samples * sizeof(int16_t);
    xStreamBufferSend(spk_stream_, pcm, bytes, 0);

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
        // Wait for a mic frame
        if (xQueueReceive(self->mic_queue_, frame, pdMS_TO_TICKS(100)) == pdTRUE) {
#if CONFIG_PUSH_TO_TALK
            if (self->talking_) {
                // Button held — stream live mic audio.
                if (self->ws_.isConnected()) {
                    self->ws_.sendAudio(frame, SAMPLES);
                }
            } else if (self->flush_frames_ > 0) {
                // Released — drain the bounded tail captured at release time so
                // the end of speech isn't clipped.
                if (self->ws_.isConnected()) {
                    self->ws_.sendAudio(frame, SAMPLES);
                }
                self->flush_frames_--;
            }
            // else: idle — discard mic frames so the backend only sees held
            // utterances.
#else
            if (self->ws_.isConnected()) {
                self->ws_.sendAudio(frame, SAMPLES);
            }
#endif
        }

#if CONFIG_PUSH_TO_TALK
        // After the tail has fully drained, finalize the utterance once.
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
        // Poll push-to-talk button and detect press/release transitions.
        bool pressed = self->display_->pollPressed();
        if (pressed && !was_pressed) {
            // Press: interrupt any ongoing playback and start streaming mic.
            ESP_LOGI(TAG, "PTT pressed — start streaming");
            self->ws_.sendInterrupt();
            // Drop any audio still queued/buffered from a previous reply so the
            // new turn starts clean (no stale tail, no partial-frame glitch).
            self->playback_.flush();
            // Resume mic capture (was paused during playback).
            self->capture_.resume();
            self->talking_ = true;
            self->session_.setState(Session::State::LISTENING);
            self->display_->showTalkState(true);
            self->display_->showStatus("Listening...");
        } else if (!pressed && was_pressed) {
            // Release: stop accepting new audio, but hand the frames already
            // buffered in the mic queue to wsSendTask so the tail of speech is
            // flushed before end_of_utterance. wsSendTask sends the signal once
            // the bounded tail drains.
            self->flush_frames_ = uxQueueMessagesWaiting(self->mic_queue_);
            ESP_LOGI(TAG, "PTT released — flushing %d frames then EOU", self->flush_frames_);
            self->eou_pending_ = true;
            self->talking_ = false;
            // Pause mic capture so I2S RX doesn't contend with TX during playback.
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
    }

    ESP_LOGI(TAG, "UI task stopped");
    vTaskDelete(nullptr);
}
