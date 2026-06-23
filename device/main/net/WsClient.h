#pragma once

#include "esp_websocket_client.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include <functional>
#include <cstdint>

/// Parsed JSON message from the server.
struct WsMessage {
    char type[20];       // "signal", "transcript", "text", "update", "error"
    char content[512];   // message content
    char msg_id[64];     // message ID (for text streaming)
    bool is_user;        // true if transcript from user
    bool is_final;       // true if message is complete
};

/// WebSocket client for Tank backend.
/// Handles binary audio frames and JSON control messages.
class WsClient {
public:
    using AudioCallback = std::function<void(const int16_t* pcm, size_t samples, uint32_t sample_rate)>;
    using MessageCallback = std::function<void(const WsMessage& msg)>;

    /// Initialize WebSocket client (does not connect yet).
    bool init(const char* host, int port, const char* session_id);

    /// Connect to the backend. Call after WiFi is ready.
    bool connect();

    /// Disconnect and clean up.
    void disconnect();

    /// Send binary audio frame (raw Int16 PCM, no header).
    bool sendAudio(const int16_t* pcm, size_t samples);

    /// Send JSON control message.
    bool sendJson(const char* type, const char* content);

    /// Send interrupt signal.
    bool sendInterrupt();

    /// Returns true if connected and ready.
    bool isConnected() const { return connected_; }

    /// Set callback for incoming audio (called from ws_recv context).
    void onAudio(AudioCallback cb) { on_audio_ = cb; }

    /// Set callback for incoming JSON messages.
    void onMessage(MessageCallback cb) { on_message_ = cb; }

private:
    static void eventHandler(void* arg, esp_event_base_t base, int32_t id, void* data);
    void handleData(esp_websocket_event_data_t* event_data);
    void parseJsonMessage(const char* data, int len);
    void parseAudioFrame(const uint8_t* data, int len);

    esp_websocket_client_handle_t client_ = nullptr;
    AudioCallback on_audio_;
    MessageCallback on_message_;
    bool connected_ = false;
    char uri_[256] = {};
};
