#include "AudioCapture.h"
#include "config.h"

#include "driver/i2s_std.h"
#if CONFIG_AEC_ENABLE && CONFIG_AEC_HW_REF
#include "driver/i2s_tdm.h"
#endif
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
    // Emit silence (not the stale DMA buffer) on a TX underrun. Without this,
    // when the playback task can't refill the DMA ring in time — a late network
    // chunk or a brief task preemption mid-response — the hardware replays the
    // last DMA buffers, which is heard as repeating noise a few words into the
    // reply. auto_clear zeros the buffer after each send, so an underrun is at
    // most a short silence gap.
    chan_cfg.auto_clear = true;

    esp_err_t err = i2s_new_channel(&chan_cfg, &tx_chan_, &rx_chan_);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create I2S full-duplex channel: %s", esp_err_to_name(err));
        return false;
    }

#if CONFIG_AEC_ENABLE && CONFIG_AEC_HW_REF
    // ── TDM full-duplex ───────────────────────────────────────────────────────
    // TX and RX share one I2S controller and one clock domain (ESP32 master).
    // To read the ES7210's MIC3 echo-reference channel we run the RX in 4-slot
    // TDM; the shared frame forces the TX into the same TDM framing, so the
    // speaker rides in slot 0. Both directions use CONFIG_AEC_TDM_SLOTS slots.
    const i2s_tdm_slot_mask_t tx_slots = (i2s_tdm_slot_mask_t)I2S_TDM_SLOT0;
    const i2s_tdm_slot_mask_t rx_slots =
        (i2s_tdm_slot_mask_t)(I2S_TDM_SLOT0 | I2S_TDM_SLOT2);  // MIC1 + MIC3 (ref)

    i2s_tdm_config_t tx_cfg = {};
    tx_cfg.clk_cfg = I2S_TDM_CLK_DEFAULT_CONFIG(CONFIG_SPK_SAMPLE_RATE);
    tx_cfg.clk_cfg.mclk_multiple = I2S_MCLK_MULTIPLE_256;
    tx_cfg.slot_cfg = I2S_TDM_PHILIPS_SLOT_DEFAULT_CONFIG(
        I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO, tx_slots);
    tx_cfg.slot_cfg.total_slot = CONFIG_AEC_TDM_SLOTS;
    tx_cfg.gpio_cfg.bclk = (gpio_num_t)I2S_BCK_PIN;
    tx_cfg.gpio_cfg.ws = (gpio_num_t)I2S_WS_PIN;
    tx_cfg.gpio_cfg.dout = (gpio_num_t)I2S_DOUT_PIN;
    tx_cfg.gpio_cfg.din = I2S_GPIO_UNUSED;
    tx_cfg.gpio_cfg.mclk = (gpio_num_t)I2S_MCLK_PIN;

    err = i2s_channel_init_tdm_mode(tx_chan_, &tx_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to init I2S TX TDM mode: %s", esp_err_to_name(err));
        return false;
    }
    i2s_channel_enable(tx_chan_);

    i2s_tdm_config_t rx_cfg = {};
    rx_cfg.clk_cfg = I2S_TDM_CLK_DEFAULT_CONFIG(CONFIG_MIC_SAMPLE_RATE);
    rx_cfg.clk_cfg.mclk_multiple = I2S_MCLK_MULTIPLE_256;
    rx_cfg.slot_cfg = I2S_TDM_PHILIPS_SLOT_DEFAULT_CONFIG(
        I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO, rx_slots);
    rx_cfg.slot_cfg.total_slot = CONFIG_AEC_TDM_SLOTS;
    rx_cfg.gpio_cfg.bclk = (gpio_num_t)I2S_BCK_PIN;
    rx_cfg.gpio_cfg.ws = (gpio_num_t)I2S_WS_PIN;
    rx_cfg.gpio_cfg.dout = I2S_GPIO_UNUSED;
    rx_cfg.gpio_cfg.din = (gpio_num_t)I2S_DIN_PIN;
    rx_cfg.gpio_cfg.mclk = (gpio_num_t)I2S_MCLK_PIN;

    err = i2s_channel_init_tdm_mode(rx_chan_, &rx_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to init I2S RX TDM mode: %s", esp_err_to_name(err));
        return false;
    }

    ESP_LOGI(TAG, "I2S TDM full-duplex initialized: %d Hz, 16-bit, %d slots (mic=%d, ref=%d), MCLK×256",
             CONFIG_MIC_SAMPLE_RATE, CONFIG_AEC_TDM_SLOTS,
             CONFIG_AEC_MIC_SLOT, CONFIG_AEC_REF_SLOT);
    return true;
