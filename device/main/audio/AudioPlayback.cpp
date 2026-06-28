#include "AudioPlayback.h"
#include "config.h"

#include "esp_log.h"
#include <cstring>

static const char* TAG = "AudioPlayback";

bool AudioPlayback::init(StreamBufferHandle_t spk_stream, i2s_chan_handle_t tx_channel) {
    spk_stream_ = spk_stream;
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

    // Don't enable TX here — enable on first audio data, disable when idle.
    // This prevents DMA from replaying stale buffer contents during silence.

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
    // Reset the stream buffer — discards all buffered audio instantly.
    if (spk_stream_) {
        xStreamBufferReset(spk_stream_);
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
        // Block until a full frame of audio is available (or timeout).
        size_t received = xStreamBufferReceive(
            self->spk_stream_, frame, frame_bytes, pdMS_TO_TICKS(50));

        if (received > 0) {
            // Got audio data — enable TX if not already playing.
            if (!self->playing_) {
                i2s_channel_enable(self->tx_chan_);
                self->playing_ = true;
            }

            // Pad partial frames with silence so I2S gets a full write.
            if (received < frame_bytes) {
                memset((uint8_t*)frame + received, 0, frame_bytes - received);
            }

            i2s_channel_write(self->tx_chan_, frame, frame_bytes, &bytes_written, pdMS_TO_TICKS(100));
        } else {
            // Timeout — no more audio. Disable TX to stop DMA from replaying
            // stale buffer contents (the "repeating garbled sound" artifact).
            if (self->playing_) {
                i2s_channel_disable(self->tx_chan_);
                self->playing_ = false;
            }
        }
    }

    ESP_LOGI(TAG, "Playback task stopped");
    vTaskDelete(nullptr);
}
