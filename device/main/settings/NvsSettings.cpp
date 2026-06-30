#include "NvsSettings.h"
#include "config.h"
#include "esp_log.h"
#include "esp_system.h"
#include <cstring>

static const char* TAG = "NvsSettings";
static const char* NVS_NAMESPACE = "tank_cfg";

bool NvsSettings::init() {
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &handle_);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "NVS open failed: %s", esp_err_to_name(err));
        return false;
    }
    opened_ = true;
    ESP_LOGI(TAG, "NVS settings initialized");
    return true;
}

uint8_t NvsSettings::getVolume() {
    if (!opened_) return 70;
    uint8_t val = 70;
    nvs_get_u8(handle_, "vol", &val);
    return val;
}

void NvsSettings::setVolume(uint8_t vol) {
    if (!opened_) return;
    nvs_set_u8(handle_, "vol", vol);
    nvs_commit(handle_);
}

bool NvsSettings::getWifiSSID(char* buf, size_t len) {
    if (!opened_) return false;
    size_t required = len;
    esp_err_t err = nvs_get_str(handle_, "ssid", buf, &required);
    return err == ESP_OK;
}

void NvsSettings::setWifiSSID(const char* ssid) {
    if (!opened_) return;
    nvs_set_str(handle_, "ssid", ssid);
    nvs_commit(handle_);
}

bool NvsSettings::getWifiPassword(char* buf, size_t len) {
    if (!opened_) return false;
    size_t required = len;
    esp_err_t err = nvs_get_str(handle_, "pass", buf, &required);
    return err == ESP_OK;
}

void NvsSettings::setWifiPassword(const char* pass) {
    if (!opened_) return;
    nvs_set_str(handle_, "pass", pass);
    nvs_commit(handle_);
}

bool NvsSettings::getBackendHost(char* buf, size_t len) {
    if (!opened_) return false;
    size_t required = len;
    esp_err_t err = nvs_get_str(handle_, "host", buf, &required);
    return err == ESP_OK;
}

void NvsSettings::setBackendHost(const char* host) {
    if (!opened_) return;
    nvs_set_str(handle_, "host", host);
    nvs_commit(handle_);
}

uint16_t NvsSettings::getBackendPort() {
    if (!opened_) return CONFIG_BACKEND_PORT;
    uint16_t val = CONFIG_BACKEND_PORT;
    nvs_get_u16(handle_, "port", &val);
    return val;
}

void NvsSettings::setBackendPort(uint16_t port) {
    if (!opened_) return;
    nvs_set_u16(handle_, "port", port);
    nvs_commit(handle_);
}

bool NvsSettings::hasNetworkConfig() {
    if (!opened_) return false;
    // Check if SSID is stored (minimum requirement)
    size_t len = 0;
    esp_err_t err = nvs_get_str(handle_, "ssid", nullptr, &len);
    return err == ESP_OK && len > 1;  // len includes null terminator
}

void NvsSettings::factoryReset() {
    if (opened_) {
        nvs_erase_all(handle_);
        nvs_commit(handle_);
    }
    ESP_LOGW(TAG, "Factory reset — rebooting");
    esp_restart();
}
