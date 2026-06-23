#pragma once

#include "Display.h"
#include <cstdint>

/// CoreS3 display implementation — 320×240 IPS LCD with capacitive touch.
/// Uses direct SPI writes via ESP-IDF LCD driver (no LVGL for simplicity).
class Cores3Display : public Display {
public:
    bool init() override;
    void showStatus(const char* status) override;
    void showUserText(const char* text) override;
    void showAssistantText(const char* text) override;
    void showThinking(bool active) override;
    void showError(const char* error) override;
    void clear() override;

    /// Poll touch input. Call from UI task loop.
    /// Returns true if a touch event was handled.
    bool pollTouch();

    /// Touch action callbacks.
    using ActionCallback = void(*)();
    void onMuteToggle(ActionCallback cb) { on_mute_ = cb; }
    void onInterrupt(ActionCallback cb) { on_interrupt_ = cb; }

private:
    void drawHeader(const char* text, uint16_t color);
    void drawTextArea(const char* text, uint16_t color, int y_offset);
    void drawButton(int x, int y, int w, int h, const char* label, uint16_t color);
    void fillRect(int x, int y, int w, int h, uint16_t color);
    void drawString(int x, int y, const char* text, uint16_t color);

    bool initLCD();
    bool initTouch();

    ActionCallback on_mute_ = nullptr;
    ActionCallback on_interrupt_ = nullptr;

    bool thinking_ = false;
    bool muted_ = false;

    // Touch zones (y-regions for simple layout)
    static constexpr int HEADER_H = 30;
    static constexpr int TEXT_AREA_H = 150;
    static constexpr int BUTTON_AREA_Y = 190;
    static constexpr int BUTTON_H = 40;
    static constexpr int SCREEN_W = 320;
    static constexpr int SCREEN_H = 240;
};
