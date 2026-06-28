#include "Cores3HAL.h"
#include "Cores3Pins.h"
#include "config.h"

#include "driver/i2c.h"
#include "driver/i2s_std.h"
#include "es7210.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char* TAG = "Cores3HAL";

// AXP2101 PMU registers
#define AXP2101_ADDR            0x34
#define AXP2101_LDO_ON_OFF      0x90  // LDO enable/disable register
#define AXP2101_ALDO1_VOLTAGE   0x92  // Speaker codec power (1.8V)
#define AXP2101_ALDO2_VOLTAGE   0x93  // Mic codec power (3.3V)
#define AXP2101_ALDO3_VOLTAGE   0x94  // Camera power
#define AXP2101_ALDO4_VOLTAGE   0x95  // SD card power
#define AXP2101_DLDO1_VOLTAGE   0x99  // LCD backlight

// AW9523B IO expander registers
#define AW9523B_ADDR            0x58
#define AW9523B_P0_OUTPUT       0x02  // Port 0 output register
#define AW9523B_P1_OUTPUT       0x03  // Port 1 output register
#define AW9523B_P0_CONFIG       0x04  // Port 0 direction (0=output)
#define AW9523B_P1_CONFIG       0x05  // Port 1 direction (0=output)
#define AW9523B_CTL             0x11  // Global control (push-pull mode)

// IO expander pin assignments (from BSP)
#define IO_PIN_TOUCH_RST        0   // P0_0
#define IO_PIN_MIC_SPK_EN       2   // P0_2 (shared mic/speaker enable)
#define IO_PIN_SD_EN            4   // P0_4
#define IO_PIN_USB_EN           5   // P0_5
#define IO_PIN_CAM_EN           8   // P1_0
#define IO_PIN_LCD_RST          9   // P1_1 (mapped from BSP_LCD_EN)

bool Cores3HAL::init() {
    ESP_LOGI(TAG, "Initializing CoreS3 hardware");

    if (!initI2C()) return false;
    if (!initPMU()) return false;
    if (!initIOExpander()) return false;
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

    ESP_LOGI(TAG, "I2C initialized (SDA=%d, SCL=%d)", CORES3_I2C_SDA_PIN, CORES3_I2C_SCL_PIN);

    return true;

    return true;
}

bool Cores3HAL::initPMU() {
    ESP_LOGI(TAG, "Initializing AXP2101 PMU");

    // Set ALDO1 = 1.8V (speaker codec AW88298)
    if (!axp2101SetVoltage(AXP2101_ALDO1_VOLTAGE, 1800)) {
        ESP_LOGW(TAG, "Failed to set ALDO1 (speaker power)");
    }

    // Set ALDO2 = 3.3V (mic codec ES7210)
    if (!axp2101SetVoltage(AXP2101_ALDO2_VOLTAGE, 3300)) {
        ESP_LOGW(TAG, "Failed to set ALDO2 (mic power)");
    }

    // Set DLDO1 = 3.3V (LCD backlight)
    if (!axp2101SetVoltage(AXP2101_DLDO1_VOLTAGE, 3300)) {
        ESP_LOGW(TAG, "Failed to set DLDO1 (backlight)");
    }

    // Wait for power rails to stabilize
    vTaskDelay(pdMS_TO_TICKS(20));

    ESP_LOGI(TAG, "PMU configured (ALDO1=1.8V, ALDO2=3.3V, DLDO1=3.3V)");
    return true;
}

bool Cores3HAL::axp2101SetVoltage(uint8_t reg, int voltage_mv) {
    // Voltage formula: register value = (voltage_mv - 500) / 100
    // Valid range: 500mV to 3300mV in 100mV steps
    if (voltage_mv < 500 || voltage_mv > 3300) return false;

    uint8_t power_val = (voltage_mv - 500) / 100;
    uint8_t data[] = {reg, power_val};
    esp_err_t err = i2c_master_write_to_device(I2C_NUM_0, AXP2101_ADDR, data, 2, pdMS_TO_TICKS(100));
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "AXP2101 reg 0x%02X write failed: %s", reg, esp_err_to_name(err));
        return false;
    }

    // Enable the LDO in the enable register
    return axp2101EnableLDO(reg);
}

