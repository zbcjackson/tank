// In-memory NVS fake for native tests.
// Backs nvs_open/get_*/set_*/commit/erase_all with std::unordered_map.

#include "nvs.h"
#include "nvs_flash.h"
#include "nvs_stubs.h"

#include <unordered_map>
#include <string>
#include <vector>
#include <cstring>

static std::unordered_map<std::string, std::vector<uint8_t>> nvs_store;
static uint32_t next_handle = 1;

void nvs_stub_reset() {
    nvs_store.clear();
    next_handle = 1;
}

esp_err_t nvs_flash_init() {
    return ESP_OK;
}

esp_err_t nvs_open(const char* /*namespace_name*/, nvs_open_mode_t /*open_mode*/, nvs_handle_t* out_handle) {
    *out_handle = next_handle++;
    return ESP_OK;
}

esp_err_t nvs_get_u8(nvs_handle_t /*handle*/, const char* key, uint8_t* out_value) {
    auto it = nvs_store.find(key);
    if (it == nvs_store.end() || it->second.size() != 1) {
        return ESP_ERR_NVS_NOT_FOUND;
    }
    *out_value = it->second[0];
    return ESP_OK;
}

esp_err_t nvs_set_u8(nvs_handle_t /*handle*/, const char* key, uint8_t value) {
    nvs_store[key] = {value};
    return ESP_OK;
}

esp_err_t nvs_get_u16(nvs_handle_t /*handle*/, const char* key, uint16_t* out_value) {
    auto it = nvs_store.find(key);
    if (it == nvs_store.end() || it->second.size() != 2) {
        return ESP_ERR_NVS_NOT_FOUND;
    }
    memcpy(out_value, it->second.data(), 2);
    return ESP_OK;
}

esp_err_t nvs_set_u16(nvs_handle_t /*handle*/, const char* key, uint16_t value) {
    std::vector<uint8_t> buf(2);
    memcpy(buf.data(), &value, 2);
    nvs_store[key] = buf;
    return ESP_OK;
}

esp_err_t nvs_get_str(nvs_handle_t /*handle*/, const char* key, char* out_value, size_t* length) {
    auto it = nvs_store.find(key);
    if (it == nvs_store.end()) {
        return ESP_ERR_NVS_NOT_FOUND;
    }

    size_t stored_len = it->second.size();  // includes null terminator

    if (out_value == nullptr) {
        // Query length only
        *length = stored_len;
        return ESP_OK;
    }

    if (*length < stored_len) {
        *length = stored_len;
        return ESP_ERR_NVS_NOT_FOUND;  // buffer too small
    }

    memcpy(out_value, it->second.data(), stored_len);
    *length = stored_len;
    return ESP_OK;
}

esp_err_t nvs_set_str(nvs_handle_t /*handle*/, const char* key, const char* value) {
    size_t len = strlen(value) + 1;  // include null terminator
    nvs_store[key] = std::vector<uint8_t>(value, value + len);
    return ESP_OK;
}

esp_err_t nvs_commit(nvs_handle_t /*handle*/) {
    return ESP_OK;
}

esp_err_t nvs_erase_all(nvs_handle_t /*handle*/) {
    nvs_store.clear();
    return ESP_OK;
}
