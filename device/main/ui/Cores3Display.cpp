#include "Cores3Display.h"
#include "hal/cores3/Cores3Pins.h"
#include "config.h"

#include "driver/spi_master.h"
#include "driver/i2c.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_vendor.h"
#include "esp_lcd_panel_ops.h"
#include <cstring>
#include <cstdio>

static const char* TAG = "Cores3Display";

// Color constants (RGB565)
static constexpr uint16_t COLOR_BLACK   = 0x0000;
static constexpr uint16_t COLOR_WHITE   = 0xFFFF;
static constexpr uint16_t COLOR_BLUE    = 0x001F;
static constexpr uint16_t COLOR_GREEN   = 0x07E0;
static constexpr uint16_t COLOR_RED     = 0xF800;
static constexpr uint16_t COLOR_GRAY    = 0x7BEF;
static constexpr uint16_t COLOR_DARK_BG = 0x1082;  // Dark gray background
static constexpr uint16_t COLOR_USER    = 0x34DF;  // Light blue
static constexpr uint16_t COLOR_ASSIST  = 0xFFFF;  // White

static esp_lcd_panel_handle_t panel_handle = nullptr;

bool Cores3Display::init() {
    if (!initLCD()) return false;
    if (!initTouch()) return false;

    clear();
    drawHeader("Tank Device", COLOR_WHITE);
    showStatus("Initializing...");
    return true;
}

bool Cores3Display::initLCD() {
    ESP_LOGI(TAG, "Initializing ILI9342C LCD (320x240)");

    // SPI bus for LCD
    spi_bus_config_t bus_cfg = {};
    bus_cfg.mosi_io_num = 37;
    bus_cfg.miso_io_num = -1;
    bus_cfg.sclk_io_num = 36;
    bus_cfg.quadwp_io_num = -1;
    bus_cfg.quadhd_io_num = -1;
    bus_cfg.max_transfer_sz = SCREEN_W * SCREEN_H * 2;

    esp_err_t err = spi_bus_initialize(SPI2_HOST, &bus_cfg, SPI_DMA_CH_AUTO);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "SPI bus init failed: %s", esp_err_to_name(err));
        return false;
    }

    // Panel IO
    esp_lcd_panel_io_handle_t io_handle = nullptr;
    esp_lcd_panel_io_spi_config_t io_config = {};
    io_config.dc_gpio_num = CORES3_LCD_DC_PIN;
    io_config.cs_gpio_num = CORES3_LCD_CS_PIN;
    io_config.pclk_hz = 40 * 1000 * 1000;  // 40 MHz
    io_config.lcd_cmd_bits = 8;
    io_config.lcd_param_bits = 8;
    io_config.spi_mode = 0;
    io_config.trans_queue_depth = 10;

    err = esp_lcd_new_panel_io_spi((esp_lcd_spi_bus_handle_t)SPI2_HOST, &io_config, &io_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "LCD panel IO init failed: %s", esp_err_to_name(err));
        return false;
    }

    // Panel driver
    esp_lcd_panel_dev_config_t panel_config = {};
    panel_config.reset_gpio_num = CORES3_LCD_RST_PIN;
    panel_config.rgb_ele_order = LCD_RGB_ELEMENT_ORDER_BGR;
    panel_config.bits_per_pixel = 16;

    err = esp_lcd_new_panel_st7789(io_handle, &panel_config, &panel_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "LCD panel init failed: %s", esp_err_to_name(err));
        return false;
    }

    esp_lcd_panel_reset(panel_handle);
    esp_lcd_panel_init(panel_handle);
    esp_lcd_panel_disp_on_off(panel_handle, true);

    ESP_LOGI(TAG, "LCD initialized");
    return true;
}

bool Cores3Display::initTouch() {
    // FT6336U touch controller on I2C (already initialized by HAL)
    ESP_LOGI(TAG, "Touch controller at 0x%02X (on shared I2C bus)", CORES3_TOUCH_ADDR);
    return true;
}

void Cores3Display::clear() {
    fillRect(0, 0, SCREEN_W, SCREEN_H, COLOR_DARK_BG);
}

void Cores3Display::showStatus(const char* status) {
    // Status bar below header
    fillRect(0, HEADER_H, SCREEN_W, 20, COLOR_DARK_BG);
    drawString(10, HEADER_H + 4, status, COLOR_GRAY);
}

void Cores3Display::showUserText(const char* text) {
    // User text in the upper portion of text area
    fillRect(0, HEADER_H + 20, SCREEN_W, 50, COLOR_DARK_BG);

    char buf[128];
    snprintf(buf, sizeof(buf), "> %s", text);
    drawString(10, HEADER_H + 24, buf, COLOR_USER);
}

