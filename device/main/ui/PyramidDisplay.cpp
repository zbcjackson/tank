#include "PyramidDisplay.h"
#include "hal/pyramid/PyramidPins.h"

#include "esp_log.h"
#include <cstring>

static const char* TAG = "PyramidDisplay";

bool PyramidDisplay::init() {
    if (!initLCD()) return false;
    if (!initLEDs()) return false;

    clear();
    setLedPattern(LedPattern::IDLE);
    ESP_LOGI(TAG, "Pyramid display initialized");
    return true;
}

bool PyramidDisplay::initLCD() {
    // AtomS3R has a tiny 0.85" 128×128 LCD
    // TODO: Initialize via SPI (ST7735 or similar driver)
    ESP_LOGI(TAG, "LCD init (128x128) — stub");
    return true;
}

bool PyramidDisplay::initLEDs() {
    // 28× WS2812 RGB LEDs on GPIO
    // TODO: Initialize RMT peripheral for WS2812 protocol
    ESP_LOGI(TAG, "LED ring init (%d LEDs on GPIO %d) — stub", LED_COUNT, PYRAMID_LED_PIN);
    return true;
}

void PyramidDisplay::showStatus(const char* status) {
    ESP_LOGI(TAG, "[STATUS] %s", status);
    // On the tiny screen, show just a 2-3 word status
    // TODO: Render on LCD
}

void PyramidDisplay::showUserText(const char* text) {
    ESP_LOGI(TAG, "[USER] %s", text);
    setLedPattern(LedPattern::LISTENING);
}

void PyramidDisplay::showAssistantText(const char* text) {
    ESP_LOGI(TAG, "[ASSISTANT] %s", text);
    setLedPattern(LedPattern::SPEAKING);
}

void PyramidDisplay::showThinking(bool active) {
    if (active) {
        ESP_LOGI(TAG, "[THINKING]");
        setLedPattern(LedPattern::THINKING);
    } else {
        setLedPattern(LedPattern::IDLE);
    }
}

void PyramidDisplay::showError(const char* error) {
    ESP_LOGE(TAG, "[ERROR] %s", error);
    setLedPattern(LedPattern::ERROR);
}

void PyramidDisplay::clear() {
    setLedPattern(LedPattern::OFF);
    // TODO: Clear LCD
}

void PyramidDisplay::setLedPattern(LedPattern pattern) {
    if (pattern == current_pattern_) return;
    current_pattern_ = pattern;

    // TODO: Implement LED ring patterns via RMT/WS2812 driver
    // Each pattern maps to a color + animation:
    // - IDLE: dim blue, slow pulse
    // - LISTENING: bright green, solid
    // - THINKING: yellow, chase animation
    // - SPEAKING: blue, wave from bottom to top
    // - ERROR: red, fast flash

    const char* names[] = {"OFF", "IDLE", "LISTENING", "THINKING", "SPEAKING", "ERROR"};
    ESP_LOGD(TAG, "LED pattern: %s", names[(int)pattern]);
}
