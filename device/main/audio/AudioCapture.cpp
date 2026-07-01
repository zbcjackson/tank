#include "AudioCapture.h"
#include "config.h"

#include "driver/i2s_std.h"
#include "esp_log.h"
#include <cstring>

#if defined(TARGET_CORES3)
#include "hal/cores3/Cores3Pins.h"
#define I2S_DIN_PIN   CORES3_I2S_DIN_PIN
#define I2S_DOUT_PIN  CORES3_I2S_DOUT_PIN
#define I2S_BCK_PIN   CORES3_I2S_BCK_PIN
#define I2S_WS_PIN    CORES3_I2S_WS_PIN
#define I2S_MCLK_PIN  CORES3_I2S_MCLK_PIN
#elif defined(TARGET_PYRAMID)
#include "hal/pyramid/PyramidPins.h"
#define I2S_DIN_PIN   PYRAMID_I2S_DIN_PIN
#define I2S_DOUT_PIN  PYRAMID_I2S_DOUT_PIN
#define I2S_BCK_PIN   PYRAMID_I2S_BCK_PIN
#define I2S_WS_PIN    PYRAMID_I2S_WS_PIN
#define I2S_MCLK_PIN  PYRAMID_I2S_MCLK_PIN
#endif

static const char* TAG = "AudioCapture";

bool AudioCapture::init(QueueHandle_t mic_queue) {
    mic_queue_ = mic_queue;

    // Create I2S TX-only channel first for speaker test.
    // RX will be added after we confirm TX works alone.
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    chan_cfg.dma_desc_num = 8;
    chan_cfg.dma_frame_num = 320;

    esp_err_t err = i2s_new_channel(&chan_cfg, &tx_chan_, &rx_chan_);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create I2S full-duplex channel: %s", esp_err_to_name(err));
        return false;
    }

    // Configure TX (speaker output) — 16kHz mono Philips
    i2s_std_config_t tx_cfg = {};
    tx_cfg.clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(CONFIG_SPK_SAMPLE_RATE);
    tx_cfg.clk_cfg.mclk_multiple = I2S_MCLK_MULTIPLE_256;
    tx_cfg.slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO);
    tx_cfg.gpio_cfg.bclk = (gpio_num_t)I2S_BCK_PIN;
    tx_cfg.gpio_cfg.ws = (gpio_num_t)I2S_WS_PIN;
    tx_cfg.gpio_cfg.dout = (gpio_num_t)I2S_DOUT_PIN;
    tx_cfg.gpio_cfg.din = I2S_GPIO_UNUSED;
    tx_cfg.gpio_cfg.mclk = (gpio_num_t)I2S_MCLK_PIN;
    tx_cfg.gpio_cfg.invert_flags.mclk_inv = false;
    tx_cfg.gpio_cfg.invert_flags.bclk_inv = false;
    tx_cfg.gpio_cfg.invert_flags.ws_inv = false;

    err = i2s_channel_init_std_mode(tx_chan_, &tx_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to init I2S TX std mode: %s", esp_err_to_name(err));
        return false;
    }

    // Enable TX immediately for the speaker test
    i2s_channel_enable(tx_chan_);

    // Configure RX (microphone input) — 16kHz, 16-bit, mono, left slot
    i2s_std_config_t rx_cfg = {};
    rx_cfg.clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(CONFIG_MIC_SAMPLE_RATE);
    rx_cfg.clk_cfg.mclk_multiple = I2S_MCLK_MULTIPLE_256;
    rx_cfg.slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO);
    rx_cfg.slot_cfg.slot_mask = I2S_STD_SLOT_LEFT;
    rx_cfg.gpio_cfg.bclk = (gpio_num_t)I2S_BCK_PIN;
    rx_cfg.gpio_cfg.ws = (gpio_num_t)I2S_WS_PIN;
    rx_cfg.gpio_cfg.dout = I2S_GPIO_UNUSED;
    rx_cfg.gpio_cfg.din = (gpio_num_t)I2S_DIN_PIN;
    rx_cfg.gpio_cfg.mclk = (gpio_num_t)I2S_MCLK_PIN;
    rx_cfg.gpio_cfg.invert_flags.mclk_inv = false;
    rx_cfg.gpio_cfg.invert_flags.bclk_inv = false;
    rx_cfg.gpio_cfg.invert_flags.ws_inv = false;

    err = i2s_channel_init_std_mode(rx_chan_, &rx_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to init I2S RX std mode: %s", esp_err_to_name(err));
        return false;
    }

    ESP_LOGI(TAG, "I2S full-duplex initialized: %d Hz, 16-bit, mono, MCLK×256",
             CONFIG_MIC_SAMPLE_RATE);
    return true;
}

