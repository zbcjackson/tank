#pragma once

#include "nvs_flash.h"
#include "nvs.h"
#include <cstdint>
#include <cstddef>

/// NVS-backed persistent settings for the device.
/// Stores volume, WiFi credentials, and backend host/port.
class NvsSettings {
public:
    /// Open NVS namespace "tank_cfg". Call after nvs_flash_init().
    bool init();

    /// Volume (0–100). Default: 70.
    uint8_t getVolume();
    void setVolume(uint8_t vol);

    /// WiFi SSID. Returns false if not stored.
    bool getWifiSSID(char* buf, size_t len);
    void setWifiSSID(const char* ssid);

    /// WiFi password. Returns false if not stored.
    bool getWifiPassword(char* buf, size_t len);
    void setWifiPassword(const char* pass);

    /// Backend host. Returns false if not stored.
    bool getBackendHost(char* buf, size_t len);
    void setBackendHost(const char* host);

    /// Backend port. Default: CONFIG_BACKEND_PORT.
    uint16_t getBackendPort();
    void setBackendPort(uint16_t port);

    /// Returns true if NVS has saved WiFi credentials.
    bool hasNetworkConfig();

    /// Erase all settings and reboot.
    void factoryReset();

private:
    nvs_handle_t handle_ = 0;
    bool opened_ = false;
};
