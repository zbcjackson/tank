#pragma once

// Minimal esp_wifi.h compat shim for native tests.
// Only provides types needed by WiFiManager.h to compile.

#include <cstdint>

typedef struct {
    uint8_t ssid[32];
    uint8_t password[64];
} wifi_sta_config_t;

typedef struct {
    wifi_sta_config_t sta;
} wifi_config_t;

typedef enum {
    WIFI_IF_STA = 0,
} wifi_interface_t;
