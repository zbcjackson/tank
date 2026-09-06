#include "WsClient.h"
#include "WsProtocol.h"
#include "config.h"

#include "esp_log.h"
#include "esp_heap_caps.h"
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
    config.task_stack = CONFIG_WS_CLIENT_TASK_STACK;
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
    resetOpus();
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

    if (opus_negotiated_) {
        // One mic frame (20 ms) per call — one packet per WS message, the
        // negotiated wire shape (plan P1-2).
        uint8_t packet[1276];
        int n = opus_encode(opus_enc_, pcm, samples, packet, sizeof(packet));
        if (n <= 0) {
            ESP_LOGW(TAG, "opus_encode failed: %d", n);
            return false;
        }
        int sent = esp_websocket_client_send_bin(client_, (const char*)packet, n,
                                                 pdMS_TO_TICKS(1000));
        return sent == n;
    }

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
            // Fresh connection — renegotiate from scratch (the ready frame
            // re-advertises features on every connect).
            self->opus_declared_ = false;
            self->opus_negotiated_ = false;
            if (self->on_connected_) {
                self->on_connected_();
            }
            break;

        case WEBSOCKET_EVENT_DISCONNECTED:
            ESP_LOGW(TAG, "WebSocket disconnected");
            self->connected_ = false;
            self->resetOpus();
            if (self->on_disconnected_) {
                self->on_disconnected_();
            }
            break;

        case WEBSOCKET_EVENT_CLOSED:
            ESP_LOGW(TAG, "WebSocket closed by server");
            self->connected_ = false;
            self->resetOpus();
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
    if (opus_negotiated_) {
        // One opus packet per WS message. Decoded at the speaker rate — opus
        // packets are rate-agnostic, so no resample is needed downstream.
        int samples = opus_decode(opus_dec_, data, len, opus_dec_pcm_,
                                  sizeof(opus_dec_pcm_) / sizeof(opus_dec_pcm_[0]), 0);
        if (samples <= 0) {
            ESP_LOGW(TAG, "opus_decode failed: %d (packet %d B)", samples, len);
            return;
        }
        if (on_audio_) {
            on_audio_(opus_dec_pcm_, samples, CONFIG_SPK_SAMPLE_RATE);
        }
        return;
    }

    AudioFrameHeader hdr = {};
    if (!parseAudioFrameHeader(data, len, &hdr)) {
        ESP_LOGW(TAG, "Invalid audio frame: len=%d", len);
        return;
    }

    const int16_t* pcm = (const int16_t*)(data + AUDIO_FRAME_HEADER_SIZE);
    size_t pcm_bytes = len - AUDIO_FRAME_HEADER_SIZE;
    size_t samples = pcm_bytes / sizeof(int16_t);

    if (on_audio_) {
        on_audio_(pcm, samples, hdr.sample_rate);
    }
}

void WsClient::parseJsonMessage(const char* data, int len) {
    WsMessage msg = {};
    if (!parseWsJsonMessage(data, len, &msg)) {
        ESP_LOGW(TAG, "JSON parse failed: %.*s", len > 100 ? 100 : len, data);
        return;
    }

    // Opus negotiation (plan P1-2): declare once per connection when ready
    // advertises the feature; switch codecs on the ack. Between the server
    // processing the declaration and the ack arriving, uplink PCM can hit
    // the server's opus decoder and be dropped — the connect-time race the
    // plan accepted (no user speech that early).
    if (strcmp(msg.type, "signal") == 0) {
        if (strcmp(msg.content, "ready") == 0 && msg.protocol_opus_advertised &&
            !opus_declared_ && !opus_negotiated_) {
            if (sendCapabilitiesDeclaration()) {
                opus_declared_ = true;
                ESP_LOGI(TAG, "Declared opus capability");
            }
        } else if (strcmp(msg.content, "capabilities") == 0 &&
                   msg.protocol_opus_enabled && !opus_negotiated_) {
            enableOpus();
        }
    }

    if (on_message_) {
        on_message_(msg);
    }
}

