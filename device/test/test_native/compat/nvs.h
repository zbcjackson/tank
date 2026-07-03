#pragma once

#include "esp_err.h"
#include <cstddef>
#include <cstdint>

typedef uint32_t nvs_handle_t;

typedef enum {
    NVS_READONLY = 0,
    NVS_READWRITE = 1,
} nvs_open_mode_t;

// NVS API subset used by NvsSettings
esp_err_t nvs_open(const char* namespace_name, nvs_open_mode_t open_mode, nvs_handle_t* out_handle);
esp_err_t nvs_get_u8(nvs_handle_t handle, const char* key, uint8_t* out_value);
esp_err_t nvs_set_u8(nvs_handle_t handle, const char* key, uint8_t value);
esp_err_t nvs_get_u16(nvs_handle_t handle, const char* key, uint16_t* out_value);
esp_err_t nvs_set_u16(nvs_handle_t handle, const char* key, uint16_t value);
esp_err_t nvs_get_str(nvs_handle_t handle, const char* key, char* out_value, size_t* length);
esp_err_t nvs_set_str(nvs_handle_t handle, const char* key, const char* value);
esp_err_t nvs_commit(nvs_handle_t handle);
esp_err_t nvs_erase_all(nvs_handle_t handle);
