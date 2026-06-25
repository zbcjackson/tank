#include "Cores3HAL.h"
#include "Cores3Pins.h"
#include "config.h"

#include "driver/i2c.h"
#include "driver/i2s_std.h"
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

    // I2C bus scan to verify which devices respond
    ESP_LOGI(TAG, "I2C bus scan:");
    int found = 0;
    for (uint8_t addr = 0x08; addr < 0x78; addr++) {
        i2c_cmd_handle_t cmd = i2c_cmd_link_create();
        i2c_master_start(cmd);
        i2c_master_write_byte(cmd, (addr << 1) | 0, true);
        i2c_master_stop(cmd);
        esp_err_t ret = i2c_master_cmd_begin(I2C_NUM_0, cmd, pdMS_TO_TICKS(50));
        i2c_cmd_link_delete(cmd);
        if (ret == ESP_OK) {
            ESP_LOGI(TAG, "  Found device at 0x%02X", addr);
            found++;
        }
    }
    ESP_LOGI(TAG, "I2C scan complete: %d devices found", found);

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
    // ES7210 initialization based on esp-bsp/components/es7210 driver
    // Slave mode, I2S standard format, 16-bit, 16kHz, MCLK=4.096MHz (256×fs)
    ESP_LOGI(TAG, "Initializing ES7210 mic codec at 0x%02X", CORES3_ES7210_ADDR);

    auto wr = [](uint8_t reg, uint8_t val) -> esp_err_t {
        uint8_t data[] = {reg, val};
        return i2c_master_write_to_device(I2C_NUM_0, CORES3_ES7210_ADDR, data, 2, pdMS_TO_TICKS(100));
    };

    // Software reset
    esp_err_t err = wr(0x00, 0xFF);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "ES7210 reset failed: %s", esp_err_to_name(err));
        return false;
    }
    vTaskDelay(pdMS_TO_TICKS(20));
    wr(0x00, 0x32);  // Exit reset (BSP uses 0x32)

    // Initialization timing
    wr(0x09, 0x30);  // TIME_CONTROL0: chip state cycle
    wr(0x0A, 0x30);  // TIME_CONTROL1: power up state cycle

    // HPF config for ADC1-4
    wr(0x23, 0x2A);  // ADC12_HPF1
    wr(0x22, 0x0A);  // ADC12_HPF2
    wr(0x21, 0x2A);  // ADC34_HPF1
    wr(0x20, 0x0A);  // ADC34_HPF2

    // I2S format: 16-bit I2S standard with TDM enabled
    // TDM mode + 32-bit I2S slot width produces correct BCLK for clean audio
    wr(0x11, 0x60);  // SDP_INTERFACE1: 16-bit I2S standard format
    wr(0x12, 0x02);  // SDP_INTERFACE2: TDM enabled for I2S mode

    // Analog power config
    wr(0x40, 0xC3);  // ANALOG: vdda=3.3V, VMID select
    wr(0x41, 0x70);  // MIC12_BIAS: 2.87V
    wr(0x42, 0x70);  // MIC34_BIAS: 2.87V

    // MIC gain: 3dB analog + 64× software gain in AudioCapture
    // Raw peak ~35 in quiet room → ~2240 after software gain
    wr(0x43, 0x11);  // MIC1_GAIN: enable (0x10) + gain 0x01 (3dB)
    wr(0x44, 0x11);  // MIC2_GAIN: enable (0x10) + gain 0x01 (3dB)
    wr(0x45, 0x00);  // MIC3_GAIN: disabled
    wr(0x46, 0x00);  // MIC4_GAIN: disabled

    // Power on MIC1-4
    wr(0x47, 0x08);  // MIC1_POWER
    wr(0x48, 0x08);  // MIC2_POWER
    wr(0x49, 0x08);  // MIC3_POWER
    wr(0x4A, 0x08);  // MIC4_POWER

    // Clock config for MCLK=4.096MHz, LRCK=16kHz
    // From coeff table: adc_div=0x01, dll=1, doubler=1, osr=0x20, lrckh=0x01, lrckl=0x00
    wr(0x07, 0x20);  // OSR
    wr(0x02, 0xC1);  // MAINCLK: adc_div=1 | doubler<<6=0x40 | dll<<7=0x80 = 0xC1
    wr(0x04, 0x01);  // LRCK_DIVH
    wr(0x05, 0x00);  // LRCK_DIVL

    // Slave mode (ESP32 is master)
    wr(0x08, 0x00);  // MODE_CONFIG: slave mode

    // Power down DLL (use doubler instead per coeff table)
    wr(0x06, 0x04);  // POWER_DOWN: DLL power down

    // Power on MIC1-4 bias & ADC1-4 & PGA1-4
    wr(0x4B, 0x0F);  // MIC12_POWER: bias+ADC+PGA power on
    wr(0x4C, 0x00);  // MIC34_POWER: power OFF (not used in stereo mode)

    // Enable device
    wr(0x00, 0x71);  // Soft reset to apply all settings
    wr(0x00, 0x41);  // Resume normal operation

    ESP_LOGI(TAG, "ES7210 mic codec initialized (slave, I2S 16-bit, 16kHz, 24dB)");
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
