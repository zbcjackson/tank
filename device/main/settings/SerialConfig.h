#pragma once

#include "settings/NvsSettings.h"
#include <cstdint>

class WiFiManager;
class WsClient;

/// Serial AT command handler for runtime configuration.
/// Runs a FreeRTOS task reading UART0 line-by-line.
///
/// Supported commands:
///   AT+SSID=<value>   Set WiFi SSID
///   AT+PASS=<value>   Set WiFi password
///   AT+HOST=<value>   Set backend host
///   AT+PORT=<value>   Set backend port
///   AT+SAVE           Save and reconnect
///   AT+INFO           Print current config
///   AT+RESET          Factory reset (erase NVS, reboot)
class SerialConfig {
public:
    /// Set dependencies.
    void init(NvsSettings* nvs, WiFiManager* wifi, WsClient* ws);

    /// Start the serial reader task.
    void start();

private:
    static void task(void* arg);
    void processLine(char* line);
    void printInfo();

    NvsSettings* nvs_ = nullptr;
    WiFiManager* wifi_ = nullptr;
    WsClient* ws_ = nullptr;
};
