#pragma once

#include "Session.h"
#include "net/WiFiManager.h"
#include "net/WsClient.h"
#include "audio/AudioCapture.h"
#include "audio/AudioPlayback.h"
#include "ui/Display.h"
#include "config.h"

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/stream_buffer.h"

/// Top-level orchestrator. Owns all components and queues,
/// manages the connection lifecycle and routes messages.
class Assistant {
public:
    /// Initialize all components and create queues.
    bool init();

    /// Start all tasks — begins streaming audio and processing messages.
    void start();

    /// Stop all tasks and disconnect.
    void stop();

    /// Get current session state.
    Session::State getState() const { return session_.getState(); }

private:
    void onWiFiConnected();
    void onWiFiDisconnected();
    void onWsAudio(const int16_t* pcm, size_t samples, uint32_t sample_rate);
    void onWsMessage(const WsMessage& msg);

    static void wsSendTask(void* arg);
    static void uiTask(void* arg);

    // Components
    Session session_;
    WiFiManager wifi_;
    WsClient ws_;
    AudioCapture capture_;
    AudioPlayback playback_;
    Display* display_ = nullptr;

    // Queues
    QueueHandle_t mic_queue_ = nullptr;   // AudioCapture → ws_send
    StreamBufferHandle_t spk_stream_ = nullptr;  // ws_recv → AudioPlayback (byte stream)
    QueueHandle_t event_queue_ = nullptr; // ws_recv → ui

    // Tasks
    TaskHandle_t ws_send_task_ = nullptr;
    TaskHandle_t ui_task_ = nullptr;

    // Push-to-talk: mic frames stream only while the button is held. wsSendTask
    // owns the release transition — it flushes the queued tail (bounded by
    // flush_frames_ captured at release) and sends end_of_utterance so the end
    // of speech isn't clipped.
    volatile bool talking_ = false;

    // Speaker stream: backend TTS audio is written as a byte stream (non-blocking)
    // from the WebSocket callback; the playback task reads fixed-size frames from it.
    // 32KB buffer ≈ 1s of 16kHz mono 16-bit audio, absorbs TTS delivery bursts.
    volatile bool eou_pending_ = false;
    volatile int flush_frames_ = 0;

    bool running_ = false;
};
