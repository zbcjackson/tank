#pragma once

#include "esp_wifi.h"
#include "esp_event.h"
#include <functional>

/// WiFi station manager with auto-reconnect.
class WiFiManager {
public:
    using ConnectedCallback = std::function<void()>;
    using DisconnectedCallback = std::function<void()>;

    /// Initialize WiFi in STA mode.
    bool init(const char* ssid, const char* password);

    /// Start connection attempt.
    void connect();

    /// Disconnect and stop WiFi.
    void disconnect();

    /// Reconfigure WiFi with new credentials and reconnect.
    bool reconfigure(const char* ssid, const char* password);

    /// Returns true if connected with IP assigned.
    bool isConnected() const { return connected_; }

    void onConnected(ConnectedCallback cb) { on_connected_ = cb; }
    void onDisconnected(DisconnectedCallback cb) { on_disconnected_ = cb; }

private:
    static void eventHandler(void* arg, esp_event_base_t base, int32_t id, void* data);

    ConnectedCallback on_connected_;
    DisconnectedCallback on_disconnected_;
    bool connected_ = false;
    int retry_count_ = 0;
};