void WsClient::resetOpus() {
    // States are PSRAM-owned (placement-init) — heap_caps_free, never the
    // opus_*_destroy wrappers (they route through the internal heap).
    if (opus_enc_) {
        heap_caps_free(opus_enc_);
        opus_enc_ = nullptr;
    }
    if (opus_dec_) {
        heap_caps_free(opus_dec_);
        opus_dec_ = nullptr;
    }
    opus_negotiated_ = false;
    opus_declared_ = false;
}

bool WsClient::sendCapabilitiesDeclaration() {
    if (!connected_ || !client_) return false;

    cJSON* root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "type", "signal");
    cJSON_AddStringToObject(root, "content", "capabilities");
    cJSON* metadata = cJSON_AddObjectToObject(root, "metadata");
    cJSON* enable = cJSON_AddArrayToObject(metadata, "enable");
    cJSON_AddItemToArray(enable, cJSON_CreateString("opus"));

    char* json_str = cJSON_PrintUnformatted(root);
    int len = strlen(json_str);
    int sent = esp_websocket_client_send_text(client_, json_str, len, pdMS_TO_TICKS(100));
    cJSON_free(json_str);
    cJSON_Delete(root);
    return sent == len;
}

void WsClient::enableOpus() {
    // Codec states (~25 KB encoder + ~18 KB decoder) live in PSRAM via the
    // placement-init APIs — mid-session internal-heap blocks that large are
    // not dependable (OPUS_ALLOC_FAIL was observed on hardware).
    opus_enc_ = (OpusEncoder*)heap_caps_malloc(opus_encoder_get_size(1), MALLOC_CAP_SPIRAM);
    if (!opus_enc_) {
        ESP_LOGE(TAG, "opus encoder state alloc failed — staying on PCM");
        return;
    }
    int err = opus_encoder_init(opus_enc_, CONFIG_MIC_SAMPLE_RATE, 1,
                                OPUS_APPLICATION_VOIP);
    if (err != OPUS_OK) {
        ESP_LOGE(TAG, "opus_encoder_init failed: %d — staying on PCM", err);
        heap_caps_free(opus_enc_);
        opus_enc_ = nullptr;
        return;
    }
    opus_encoder_ctl(opus_enc_, OPUS_SET_BITRATE(CONFIG_OPUS_BITRATE));
    // Complexity 5: the CoreS3 gate measured the server default (9) at 111%
    // of the 20 ms real-time budget; cx5 lands at 73% (see opus_bench data).
    opus_encoder_ctl(opus_enc_, OPUS_SET_COMPLEXITY(CONFIG_OPUS_COMPLEXITY));

    opus_dec_ = (OpusDecoder*)heap_caps_malloc(opus_decoder_get_size(1), MALLOC_CAP_SPIRAM);
    if (!opus_dec_) {
        ESP_LOGE(TAG, "opus decoder state alloc failed — staying on PCM");
        heap_caps_free(opus_enc_);
        opus_enc_ = nullptr;
        return;
    }
    err = opus_decoder_init(opus_dec_, CONFIG_SPK_SAMPLE_RATE, 1);
    if (err != OPUS_OK) {
        ESP_LOGE(TAG, "opus_decoder_init failed: %d — staying on PCM", err);
        heap_caps_free(opus_dec_);
        opus_dec_ = nullptr;
        heap_caps_free(opus_enc_);
        opus_enc_ = nullptr;
        return;
    }

    opus_negotiated_ = true;
    ESP_LOGI(TAG, "Opus negotiated (%u Hz up / %u Hz down, 20 ms, %d bps, cx%d)",
             CONFIG_MIC_SAMPLE_RATE, CONFIG_SPK_SAMPLE_RATE, CONFIG_OPUS_BITRATE,
             CONFIG_OPUS_COMPLEXITY);
}
