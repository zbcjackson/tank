#pragma once

#include "Display.h"
#include <cstdint>

/// Pyramid display — 0.85" 128×128 LCD on AtomS3R + 28 WS2812 LED ring.
/// Small screen shows minimal status; LED ring provides visual feedback.
class PyramidDisplay : public Display {
public:
    bool init() override;
    void showStatus(const char* status) override;
    void showUserText(const char* text) override;
    void showAssistantText(const char* text) override;
    void showThinking(bool active) override;
    void showError(const char* error) override;
    void clear() override;

    /// Set LED ring pattern.
    enum class LedPattern {
        OFF,
        IDLE,       // Soft blue pulse
        LISTENING,  // Green ring
        THINKING,   // Yellow chase
        SPEAKING,   // Blue wave
        ERROR,      // Red flash
    };
    void setLedPattern(LedPattern pattern);

private:
    bool initLCD();
    bool initLEDs();

    LedPattern current_pattern_ = LedPattern::OFF;

    static constexpr int SCREEN_W = 128;
    static constexpr int SCREEN_H = 128;
    static constexpr int LED_COUNT = 28;
};
