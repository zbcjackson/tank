#include "Session.h"

#include "esp_mac.h"
#include "esp_log.h"
#include <cstdio>

static const char* TAG = "Session";

void Session::init() {
    // Generate session ID from device MAC address for consistency across reboots
    uint8_t mac[6];
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    snprintf(session_id_, sizeof(session_id_),
             "device_%02x%02x%02x%02x%02x%02x",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);

    ESP_LOGI(TAG, "Session ID: %s", session_id_);
    state_ = State::IDLE;
}
