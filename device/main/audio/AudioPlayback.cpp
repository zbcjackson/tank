#include "AudioPlayback.h"
#include "config.h"

#include "esp_log.h"
#include <cstring>

static const char* TAG = "AudioPlayback";

bool AudioPlayback::init(QueueHandle_t spk_queue, i2s_chan_handle_t tx_channel) {
    spk_queue_ = spk_queue;
    tx_chan_ = tx_channel;

    if (!tx_chan_) {
        ESP_LOGE(TAG, "TX channel handle is null");
        return false;
    }

    ESP_LOGI(TAG, "I2S TX attached: %d Hz, %d-bit, mono",
             CONFIG_SPK_SAMPLE_RATE, CONFIG_SPK_BITS);
    return true;
}

void AudioPlayback::start() {
    if (running_) return;
    running_ = true;

    i2s_channel_enable(tx_chan_);

    xTaskCreatePinnedToCore(
        playbackTask, "audio_playback",
        CONFIG_AUDIO_TASK_STACK, this,
        CONFIG_AUDIO_TASK_PRIORITY, &task_,
        CONFIG_AUDIO_TASK_CORE
    );
}

void AudioPlayback::stop() {
    running_ = false;
    if (task_) {
        vTaskDelay(pdMS_TO_TICKS(50));
        task_ = nullptr;
    }
    if (tx_chan_) {
        i2s_channel_disable(tx_chan_);
        tx_chan_ = nullptr;  // Don't delete — AudioCapture owns the channel
    }
}

void AudioPlayback::flush() {
    // Drain the queue — discard all buffered audio
    constexpr size_t FRAME_SAMPLES = CONFIG_SPK_SAMPLE_RATE * CONFIG_SPK_FRAME_MS / 1000;
    int16_t discard[FRAME_SAMPLES];
    while (xQueueReceive(spk_queue_, discard, 0) == pdTRUE) {
        // discard
    }
    playing_ = false;
}

void AudioPlayback::playbackTask(void* arg) {
    auto* self = static_cast<AudioPlayback*>(arg);

    constexpr size_t FRAME_SAMPLES = CONFIG_SPK_SAMPLE_RATE * CONFIG_SPK_FRAME_MS / 1000;  // 320
    int16_t frame[FRAME_SAMPLES];
    const size_t frame_bytes = FRAME_SAMPLES * sizeof(int16_t);  // 640 bytes
    size_t bytes_written = 0;

    ESP_LOGI(TAG, "Playback task started (%d samples, %d bytes)",
             (int)FRAME_SAMPLES, (int)frame_bytes);

    while (self->running_) {
        // Wait up to 50ms for audio data
        if (xQueueReceive(self->spk_queue_, frame, pdMS_TO_TICKS(50)) == pdTRUE) {
            self->playing_ = true;

            esp_err_t err = i2s_channel_write(self->tx_chan_, frame, frame_bytes, &bytes_written, pdMS_TO_TICKS(100));
            if (err != ESP_OK) {
                ESP_LOGW(TAG, "I2S write error: %s", esp_err_to_name(err));
            }
        } else {
            if (self->playing_) {
                self->playing_ = false;
            }
        }
    }

    ESP_LOGI(TAG, "Playback task stopped");
    vTaskDelete(nullptr);
}
