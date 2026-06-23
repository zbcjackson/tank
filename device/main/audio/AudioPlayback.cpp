#include "AudioPlayback.h"
#include "config.h"

#include "driver/i2s_std.h"
#include "esp_log.h"
#include <cstring>

#if defined(TARGET_CORES3)
#include "hal/cores3/Cores3Pins.h"
#define I2S_DOUT_PIN  CORES3_I2S_DOUT_PIN
#define I2S_BCK_PIN   CORES3_I2S_BCK_PIN
#define I2S_WS_PIN    CORES3_I2S_WS_PIN
#define I2S_MCLK_PIN  CORES3_I2S_MCLK_PIN
#elif defined(TARGET_PYRAMID)
#include "hal/pyramid/PyramidPins.h"
#define I2S_DOUT_PIN  PYRAMID_I2S_DOUT_PIN
#define I2S_BCK_PIN   PYRAMID_I2S_BCK_PIN
#define I2S_WS_PIN    PYRAMID_I2S_WS_PIN
#define I2S_MCLK_PIN  PYRAMID_I2S_MCLK_PIN
#endif

static const char* TAG = "AudioPlayback";

static i2s_chan_handle_t tx_chan = nullptr;

bool AudioPlayback::init(QueueHandle_t spk_queue) {
    spk_queue_ = spk_queue;

    // Configure I2S TX channel (speaker)
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_1, I2S_ROLE_MASTER);
    chan_cfg.dma_desc_num = 6;
    chan_cfg.dma_frame_num = 240;

    esp_err_t err = i2s_new_channel(&chan_cfg, &tx_chan, nullptr);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create I2S TX channel: %s", esp_err_to_name(err));
        return false;
    }

    i2s_std_config_t std_cfg = {};
    std_cfg.clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(CONFIG_SPK_SAMPLE_RATE);
    std_cfg.slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO);
    std_cfg.gpio_cfg.bclk = (gpio_num_t)I2S_BCK_PIN;
    std_cfg.gpio_cfg.ws = (gpio_num_t)I2S_WS_PIN;
    std_cfg.gpio_cfg.dout = (gpio_num_t)I2S_DOUT_PIN;
    std_cfg.gpio_cfg.din = I2S_GPIO_UNUSED;
    std_cfg.gpio_cfg.mclk = (gpio_num_t)I2S_MCLK_PIN;
    std_cfg.gpio_cfg.invert_flags.mclk_inv = false;
    std_cfg.gpio_cfg.invert_flags.bclk_inv = false;
    std_cfg.gpio_cfg.invert_flags.ws_inv = false;

    err = i2s_channel_init_std_mode(tx_chan, &std_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to init I2S TX std mode: %s", esp_err_to_name(err));
        return false;
    }

    ESP_LOGI(TAG, "I2S TX initialized: %d Hz, %d-bit, mono",
             CONFIG_SPK_SAMPLE_RATE, CONFIG_SPK_BITS);
    return true;
}

void AudioPlayback::start() {
    if (running_) return;
    running_ = true;

    i2s_channel_enable(tx_chan);

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
    if (tx_chan) {
        i2s_channel_disable(tx_chan);
        i2s_del_channel(tx_chan);
        tx_chan = nullptr;
    }
}

void AudioPlayback::flush() {
    // Drain the queue — discard all buffered audio
    int16_t discard[CONFIG_SPK_SAMPLE_RATE * CONFIG_MIC_FRAME_MS / 1000];
    while (xQueueReceive(spk_queue_, discard, 0) == pdTRUE) {
        // discard
    }
    playing_ = false;
}

void AudioPlayback::playbackTask(void* arg) {
    auto* self = static_cast<AudioPlayback*>(arg);

    // Buffer for one playback frame
    // Server sends 24kHz, so frame size differs from mic
    // Max expected: 24000 * 20ms / 1000 = 480 samples = 960 bytes
    int16_t frame[480];
    size_t bytes_written = 0;

    ESP_LOGI(TAG, "Playback task started");

    while (self->running_) {
        // Wait up to 50ms for audio data
        if (xQueueReceive(self->spk_queue_, frame, pdMS_TO_TICKS(50)) == pdTRUE) {
            self->playing_ = true;

            // Write the frame size that matches what was queued
            // The WsClient pushes variable-length frames based on what the server sends
            size_t frame_bytes = sizeof(frame);  // Full buffer; actual data may be less
            esp_err_t err = i2s_channel_write(tx_chan, frame, frame_bytes, &bytes_written, pdMS_TO_TICKS(100));
            if (err != ESP_OK) {
                ESP_LOGW(TAG, "I2S write error: %s", esp_err_to_name(err));
            }
        } else {
            // No audio available — send silence to keep DMA running
            if (self->playing_) {
                self->playing_ = false;
            }
        }
    }

    ESP_LOGI(TAG, "Playback task stopped");
    vTaskDelete(nullptr);
}
