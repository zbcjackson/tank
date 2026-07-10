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

    // TX channel is already enabled by AudioCapture::start() as part of the
    // full-duplex pair. We never disable it — disabling TX on the shared I2S
    // peripheral kills the clock that RX (mic) depends on.

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
    // Don't disable TX — AudioCapture owns the channel and the shared clock.
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
            self->playing_ = true;

            // Pad partial frames with silence so I2S gets a full write.
            if (received < frame_bytes) {
                memset((uint8_t*)frame + received, 0, frame_bytes - received);
            }

            // Software volume: scale PCM samples before I2S output.
            // M5Unified uses this approach — the AW88298 hardware register
            // sets a fixed analog gain, actual volume is PCM multiplication.
            uint8_t vol = self->volume_;
            if (vol < 100) {
                for (size_t i = 0; i < FRAME_SAMPLES; i++) {
                    frame[i] = (int16_t)((int32_t)frame[i] * vol / 100);
                }
            }

#if CONFIG_AEC_ENABLE && !CONFIG_AEC_HW_REF
            // Software AEC reference: copy the exact PCM going to the speaker
            // (post-volume) so the AFE can subtract the echo. Non-blocking — if
            // the AFE feed task hasn't drained it, drop the oldest by resetting;
            // a lagging reference is worse than a short gap.
            if (self->ref_stream_) {
                if (xStreamBufferSpacesAvailable(self->ref_stream_) < frame_bytes) {
                    xStreamBufferReset(self->ref_stream_);
                }
                xStreamBufferSend(self->ref_stream_, frame, frame_bytes, 0);
            }
#endif

            i2s_channel_write(self->tx_chan_, frame, frame_bytes, &bytes_written, pdMS_TO_TICKS(100));
        } else {
            // Timeout — no more audio. Write silence to keep the TX DMA fed
            // (prevents stale-buffer replay). We NEVER disable the TX channel
            // because it shares the I2S clock with RX (mic). Disabling TX
            // permanently kills mic input until a full device reset.
            if (self->playing_) {
                memset(frame, 0, frame_bytes);
                // Write a few silence frames to flush the DMA pipeline and
                // ramp the DAC to zero (prevents the stop "pop").
                for (int i = 0; i < 3; i++) {
                    i2s_channel_write(self->tx_chan_, frame, frame_bytes,
                                      &bytes_written, pdMS_TO_TICKS(100));
                }
                self->playing_ = false;
            }
            // TX stays enabled, outputting zeros from the idle DMA buffers.
        }
    }

    ESP_LOGI(TAG, "Playback task stopped");
    vTaskDelete(nullptr);
}