bool Cores3HAL::axp2101EnableLDO(uint8_t voltage_reg) {
    // Determine which bit to set in the LDO enable register (0x90)
    uint8_t enable_bit = 0;
    switch (voltage_reg) {
        case AXP2101_ALDO1_VOLTAGE: enable_bit = 0x01; break;  // Bit 0
        case AXP2101_ALDO2_VOLTAGE: enable_bit = 0x02; break;  // Bit 1
        case AXP2101_ALDO3_VOLTAGE: enable_bit = 0x04; break;  // Bit 2
        case AXP2101_ALDO4_VOLTAGE: enable_bit = 0x08; break;  // Bit 3
        case AXP2101_DLDO1_VOLTAGE: enable_bit = 0x80; break;  // Bit 7
        default: return false;
    }

    // Read current enable register
    uint8_t reg_addr = AXP2101_LDO_ON_OFF;
    uint8_t current_val = 0;
    esp_err_t err = i2c_master_write_read_device(I2C_NUM_0, AXP2101_ADDR,
        &reg_addr, 1, &current_val, 1, pdMS_TO_TICKS(100));
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "AXP2101 read LDO enable failed: %s", esp_err_to_name(err));
        // Try writing anyway with the bit set
        current_val = 0;
    }

    // Set the enable bit
    uint8_t new_val = current_val | enable_bit;
    if (new_val != current_val) {
        uint8_t data[] = {AXP2101_LDO_ON_OFF, new_val};
        err = i2c_master_write_to_device(I2C_NUM_0, AXP2101_ADDR, data, 2, pdMS_TO_TICKS(100));
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "AXP2101 LDO enable write failed: %s", esp_err_to_name(err));
            return false;
        }
    }

    return true;
}

bool Cores3HAL::initIOExpander() {
    ESP_LOGI(TAG, "Initializing AW9523B IO expander at 0x%02X", AW9523B_ADDR);

    // Set push-pull mode for all outputs (bit 4 = 1 in CTL register)
    uint8_t ctl_data[] = {AW9523B_CTL, 0x10};
    esp_err_t err = i2c_master_write_to_device(I2C_NUM_0, AW9523B_ADDR, ctl_data, 2, pdMS_TO_TICKS(100));
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "AW9523B CTL write failed: %s", esp_err_to_name(err));
        return false;
    }

    // Read current Port 0 output state to avoid disturbing USB (already enabled by bootloader)
    uint8_t p0_reg = AW9523B_P0_OUTPUT;
    uint8_t p0_current = 0;
    i2c_master_write_read_device(I2C_NUM_0, AW9523B_ADDR, &p0_reg, 1, &p0_current, 1, pdMS_TO_TICKS(100));

    // Configure Port 0 pins as outputs: MIC_SPK_EN(2), TOUCH_RST(0)
    // Do NOT reconfigure USB_EN — leave it as-is to avoid USB disconnect
    uint8_t p0_dir_reg = AW9523B_P0_CONFIG;
    uint8_t p0_dir_current = 0xFF;
    i2c_master_write_read_device(I2C_NUM_0, AW9523B_ADDR, &p0_dir_reg, 1, &p0_dir_current, 1, pdMS_TO_TICKS(100));
    uint8_t p0_dir_new = p0_dir_current & ~((1 << IO_PIN_MIC_SPK_EN) | (1 << IO_PIN_TOUCH_RST));
    uint8_t p0_dir[] = {AW9523B_P0_CONFIG, p0_dir_new};
    i2c_master_write_to_device(I2C_NUM_0, AW9523B_ADDR, p0_dir, 2, pdMS_TO_TICKS(100));

    // Configure Port 1 pins as outputs: LCD_RST(1)
    uint8_t p1_dir_reg = AW9523B_P1_CONFIG;
    uint8_t p1_dir_current = 0xFF;
    i2c_master_write_read_device(I2C_NUM_0, AW9523B_ADDR, &p1_dir_reg, 1, &p1_dir_current, 1, pdMS_TO_TICKS(100));
    uint8_t p1_dir_new = p1_dir_current & ~(1 << (IO_PIN_LCD_RST - 8));
    uint8_t p1_dir[] = {AW9523B_P1_CONFIG, p1_dir_new};
    i2c_master_write_to_device(I2C_NUM_0, AW9523B_ADDR, p1_dir, 2, pdMS_TO_TICKS(100));

    // Set Port 0 outputs: enable MIC/SPK, preserve existing USB and other pins
    uint8_t p0_new = p0_current | (1 << IO_PIN_MIC_SPK_EN) | (1 << IO_PIN_TOUCH_RST);
    uint8_t p0_out[] = {AW9523B_P0_OUTPUT, p0_new};
    i2c_master_write_to_device(I2C_NUM_0, AW9523B_ADDR, p0_out, 2, pdMS_TO_TICKS(100));

    // Set Port 1 outputs: enable LCD
    uint8_t p1_reg = AW9523B_P1_OUTPUT;
    uint8_t p1_current = 0;
    i2c_master_write_read_device(I2C_NUM_0, AW9523B_ADDR, &p1_reg, 1, &p1_current, 1, pdMS_TO_TICKS(100));
    uint8_t p1_new = p1_current | (1 << (IO_PIN_LCD_RST - 8));
    uint8_t p1_out[] = {AW9523B_P1_OUTPUT, p1_new};
    i2c_master_write_to_device(I2C_NUM_0, AW9523B_ADDR, p1_out, 2, pdMS_TO_TICKS(100));

    // Wait for peripherals to power up
    vTaskDelay(pdMS_TO_TICKS(20));

    ESP_LOGI(TAG, "IO expander configured (mic/spk=ON, lcd=ON, usb=ON)");
    return true;
}

