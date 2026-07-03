#pragma once

#include <cstdint>

// ESP-IDF MAC address type enum (subset needed for Session.cpp)
typedef enum {
    ESP_MAC_WIFI_STA = 0,
} esp_mac_type_t;

// Defined in esp_stubs.cpp — returns fixed MAC for deterministic tests.
int esp_read_mac(uint8_t* mac, esp_mac_type_t type);
