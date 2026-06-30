#include "SerialConfig.h"
#include "net/WiFiManager.h"
#include "net/WsClient.h"
#include "config.h"

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <cstring>
#include <cstdio>
#include <cstdlib>

static const char* TAG = "SerialConfig";

void SerialConfig::init(NvsSettings* nvs, WiFiManager* wifi, WsClient* ws) {
    nvs_ = nvs;
    wifi_ = wifi;
    ws_ = ws;
}

void SerialConfig::start() {
    xTaskCreatePinnedToCore(
        task, "serial_cfg",
        4096, this,
        2,  // Low priority
        nullptr,
        CONFIG_UI_TASK_CORE
    );
    ESP_LOGI(TAG, "Serial config task started");
}

void SerialConfig::task(void* arg) {
    auto* self = static_cast<SerialConfig*>(arg);

    char line[256];
    int pos = 0;

    // Read from UART0 (stdin) character by character
    while (true) {
        int c = fgetc(stdin);
        if (c == EOF) {
            vTaskDelay(pdMS_TO_TICKS(50));
            continue;
        }

        if (c == '\n' || c == '\r') {
            if (pos > 0) {
                line[pos] = '\0';
                self->processLine(line);
                pos = 0;
            }
        } else if (pos < (int)sizeof(line) - 1) {
            line[pos++] = (char)c;
        }
    }
}

void SerialConfig::processLine(char* line) {
    // Trim leading/trailing whitespace
    while (*line == ' ') line++;
    size_t len = strlen(line);
    while (len > 0 && (line[len - 1] == ' ' || line[len - 1] == '\r')) {
        line[--len] = '\0';
    }

    if (len == 0) return;

    // Only process AT+ commands
    if (strncmp(line, "AT+", 3) != 0) {
        return;
    }

    const char* cmd = line + 3;

    // AT+INFO
    if (strcmp(cmd, "INFO") == 0) {
        printInfo();
        return;
    }

    // AT+SAVE
    if (strcmp(cmd, "SAVE") == 0) {
        printf("OK: Settings saved. Rebooting to apply...\n");
        ESP_LOGI(TAG, "AT+SAVE — rebooting");
        vTaskDelay(pdMS_TO_TICKS(500));
        esp_restart();
        return;
    }

    // AT+RESET
    if (strcmp(cmd, "RESET") == 0) {
        printf("OK: Factory reset...\n");
        if (nvs_) {
            nvs_->factoryReset();  // This reboots
        }
        return;
    }

    // Commands with = value
    const char* eq = strchr(cmd, '=');
    if (!eq) {
        printf("ERROR: Unknown command: %s\n", line);
        return;
    }

    // Extract key and value
    size_t key_len = eq - cmd;
    const char* value = eq + 1;

    if (key_len == 4 && strncmp(cmd, "SSID", 4) == 0) {
        if (nvs_) nvs_->setWifiSSID(value);
        printf("OK: SSID=%s\n", value);
    } else if (key_len == 4 && strncmp(cmd, "PASS", 4) == 0) {
        if (nvs_) nvs_->setWifiPassword(value);
        printf("OK: PASS=****\n");
    } else if (key_len == 4 && strncmp(cmd, "HOST", 4) == 0) {
        if (nvs_) nvs_->setBackendHost(value);
        printf("OK: HOST=%s\n", value);
    } else if (key_len == 4 && strncmp(cmd, "PORT", 4) == 0) {
        uint16_t port = (uint16_t)atoi(value);
        if (port > 0) {
            if (nvs_) nvs_->setBackendPort(port);
            printf("OK: PORT=%d\n", port);
        } else {
            printf("ERROR: Invalid port: %s\n", value);
        }
    } else {
        printf("ERROR: Unknown key: %.*s\n", (int)key_len, cmd);
    }
}

void SerialConfig::printInfo() {
    printf("\n=== Tank Device Configuration ===\n");

    if (!nvs_) {
        printf("  (NVS not initialized)\n");
        printf("=================================\n\n");
        return;
    }

    char buf[128];

    if (nvs_->getWifiSSID(buf, sizeof(buf))) {
        printf("  SSID: %s\n", buf);
    } else {
        printf("  SSID: (default: %s)\n", CONFIG_WIFI_SSID);
    }

    printf("  PASS: ****\n");

    if (nvs_->getBackendHost(buf, sizeof(buf))) {
        printf("  HOST: %s\n", buf);
    } else {
        printf("  HOST: (default: %s)\n", CONFIG_BACKEND_HOST);
    }

    printf("  PORT: %d\n", nvs_->getBackendPort());
    printf("  VOL:  %d%%\n", nvs_->getVolume());
    printf("=================================\n\n");
}