#else
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
#endif
}

void AudioCapture::start() {
    if (running_) return;
    running_ = true;

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

    // 20ms frame at 16kHz mono 16-bit = 320 samples per channel.
    constexpr size_t FRAME_SAMPLES = CONFIG_MIC_SAMPLE_RATE * CONFIG_MIC_FRAME_MS / 1000;

#if CONFIG_AEC_ENABLE && CONFIG_AEC_HW_REF
    // TDM stereo reading slots 0+2 delivers only the two enabled slots,
    // interleaved: [mic0, ref0, mic1, ref1, ...]. Read both channels' worth of
    // samples per frame, then push the interleaved [mic, ref] pair (already the
    // layout the AFE feed() expects: mic channel(s) first, reference last).
    constexpr size_t CH = CONFIG_AFE_TOTAL_CH;              // 2 (mic + ref)
    int16_t frame[FRAME_SAMPLES * CH];
    const size_t frame_bytes = sizeof(frame);
    size_t bytes_read = 0;

    uint32_t frame_count = 0;
    int16_t max_mic = 0;
    int16_t max_ref = 0;

    ESP_LOGI(TAG, "Capture task started (TDM: %d samples/ch, %d ch, %d bytes, %dms)",
             (int)FRAME_SAMPLES, (int)CH, (int)frame_bytes, CONFIG_MIC_FRAME_MS);

    while (self->running_) {
        esp_err_t err = i2s_channel_read(self->rx_chan_, frame, frame_bytes, &bytes_read, pdMS_TO_TICKS(100));
        if (err != ESP_OK || bytes_read == 0) {
            continue;
        }

        const size_t samples_read = bytes_read / sizeof(int16_t);

#if CONFIG_AEC_DIAG
        // Diagnostic: track per-channel peak to confirm the MIC3 reference is
        // wired (R40/R42 populated). While the speaker plays, the ref channel
        // (slot 2) should show amplitude correlated with playback; if it stays
        // at noise floor, the hardware reference path is not present.
        for (size_t i = 0; i + 1 < samples_read; i += CH) {
            int16_t m = frame[i] > 0 ? frame[i] : -frame[i];
            int16_t r = frame[i + 1] > 0 ? frame[i + 1] : -frame[i + 1];
            if (m > max_mic) max_mic = m;
            if (r > max_ref) max_ref = r;
        }
        frame_count++;
        if (frame_count % 250 == 0) {
            ESP_LOGI(TAG, "AEC diag: frames=%lu, mic_peak=%d, ref_peak=%d",
                     (unsigned long)frame_count, max_mic, max_ref);
            max_mic = 0;
            max_ref = 0;
        }
#else
        (void)samples_read;
        (void)max_ref;
        frame_count++;
#endif

        // Push the interleaved [mic, ref] frame. wsSendTask/afeFetch decide what
        // is actually sent based on PTT/wake state.
        if (!self->paused_) {
            if (xQueueSend(self->mic_queue_, frame, 0) != pdTRUE) {
                // Queue full — drop frame
            }
        }
    }
#else
    // 20ms frame at 16kHz mono 16-bit = 320 samples = 640 bytes
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
#endif

    ESP_LOGI(TAG, "Capture task stopped");
    vTaskDelete(nullptr);
}