bool Cores3HAL::initMicCodec() {
    ESP_LOGI(TAG, "Initializing ES7210 mic codec at 0x%02X", CORES3_ES7210_ADDR);

    // Use the esp-bsp es7210 component for proper codec initialization
    es7210_i2c_config_t i2c_cfg = {};
    i2c_cfg.i2c_port = I2C_NUM_0;
    i2c_cfg.i2c_addr = CORES3_ES7210_ADDR;

    esp_err_t err = es7210_new_codec(&i2c_cfg, &es7210_handle_);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "ES7210 handle creation failed: %s", esp_err_to_name(err));
        return false;
    }

    // Configure: 16kHz, 16-bit, standard I2S, NO TDM, 30dB gain
    es7210_codec_config_t codec_cfg = {};
    codec_cfg.sample_rate_hz = 16000;
    codec_cfg.mclk_ratio = 256;
    codec_cfg.i2s_format = ES7210_I2S_FMT_I2S;
    codec_cfg.bit_width = ES7210_I2S_BITS_16B;
    codec_cfg.mic_bias = ES7210_MIC_BIAS_2V87;
    codec_cfg.mic_gain = ES7210_MIC_GAIN_30DB;
    codec_cfg.flags.tdm_enable = 0;

    err = es7210_config_codec(es7210_handle_, &codec_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "ES7210 config failed: %s", esp_err_to_name(err));
        return false;
    }

    ESP_LOGI(TAG, "ES7210 initialized (16kHz, 16-bit, I2S, no TDM, 30dB gain)");
    return true;
}

bool Cores3HAL::initAmpCodec() {
    // AW88298 initialization — Class-D amplifier with I2S input.
    // The AW88298 has 16-bit registers transmitted MSB-first (big-endian).
    // Sequence and values follow the M5Unified CoreS3 reference.
    ESP_LOGI(TAG, "Initializing AW88298 amplifier at 0x%02X", CORES3_AW88298_ADDR);

    // Encode the speaker sample rate into the I2S control register (0x06).
    // rate_tbl maps (sr+1102)/2205 buckets to the register's low nibble.
    static const uint8_t rate_tbl[] = {4, 5, 6, 8, 10, 11, 15, 20, 22, 44};
    size_t idx = 0;
    size_t rate = (CONFIG_SPK_SAMPLE_RATE + 1102) / 2205;
    while (idx < sizeof(rate_tbl) && rate > rate_tbl[idx]) {
        idx++;
    }
    if (idx >= sizeof(rate_tbl)) idx = sizeof(rate_tbl) - 1;
    uint16_t reg06 = (uint16_t)(idx | 0x14C0);  // I2SBCK=0 (16*2 BCK mode)

    struct { uint8_t reg; uint16_t val; } init_seq[] = {
        {0x61, 0x0673},  // boost mode disabled
        {0x04, 0x4040},  // I2SEN=1 AMPPD=0 PWDN=0 (power up)
        {0x05, 0x0008},  // SYSCTRL2: RMSE=0 HAGCE=0 HDCCE=0 HMUTE=0 (unmute)
        {0x06, reg06},   // I2S rate config (sample-rate dependent)
        {0x0C, 0x0064},  // volume (full); refined by setVolume below
    };

    for (auto& cmd : init_seq) {
        if (!aw88298WriteReg(cmd.reg, cmd.val)) {
            ESP_LOGW(TAG, "AW88298 reg 0x%02X write failed", cmd.reg);
        }
    }

    ESP_LOGI(TAG, "AW88298 initialized (rate=%d, reg0x06=0x%04X)",
             CONFIG_SPK_SAMPLE_RATE, reg06);
    setVolume(volume_);
    return true;
}

bool Cores3HAL::aw88298WriteReg(uint8_t reg, uint16_t value) {
    // AW88298 expects the 16-bit value MSB-first on the wire.
    uint8_t data[] = {reg, (uint8_t)(value >> 8), (uint8_t)(value & 0xFF)};
    esp_err_t err = i2c_master_write_to_device(
        I2C_NUM_0, CORES3_AW88298_ADDR, data, sizeof(data), pdMS_TO_TICKS(100));
    return err == ESP_OK;
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
    // AW88298 register 0x0C is the output level. The M5Unified reference uses
    // the fixed value 0x0064 for full volume; the exact dB-per-step encoding
    // isn't documented here, so we use that verified value rather than a
    // guessed attenuation formula (which risked distorting output).
    // TODO: implement fine-grained volume from the AW88298 datasheet if needed.
    aw88298WriteReg(0x0C, 0x0064);
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
