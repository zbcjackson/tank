#include "AudioCapture.h"
#include "config.h"

#include "driver/i2s_std.h"
#include "esp_log.h"
#include <cstring>

#if defined(TARGET_CORES3)
#include "hal/cores3/Cores3Pins.h"
#define I2S_DIN_PIN   CORES3_I2S_DIN_PIN
#define I2S_BCK_PIN   CORES3_I2S_BCK_PIN
#define I2S_WS_PIN    CORES3_I2S_WS_PIN
#define I2S_MCLK_PIN  CORES3_I2S_MCLK_PIN
#elif defined(TARGET_PYRAMID)
#include "hal/pyramid/PyramidPins.h"
#define I2S_DIN_PIN   PYRAMID_I2S_DIN_PIN
#define I2S_BCK_PIN   PYRAMID_I2S_BCK_PIN
#define I2S_WS_PIN    PYRAMID_I2S_WS_PIN
#define I2S_MCLK_PIN  PYRAMID_I2S_MCLK_PIN
#endif

static const char* TAG = "AudioCapture";

static i2s_chan_handle_t rx_chan = nullptr;

bool AudioCapture::init(QueueHandle_t mic_queue) {
    mic_queue_ = mic_queue;

    // Configure I2S RX channel (microphone)
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    chan_cfg.dma_desc_num = 6;
    chan_cfg.dma_frame_num = 240;  // DMA frames per descriptor

    esp_err_t err = i2s_new_channel(&chan_cfg, nullptr, &rx_chan);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create I2S RX channel: %s", esp_err_to_name(err));
        return false;
    }

    i2s_std_config_t std_cfg = {};
    std_cfg.clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(CONFIG_MIC_SAMPLE_RATE);
    std_cfg.slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO);
    std_cfg.gpio_cfg.bclk = (gpio_num_t)I2S_BCK_PIN;
    std_cfg.gpio_cfg.ws = (gpio_num_t)I2S_WS_PIN;
    std_cfg.gpio_cfg.dout = I2S_GPIO_UNUSED;
    std_cfg.gpio_cfg.din = (gpio_num_t)I2S_DIN_PIN;
    std_cfg.gpio_cfg.mclk = (gpio_num_t)I2S_MCLK_PIN;
    std_cfg.gpio_cfg.invert_flags.mclk_inv = false;
    std_cfg.gpio_cfg.invert_flags.bclk_inv = false;
    std_cfg.gpio_cfg.invert_flags.ws_inv = false;

    err = i2s_channel_init_std_mode(rx_chan, &std_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to init I2S RX std mode: %s", esp_err_to_name(err));
        return false;
    }

    ESP_LOGI(TAG, "I2S RX initialized: %d Hz, %d-bit, mono",
             CONFIG_MIC_SAMPLE_RATE, CONFIG_MIC_BITS);
    return true;
}

void AudioCapture::start() {
    if (running_) return;
    running_ = true;

    i2s_channel_enable(rx_chan);

    xTaskCreatePinnedToCore(
        captureTask, "audio_capture",
        CONFIG_AUDIO_TASK_STACK, this,
        CONFIG_AUDIO_TASK_PRIORITY, &task_,
        CONFIG_AUDIO_TASK_CORE
    );
}

void AudioCapture::stop() {
    running_ = false;
    if (task_) {
        vTaskDelay(pdMS_TO_TICKS(50));  // Let task exit
        task_ = nullptr;
    }
    if (rx_chan) {
        i2s_channel_disable(rx_chan);
        i2s_del_channel(rx_chan);
        rx_chan = nullptr;
    }
}

void AudioCapture::captureTask(void* arg) {
    auto* self = static_cast<AudioCapture*>(arg);

    // Buffer for one frame: 20ms at 16kHz mono 16-bit = 640 bytes
    int16_t frame[CONFIG_MIC_SAMPLE_RATE * CONFIG_MIC_FRAME_MS / 1000];
    const size_t frame_bytes = sizeof(frame);
    size_t bytes_read = 0;

    ESP_LOGI(TAG, "Capture task started (frame: %d bytes, %d ms)",
             (int)frame_bytes, CONFIG_MIC_FRAME_MS);

    while (self->running_) {
        esp_err_t err = i2s_channel_read(rx_chan, frame, frame_bytes, &bytes_read, pdMS_TO_TICKS(100));
        if (err != ESP_OK || bytes_read == 0) {
            continue;
        }

        // If muted, zero the frame (still push to keep timing consistent)
        if (self->muted_) {
            memset(frame, 0, bytes_read);
        }

        // Push frame to queue (non-blocking — drop if full)
        xQueueSend(self->mic_queue_, frame, 0);
    }

    ESP_LOGI(TAG, "Capture task stopped");
    vTaskDelete(nullptr);
}
