#pragma once

#include <cstdint>
#include <cstddef>
#include "freertos/FreeRTOS.h"

// Minimal esp_websocket_client types for native compilation of WsClient.h

typedef void* esp_websocket_client_handle_t;
typedef const char* esp_event_base_t;

// WebSocket event data — the struct WsClient::handleData receives
typedef struct {
    const char* data_ptr;
    int data_len;
    int payload_len;
    int payload_offset;
    uint8_t op_code;  // 0x01 = text, 0x02 = binary
} esp_websocket_event_data_t;

// Event IDs
#define WEBSOCKET_EVENT_ANY       -1
#define WEBSOCKET_EVENT_CONNECTED  0
#define WEBSOCKET_EVENT_DISCONNECTED 1
#define WEBSOCKET_EVENT_DATA       2
#define WEBSOCKET_EVENT_ERROR      3
#define WEBSOCKET_EVENT_CLOSED     4

// Client config (subset used by WsClient::connect)
typedef struct {
    const char* uri;
    int buffer_size;
    int task_stack;
    int task_prio;
    int ping_interval_sec;
    int network_timeout_ms;
    int pingpong_timeout_sec;
    bool disable_pingpong_discon;
    int reconnect_timeout_ms;
    bool enable_close_reconnect;
} esp_websocket_client_config_t;

// Function declarations (stubs)
typedef void (*esp_event_handler_t)(void* arg, esp_event_base_t base, int32_t id, void* data);

esp_websocket_client_handle_t esp_websocket_client_init(const esp_websocket_client_config_t* config);
int esp_websocket_register_events(esp_websocket_client_handle_t client, int32_t event, esp_event_handler_t handler, void* arg);
int esp_websocket_client_start(esp_websocket_client_handle_t client);
int esp_websocket_client_send_bin(esp_websocket_client_handle_t client, const char* data, int len, TickType_t timeout);
int esp_websocket_client_send_text(esp_websocket_client_handle_t client, const char* data, int len, TickType_t timeout);
void esp_websocket_client_close(esp_websocket_client_handle_t client, TickType_t timeout);
void esp_websocket_client_destroy(esp_websocket_client_handle_t client);
