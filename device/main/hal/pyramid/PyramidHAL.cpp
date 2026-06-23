#include "PyramidHAL.h"
#include "PyramidPins.h"
#include "config.h"

#include "driver/i2c.h"
#include "esp_log.h"

static const char* TAG = "PyramidHAL";

bool PyramidHAL::init() {
    ESP_LOGI(TAG, "Initializing Pyramid + AtomS3R hardware");

    if (!initI2C()) return false;
    if (!initClock()) return false;
    if (!initMicCodec()) return false;
    if (!initDacCodec()) return false;
    if (!initAmp()) return false;
    if (!initI2S()) return false;

    ESP_LOGI(TAG, "Pyramid hardware initialized");
    return true;
}

bool PyramidHAL::initI2C() {
    i2c_config_t conf = {};
    conf.mode = I2C_MODE_MASTER;
    conf.sda_io_num = PYRAMID_I2C_SDA_PIN;
    conf.scl_io_num = PYRAMID_I2C_SCL_PIN;
    conf.sda_pullup_en = GPIO_PULLUP_ENABLE;
    conf.scl_pullup_en = GPIO_PULLUP_ENABLE;
    conf.master.clk_speed = PYRAMID_I2C_FREQ;

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

bool PyramidHAL::initClock() {
    // Si5351 provides MCLK to both ES7210 and ES8311
    ESP_LOGI(TAG, "Initializing Si5351 clock generator at 0x%02X", PYRAMID_SI5351_ADDR);
    // TODO: Configure Si5351 for appropriate MCLK frequency
    // Typical: 12.288MHz for 16kHz audio (MCLK = 256 * Fs)
    return true;
}

bool PyramidHAL::initMicCodec() {
    ESP_LOGI(TAG, "Initializing ES7210 mic codec at 0x%02X", PYRAMID_ES7210_ADDR);
    // Similar to CoreS3 but may have different register defaults
    // due to Si5351 providing MCLK instead of ESP32-S3 GPIO
    // TODO: Full ES7210 init with Pyramid-specific clock config
    return true;
}

bool PyramidHAL::initDacCodec() {
    ESP_LOGI(TAG, "Initializing ES8311 DAC at 0x%02X", PYRAMID_ES8311_ADDR);
    // ES8311 is a high-performance mono DAC
    // Configure for 24kHz playback to match server output
    // TODO: Full ES8311 init sequence
    return true;
}

bool PyramidHAL::initAmp() {
    ESP_LOGI(TAG, "Initializing AW87559 amplifier at 0x%02X", PYRAMID_AW87559_ADDR);
    // AW87559 Class-D speaker amplifier
    // TODO: Init and volume configuration
    return true;
}

bool PyramidHAL::initI2S() {
    ESP_LOGI(TAG, "Initializing I2S (full-duplex via Atom connector)");
    // I2S pin setup specific to Pyramid wiring
    return true;
}

void PyramidHAL::setVolume(uint8_t volume) {
    volume_ = volume;
    // ES8311 DAC volume + AW87559 amp gain
    // TODO: I2C register writes
}

void PyramidHAL::setMicGain(uint8_t gain) {
    mic_gain_ = gain;
    // ES7210 analog gain
    // TODO: I2C register write
}

int PyramidHAL::getMicI2SPort() {
    return 0;
}

int PyramidHAL::getSpkI2SPort() {
    return 0;  // Same port, full-duplex
}

// Factory (only compiled when TARGET_PYRAMID is defined)
#ifdef TARGET_PYRAMID
BoardHAL* createBoardHAL() {
    return new PyramidHAL();
}
#endif
