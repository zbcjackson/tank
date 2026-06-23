#include "WsClient.h"
#include "config.h"

#include "esp_log.h"
#include "cJSON.h"
#include <cstring>
#include <cstdio>

static const char* TAG = "WsClient";

bool WsClient::init(const char* host, int port, const char* session_id) {
    snprintf(uri_, sizeof(uri_), "ws://%s:%d/ws/%s", host, port, session_id);
    ESP_LOGI(TAG, "WebSocket URI: %s", uri_);
    return true;
}

bool WsClient::connect() {
    esp_websocket_client_config_t config = {};
    config.uri = uri_;
    config.buffer_size = 4096;
    config.task_stack = CONFIG_NET_TASK_STACK;
    config.task_prio = CONFIG_NET_TASK_PRIORITY;
    config.ping_interval_sec = 10;
    config.reconnect_timeout_ms = CONFIG_WS_RECONNECT_MS;

    client_ = esp_websocket_client_init(&config);
    if (!client_) {
        ESP_LOGE(TAG, "Failed to init WebSocket client");
        return false;
    }

    // Register event handler
    esp_websocket_register_events(client_, WEBSOCKET_EVENT_ANY, &WsClient::eventHandler, this);

    esp_err_t err = esp_websocket_client_start(client_);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start WebSocket: %s", esp_err_to_name(err));
        return false;
    }

    ESP_LOGI(TAG, "WebSocket connecting...");
    return true;
}

void WsClient::disconnect() {
    if (client_) {
        esp_websocket_client_close(client_, pdMS_TO_TICKS(2000));
        esp_websocket_client_destroy(client_);
        client_ = nullptr;
    }
    connected_ = false;
}

bool WsClient::sendAudio(const int16_t* pcm, size_t samples) {
    if (!connected_ || !client_) return false;

    int len = samples * sizeof(int16_t);
    int sent = esp_websocket_client_send_bin(client_, (const char*)pcm, len, pdMS_TO_TICKS(100));
    return sent == len;
}

bool WsClient::sendJson(const char* type, const char* content) {
    if (!connected_ || !client_) return false;

    cJSON* root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "type", type);
    cJSON_AddStringToObject(root, "content", content);

    char* json_str = cJSON_PrintUnformatted(root);
    int len = strlen(json_str);
    int sent = esp_websocket_client_send_text(client_, json_str, len, pdMS_TO_TICKS(100));

    cJSON_free(json_str);
    cJSON_Delete(root);
    return sent == len;
}

bool WsClient::sendInterrupt() {
    return sendJson("signal", "interrupt");
}

void WsClient::eventHandler(void* arg, esp_event_base_t base, int32_t id, void* data) {
    auto* self = static_cast<WsClient*>(arg);
    auto* event_data = static_cast<esp_websocket_event_data_t*>(data);

    switch (id) {
        case WEBSOCKET_EVENT_CONNECTED:
            ESP_LOGI(TAG, "WebSocket connected");
            self->connected_ = true;
            break;

        case WEBSOCKET_EVENT_DISCONNECTED:
            ESP_LOGW(TAG, "WebSocket disconnected");
            self->connected_ = false;
            break;

        case WEBSOCKET_EVENT_DATA:
            self->handleData(event_data);
            break;

        case WEBSOCKET_EVENT_ERROR:
            ESP_LOGE(TAG, "WebSocket error");
            break;

        default:
            break;
    }
}

void WsClient::handleData(esp_websocket_event_data_t* event_data) {
    if (event_data->op_code == 0x02) {
        // Binary frame — audio data
        parseAudioFrame((const uint8_t*)event_data->data_ptr, event_data->data_len);
    } else if (event_data->op_code == 0x01) {
        // Text frame — JSON message
        parseJsonMessage(event_data->data_ptr, event_data->data_len);
    }
}

void WsClient::parseAudioFrame(const uint8_t* data, int len) {
    if (len < AUDIO_FRAME_HEADER_SIZE) {
        ESP_LOGW(TAG, "Audio frame too short: %d bytes", len);
        return;
    }

    // Parse header: magic(2) + sample_rate(4) + channels(2), little-endian
    uint16_t magic = data[0] | (data[1] << 8);
    if (magic != AUDIO_FRAME_MAGIC) {
        ESP_LOGW(TAG, "Invalid audio magic: 0x%04X", magic);
        return;
    }

    uint32_t sample_rate = data[2] | (data[3] << 8) | (data[4] << 16) | (data[5] << 24);
    // uint16_t channels = data[6] | (data[7] << 8);  // Currently always 1

    const int16_t* pcm = (const int16_t*)(data + AUDIO_FRAME_HEADER_SIZE);
    size_t pcm_bytes = len - AUDIO_FRAME_HEADER_SIZE;
    size_t samples = pcm_bytes / sizeof(int16_t);

    if (on_audio_) {
        on_audio_(pcm, samples, sample_rate);
    }
}

void WsClient::parseJsonMessage(const char* data, int len) {
    // Null-terminate for cJSON (data may not be terminated)
    char* buf = (char*)malloc(len + 1);
    if (!buf) return;
    memcpy(buf, data, len);
    buf[len] = '\0';

    cJSON* root = cJSON_Parse(buf);
    if (!root) {
        ESP_LOGW(TAG, "JSON parse failed: %.*s", len > 100 ? 100 : len, buf);
        free(buf);
        return;
    }

    WsMessage msg = {};

    cJSON* type = cJSON_GetObjectItem(root, "type");
    if (type && cJSON_IsString(type)) {
        strncpy(msg.type, type->valuestring, sizeof(msg.type) - 1);
    }

    cJSON* content = cJSON_GetObjectItem(root, "content");
    if (content && cJSON_IsString(content)) {
        strncpy(msg.content, content->valuestring, sizeof(msg.content) - 1);
    }

    cJSON* msg_id = cJSON_GetObjectItem(root, "msg_id");
    if (msg_id && cJSON_IsString(msg_id)) {
        strncpy(msg.msg_id, msg_id->valuestring, sizeof(msg.msg_id) - 1);
    }

    cJSON* is_user = cJSON_GetObjectItem(root, "is_user");
    msg.is_user = is_user && cJSON_IsTrue(is_user);

    cJSON* is_final = cJSON_GetObjectItem(root, "is_final");
    msg.is_final = is_final && cJSON_IsTrue(is_final);

    if (on_message_) {
        on_message_(msg);
    }

    cJSON_Delete(root);
    free(buf);
}
