#include "Display.h"
#include "esp_log.h"

// Stub implementation — logs to serial.
// Will be replaced with LCD driver in Phase 4.

static const char* TAG = "Display";

class SerialDisplay : public Display {
public:
    bool init() override {
        ESP_LOGI(TAG, "Display initialized (serial stub)");
        return true;
    }

    void showStatus(const char* status) override {
        ESP_LOGI(TAG, "[STATUS] %s", status);
    }

    void showUserText(const char* text) override {
        ESP_LOGI(TAG, "[USER] %s", text);
    }

    void showAssistantText(const char* text) override {
        ESP_LOGI(TAG, "[ASSISTANT] %s", text);
    }

    void showThinking(bool active) override {
        if (active) {
            ESP_LOGI(TAG, "[THINKING] ...");
        }
    }

    void showError(const char* error) override {
        ESP_LOGE(TAG, "[ERROR] %s", error);
    }

    void clear() override {
        ESP_LOGI(TAG, "[CLEAR]");
    }
};

// Factory — returns serial stub for now
Display* createDisplay() {
    return new SerialDisplay();
}