void Cores3Display::showAssistantText(const char* text) {
    // Assistant text in the lower portion of text area
    fillRect(0, HEADER_H + 70, SCREEN_W, TEXT_AREA_H - 70, COLOR_DARK_BG);
    drawString(10, HEADER_H + 74, text, COLOR_ASSIST);
}

void Cores3Display::showThinking(bool active) {
    thinking_ = active;
    if (active) {
        fillRect(0, HEADER_H + 70, SCREEN_W, 20, COLOR_DARK_BG);
        drawString(10, HEADER_H + 74, "Thinking...", COLOR_GRAY);
    }
}

void Cores3Display::showError(const char* error) {
    fillRect(0, HEADER_H + 70, SCREEN_W, 20, COLOR_DARK_BG);
    drawString(10, HEADER_H + 74, error, COLOR_RED);
}

bool Cores3Display::pollTouch() {
    // Read touch data from FT6336U
    uint8_t data[7] = {};
    uint8_t reg = 0x02;  // Touch status register

    esp_err_t err = i2c_master_write_read_device(
        I2C_NUM_0, CORES3_TOUCH_ADDR,
        &reg, 1, data, sizeof(data),
        pdMS_TO_TICKS(10)
    );

    if (err != ESP_OK) return false;

    uint8_t touch_count = data[0] & 0x0F;
    if (touch_count == 0) return false;

    // Parse first touch point
    uint16_t x = ((data[1] & 0x0F) << 8) | data[2];
    uint16_t y = ((data[3] & 0x0F) << 8) | data[4];

    // Check button zones
    if (y >= BUTTON_AREA_Y && y < BUTTON_AREA_Y + BUTTON_H) {
        if (x < SCREEN_W / 2) {
            // Left button: mute toggle
            muted_ = !muted_;
            if (on_mute_) on_mute_();

            // Visual feedback
            uint16_t color = muted_ ? COLOR_RED : COLOR_GREEN;
            const char* label = muted_ ? "MUTED" : "MIC ON";
            drawButton(10, BUTTON_AREA_Y, SCREEN_W / 2 - 20, BUTTON_H, label, color);
            return true;
        } else {
            // Right button: interrupt
            if (on_interrupt_) on_interrupt_();

            // Visual feedback
            drawButton(SCREEN_W / 2 + 10, BUTTON_AREA_Y, SCREEN_W / 2 - 20, BUTTON_H, "STOP", COLOR_RED);
            vTaskDelay(pdMS_TO_TICKS(200));
            drawButton(SCREEN_W / 2 + 10, BUTTON_AREA_Y, SCREEN_W / 2 - 20, BUTTON_H, "INTERRUPT", COLOR_GRAY);
            return true;
        }
    }

    return false;
}

// ─── Drawing primitives ─────────────────────────────────────────────────────

void Cores3Display::drawHeader(const char* text, uint16_t color) {
    fillRect(0, 0, SCREEN_W, HEADER_H, COLOR_BLACK);
    drawString(10, 8, text, color);
}

void Cores3Display::drawButton(int x, int y, int w, int h, const char* label, uint16_t color) {
    fillRect(x, y, w, h, color);
    // Center label (approximate)
    int text_x = x + (w - strlen(label) * 8) / 2;
    int text_y = y + (h - 12) / 2;
    drawString(text_x, text_y, label, COLOR_BLACK);
}

void Cores3Display::fillRect(int x, int y, int w, int h, uint16_t color) {
    if (!panel_handle) return;

    // Allocate buffer for one row and fill repeatedly
    uint16_t* line = (uint16_t*)heap_caps_malloc(w * sizeof(uint16_t), MALLOC_CAP_DMA);
    if (!line) return;

    for (int i = 0; i < w; i++) {
        line[i] = color;
    }

    for (int row = y; row < y + h; row++) {
        esp_lcd_panel_draw_bitmap(panel_handle, x, row, x + w, row + 1, line);
    }

    heap_caps_free(line);
}

void Cores3Display::drawString(int x, int y, const char* text, uint16_t color) {
    // Simple character rendering — placeholder for a proper font engine.
    // In production, use LVGL or a bitmap font library.
    // For now, this logs to serial (the LCD rendering would need a font table).
    ESP_LOGD(TAG, "Draw @(%d,%d): %s", x, y, text);

    // TODO: Implement bitmap font rendering or integrate LVGL.
    // For Phase 4 MVP, the serial stub (Display.cpp) provides the output,
    // and this file provides the framework for real LCD rendering.
    (void)x; (void)y; (void)text; (void)color;
}
