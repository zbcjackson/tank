#include "app/Assistant.h"
#include "hal/BoardHAL.h"

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char* TAG = "main";

// Factory defined in HAL compilation unit
extern BoardHAL* createBoardHAL();

extern "C" void app_main(void) {
    ESP_LOGI(TAG, "=== Tank Device Client ===");
    ESP_LOGI(TAG, "Build target: %s",
#if defined(TARGET_CORES3)
        "CoreS3"
#elif defined(TARGET_PYRAMID)
        "Pyramid + AtomS3R"
#else
        "Unknown"
#endif
    );

    // Initialize board hardware (codecs, I2C, pins)
    BoardHAL* hal = createBoardHAL();
    if (!hal->init()) {
        ESP_LOGE(TAG, "Board HAL init failed, halting");
        while (true) { vTaskDelay(pdMS_TO_TICKS(1000)); }
    }

    // Initialize and start the assistant
    static Assistant assistant;
    if (!assistant.init()) {
        ESP_LOGE(TAG, "Assistant init failed, halting");
        while (true) { vTaskDelay(pdMS_TO_TICKS(1000)); }
    }

    assistant.start();

    // Main task done — FreeRTOS tasks handle everything from here
    ESP_LOGI(TAG, "Main task complete, running on FreeRTOS tasks");
}
