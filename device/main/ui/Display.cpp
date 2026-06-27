#include "Display.h"
#include "esp_log.h"

#if defined(TARGET_CORES3)
#include "Cores3Display.h"
#endif

// Serial stub — logs to console. Used when no board display is available.

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

// Factory — board-specific display, falling back to the serial stub.
Display* createDisplay() {
#if defined(TARGET_CORES3)
    return new Cores3Display();
#else
    return new SerialDisplay();
#endif
}