void AudioCapture::start() {
    if (running_) return;
    running_ = true;

    // In continuous (non-PTT) mode nothing calls resume(), so unpause here.
    // In PTT mode we stay paused until the first button press.
#if !CONFIG_PUSH_TO_TALK
    paused_ = false;
#endif

    i2s_channel_enable(rx_chan_);

    xTaskCreatePinnedToCore(
        captureTask, "mic_task", CONFIG_AUDIO_TASK_STACK,
        this, CONFIG_AUDIO_TASK_PRIORITY, nullptr, CONFIG_AUDIO_TASK_CORE
    );
}

void AudioCapture::pause() {
    // Gate frame queuing rather than disabling the I2S RX channel. On the
    // shared full-duplex channel, toggling RX enable/disable is fragile —
    // re-enabling after a pause could fail and silently kill mic input
    // (symptom: first PTT works, later ones send no audio). The channel runs
    // continuously; we just stop pushing frames to the send queue.
    paused_ = true;
}

void AudioCapture::resume() {
    paused_ = false;
}



void AudioCapture::stop() {
    running_ = false;
    if (rx_chan_) {
        i2s_channel_disable(rx_chan_);
    }
    if (tx_chan_) {
        i2s_channel_disable(tx_chan_);
    }
    if (rx_chan_) {
        i2s_del_channel(rx_chan_);
        rx_chan_ = nullptr;
    }
    if (tx_chan_) {
        i2s_del_channel(tx_chan_);
        tx_chan_ = nullptr;
    }
}

void AudioCapture::captureTask(void* arg) {
    auto* self = static_cast<AudioCapture*>(arg);

    // 20ms frame at 16kHz mono 16-bit = 320 samples = 640 bytes
    constexpr size_t FRAME_SAMPLES = CONFIG_MIC_SAMPLE_RATE * CONFIG_MIC_FRAME_MS / 1000;
    int16_t frame[FRAME_SAMPLES];
    const size_t frame_bytes = sizeof(frame);
    size_t bytes_read = 0;

    uint32_t frame_count = 0;
    int16_t max_sample = 0;

    ESP_LOGI(TAG, "Capture task started (%d samples, %d bytes, %dms)",
             (int)FRAME_SAMPLES, (int)frame_bytes, CONFIG_MIC_FRAME_MS);

    while (self->running_) {
        esp_err_t err = i2s_channel_read(self->rx_chan_, frame, frame_bytes, &bytes_read, pdMS_TO_TICKS(100));
        if (err != ESP_OK || bytes_read == 0) {
            continue;
        }

        // Track peak amplitude
        for (size_t i = 0; i < bytes_read / sizeof(int16_t); i++) {
            int16_t abs_val = frame[i] > 0 ? frame[i] : -frame[i];
            if (abs_val > max_sample) max_sample = abs_val;
        }
        frame_count++;

        // Log audio level every 5 seconds
        if (frame_count % 250 == 0) {
            ESP_LOGI(TAG, "Audio: frames=%lu, peak=%d",
                     (unsigned long)frame_count, max_sample);
            max_sample = 0;
        }

        // Push to queue for WebSocket transmission. The capture task always
        // runs; the wsSendTask decides what actually gets sent based on PTT
        // state (talking_ / drain_frames_).
        if (!self->paused_) {
            if (xQueueSend(self->mic_queue_, frame, 0) != pdTRUE) {
                // Queue full — drop frame
            }
        }
    }

    ESP_LOGI(TAG, "Capture task stopped");
    vTaskDelete(nullptr);
}
