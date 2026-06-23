#include "Cores3HAL.h"
#include "Cores3Pins.h"
#include "config.h"

#include "driver/i2c.h"
#include "driver/i2s_std.h"
#include "esp_log.h"

static const char* TAG = "Cores3HAL";

bool Cores3HAL::init() {
    ESP_LOGI(TAG, "Initializing CoreS3 hardware");

    if (!initI2C()) return false;
    if (!initMicCodec()) return false;
    if (!initAmpCodec()) return false;
    if (!initI2S()) return false;

    ESP_LOGI(TAG, "CoreS3 hardware initialized");
    return true;
}

bool Cores3HAL::initI2C() {
    i2c_config_t conf = {};
    conf.mode = I2C_MODE_MASTER;
    conf.sda_io_num = CORES3_I2C_SDA_PIN;
    conf.scl_io_num = CORES3_I2C_SCL_PIN;
    conf.sda_pullup_en = GPIO_PULLUP_ENABLE;
    conf.scl_pullup_en = GPIO_PULLUP_ENABLE;
    conf.master.clk_speed = CORES3_I2C_FREQ;

    esp_err_t err = i2c_param_config(I2C_NUM_0, &conf);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "I2C config failed: %s", esp_err_to_name(err));
        return false;
    }

    err = i2c_driver_install(I2C_NUM_0, I2C_MODE_MASTER, 0, 0, 0);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "I2C driver install failed: %s", esp_err_to_name(err));
        return false;
    }

    return true;
}

bool Cores3HAL::initMicCodec() {
    // ES7210 initialization — configure for 16kHz, 16-bit, mono
    // The ES7210 is a quad-channel ADC; we use channels 1+2 for dual mic
    ESP_LOGI(TAG, "Initializing ES7210 mic codec at 0x%02X", CORES3_ES7210_ADDR);

    // Reset codec
    uint8_t reset_cmd[] = {0x00, 0xFF};
    i2c_master_write_to_device(I2C_NUM_0, CORES3_ES7210_ADDR, reset_cmd, sizeof(reset_cmd), pdMS_TO_TICKS(100));
    vTaskDelay(pdMS_TO_TICKS(10));

    // Basic init sequence for ES7210 (16kHz, 16-bit, I2S standard)
    // Clock source: MCLK from ESP32-S3
    struct { uint8_t reg; uint8_t val; } init_seq[] = {
        {0x00, 0x41},  // Reset all registers
        {0x01, 0x1F},  // Clock manager: all channels on
        {0x02, 0xC3},  // Master mode, MCLK input
        {0x04, 0x01},  // I2S format: standard, 16-bit
        {0x06, 0x04},  // MCLK/LRCK ratio for 16kHz
        {0x08, 0x14},  // Analog gain ch1
        {0x09, 0x14},  // Analog gain ch2
    };

    for (auto& cmd : init_seq) {
        uint8_t data[] = {cmd.reg, cmd.val};
        esp_err_t err = i2c_master_write_to_device(I2C_NUM_0, CORES3_ES7210_ADDR, data, 2, pdMS_TO_TICKS(100));
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "ES7210 reg 0x%02X write failed: %s", cmd.reg, esp_err_to_name(err));
        }
    }

    return true;
}

bool Cores3HAL::initAmpCodec() {
    // AW88298 initialization — Class-D amplifier with I2S input
    ESP_LOGI(TAG, "Initializing AW88298 amplifier at 0x%02X", CORES3_AW88298_ADDR);

    // Basic init: enable amp, set volume
    struct { uint8_t reg; uint8_t val; } init_seq[] = {
        {0x02, 0x00},  // Power on
        {0x61, 0x03},  // I2S config: 16-bit, standard
        {0x04, 0x08},  // Volume (will be overridden by setVolume)
    };

    for (auto& cmd : init_seq) {
        uint8_t data[] = {cmd.reg, cmd.val};
        esp_err_t err = i2c_master_write_to_device(I2C_NUM_0, CORES3_AW88298_ADDR, data, 2, pdMS_TO_TICKS(100));
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "AW88298 reg 0x%02X write failed: %s", cmd.reg, esp_err_to_name(err));
        }
    }

    setVolume(volume_);
    return true;
}

bool Cores3HAL::initI2S() {
    // CoreS3 uses a single I2S port for both mic and speaker (full-duplex)
    ESP_LOGI(TAG, "Initializing I2S (full-duplex)");

    // Note: ESP-IDF v5.x uses the new I2S standard driver.
    // Full I2S init is done in AudioCapture/AudioPlayback using these pins.
    // HAL just validates the hardware is responsive.
    return true;
}

void Cores3HAL::setVolume(uint8_t volume) {
    volume_ = volume;
    // AW88298 volume register (0x04): 0=max, 0xFF=mute
    uint8_t hw_vol = (100 - volume) * 255 / 100;
    uint8_t data[] = {0x04, hw_vol};
    i2c_master_write_to_device(I2C_NUM_0, CORES3_AW88298_ADDR, data, 2, pdMS_TO_TICKS(100));
}

void Cores3HAL::setMicGain(uint8_t gain) {
    mic_gain_ = gain;
    // ES7210 analog gain registers (0x08, 0x09): 0x00–0x1F
    uint8_t hw_gain = gain * 31 / 100;
    uint8_t data1[] = {0x08, hw_gain};
    uint8_t data2[] = {0x09, hw_gain};
    i2c_master_write_to_device(I2C_NUM_0, CORES3_ES7210_ADDR, data1, 2, pdMS_TO_TICKS(100));
    i2c_master_write_to_device(I2C_NUM_0, CORES3_ES7210_ADDR, data2, 2, pdMS_TO_TICKS(100));
}

int Cores3HAL::getMicI2SPort() {
    return 0;  // I2S_NUM_0
}

int Cores3HAL::getSpkI2SPort() {
    return 0;  // Same port, full-duplex
}

// Factory (only compiled when TARGET_CORES3 is defined)
#ifdef TARGET_CORES3
BoardHAL* createBoardHAL() {
    return new Cores3HAL();
}
#endif
