#include "WsClient.h"
#include "config.h"

#include "esp_log.h"
#include "cJSON.h"
#include <cstring>
#include <cstdio>

static const char* TAG = "WsClient";

bool WsClient::init(const char* host, int port, const char* session_id) {
    snprintf(uri_, sizeof(uri_), "ws://%s:%d/ws/%s?output_rate=%d",
             host, port, session_id, CONFIG_SPK_SAMPLE_RATE);
    ESP_LOGI(TAG, "WebSocket URI: %s", uri_);
    return true;
}

bool WsClient::connect() {
    esp_websocket_client_config_t config = {};
    config.uri = uri_;
    config.buffer_size = CONFIG_TANK_WS_BUFFER_SIZE;
    config.task_stack = CONFIG_NET_TASK_STACK;
    config.task_prio = CONFIG_NET_TASK_PRIORITY;
    config.ping_interval_sec = 10;
    config.network_timeout_ms = CONFIG_WS_NETWORK_TIMEOUT_MS;
    config.pingpong_timeout_sec = CONFIG_WS_PINGPONG_TIMEOUT_S;
    // Don't drop the link if a single PONG is late — the backend can be busy
    // streaming audio. Liveness is still bounded by network_timeout_ms.
    config.disable_pingpong_discon = true;
    config.reconnect_timeout_ms = CONFIG_WS_RECONNECT_MS;
    config.enable_close_reconnect = true;

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

bool WsClient::reconfigure(const char* host, int port, const char* session_id) {
    ESP_LOGI(TAG, "Reconfiguring WebSocket: %s:%d", host, port);

    // Disconnect existing connection
    disconnect();

    // Rebuild URI
    snprintf(uri_, sizeof(uri_), "ws://%s:%d/ws/%s?output_rate=%d",
             host, port, session_id, CONFIG_SPK_SAMPLE_RATE);
    ESP_LOGI(TAG, "New WebSocket URI: %s", uri_);

    // Reconnect
    return connect();
}

bool WsClient::sendAudio(const int16_t* pcm, size_t samples) {
    if (!connected_ || !client_) return false;

    int len = samples * sizeof(int16_t);
    int sent = esp_websocket_client_send_bin(client_, (const char*)pcm, len, pdMS_TO_TICKS(1000));
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

bool WsClient::sendEndOfUtterance() {
    return sendJson("signal", "end_of_utterance");
}

void WsClient::eventHandler(void* arg, esp_event_base_t base, int32_t id, void* data) {
    auto* self = static_cast<WsClient*>(arg);
    auto* event_data = static_cast<esp_websocket_event_data_t*>(data);

    switch (id) {
        case WEBSOCKET_EVENT_CONNECTED:
            ESP_LOGI(TAG, "WebSocket connected");
            self->connected_ = true;
            if (self->on_connected_) {
                self->on_connected_();
            }
            break;

        case WEBSOCKET_EVENT_DISCONNECTED:
            ESP_LOGW(TAG, "WebSocket disconnected");
            self->connected_ = false;
            if (self->on_disconnected_) {
                self->on_disconnected_();
            }
            break;

        case WEBSOCKET_EVENT_CLOSED:
            ESP_LOGW(TAG, "WebSocket closed by server");
            self->connected_ = false;
            if (self->on_disconnected_) {
                self->on_disconnected_();
            }
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
    // esp_websocket_client delivers payloads exceeding buffer_size in multiple
    // WEBSOCKET_EVENT_DATA callbacks. Each has:
    //   payload_len    = total frame payload length
    //   payload_offset = byte offset of this chunk within the payload
    //   data_len       = bytes in this chunk
    // We must reassemble before parsing.

    const int total = event_data->payload_len;
    const int offset = event_data->payload_offset;
    const int chunk_len = event_data->data_len;

    // Single-event frame (common case: payload fits in buffer) — parse directly.
    if (offset == 0 && chunk_len == total) {
        if (event_data->op_code == 0x02) {
            parseAudioFrame((const uint8_t*)event_data->data_ptr, chunk_len);
        } else if (event_data->op_code == 0x01) {
            parseJsonMessage(event_data->data_ptr, chunk_len);
        }
        return;
    }

    // Multi-event (fragmented) frame — accumulate into reassembly buffer.
    if (offset == 0) {
        // First fragment: allocate buffer for the full payload.
        free(frag_buf_);
        frag_buf_ = (uint8_t*)malloc(total);
        frag_len_ = total;
        frag_pos_ = 0;
        if (!frag_buf_) {
            ESP_LOGE(TAG, "Failed to alloc %d bytes for fragmented frame", total);
            frag_len_ = 0;
            return;
        }
    }

    if (!frag_buf_ || offset != frag_pos_) {
        // Out-of-order or missing first fragment — discard.
        ESP_LOGW(TAG, "Fragment out of order: offset=%d expected=%d", offset, frag_pos_);
        free(frag_buf_);
        frag_buf_ = nullptr;
        frag_len_ = 0;
        frag_pos_ = 0;
        return;
    }

    // Copy this chunk into the reassembly buffer.
    int copy_len = chunk_len;
    if (frag_pos_ + copy_len > frag_len_) {
        copy_len = frag_len_ - frag_pos_;
    }
    memcpy(frag_buf_ + frag_pos_, event_data->data_ptr, copy_len);
    frag_pos_ += copy_len;

    // Final fragment: parse the complete reassembled payload.
    if (frag_pos_ >= frag_len_) {
        if (event_data->op_code == 0x02) {
            parseAudioFrame(frag_buf_, frag_len_);
        } else if (event_data->op_code == 0x01) {
            parseJsonMessage((const char*)frag_buf_, frag_len_);
        }
        free(frag_buf_);
        frag_buf_ = nullptr;
        frag_len_ = 0;
        frag_pos_ = 0;
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
