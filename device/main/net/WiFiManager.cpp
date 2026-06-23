#include "WiFiManager.h"
#include "config.h"

#include "esp_log.h"
#include "esp_netif.h"
#include "nvs_flash.h"
#include <cstring>

static const char* TAG = "WiFiManager";

bool WiFiManager::init(const char* ssid, const char* password) {
    // Initialize NVS (required by WiFi)
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        ret = nvs_flash_init();
    }
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "NVS init failed: %s", esp_err_to_name(ret));
        return false;
    }

    // Initialize TCP/IP and event loop
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    // WiFi driver init with default config
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    // Register event handlers
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, &WiFiManager::eventHandler, this, nullptr));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT, IP_EVENT_STA_GOT_IP, &WiFiManager::eventHandler, this, nullptr));

    // Configure STA
    wifi_config_t wifi_config = {};
    strncpy((char*)wifi_config.sta.ssid, ssid, sizeof(wifi_config.sta.ssid) - 1);
    strncpy((char*)wifi_config.sta.password, password, sizeof(wifi_config.sta.password) - 1);
    wifi_config.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG, "WiFi initialized, SSID: %s", ssid);
    return true;
}

void WiFiManager::connect() {
    retry_count_ = 0;
    esp_wifi_connect();
}

void WiFiManager::disconnect() {
    connected_ = false;
    esp_wifi_disconnect();
    esp_wifi_stop();
}

void WiFiManager::eventHandler(void* arg, esp_event_base_t base, int32_t id, void* data) {
    auto* self = static_cast<WiFiManager*>(arg);

    if (base == WIFI_EVENT) {
        if (id == WIFI_EVENT_STA_START) {
            ESP_LOGI(TAG, "WiFi STA started, connecting...");
            esp_wifi_connect();
        } else if (id == WIFI_EVENT_STA_DISCONNECTED) {
            self->connected_ = false;
            if (self->on_disconnected_) {
                self->on_disconnected_();
            }

            if (self->retry_count_ < CONFIG_WIFI_RETRY_MAX) {
                self->retry_count_++;
                ESP_LOGW(TAG, "Disconnected, retry %d/%d", self->retry_count_, CONFIG_WIFI_RETRY_MAX);
                vTaskDelay(pdMS_TO_TICKS(1000));
                esp_wifi_connect();
            } else {
                ESP_LOGE(TAG, "Max retries reached, giving up");
            }
        }
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        auto* event = static_cast<ip_event_got_ip_t*>(data);
        ESP_LOGI(TAG, "Connected, IP: " IPSTR, IP2STR(&event->ip_info.ip));
        self->connected_ = true;
        self->retry_count_ = 0;
        if (self->on_connected_) {
            self->on_connected_();
        }
    }
}
