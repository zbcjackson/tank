#pragma once

#include "Session.h"
#include "net/WiFiManager.h"
#include "net/WsClient.h"
#include "audio/AudioCapture.h"
#include "audio/AudioPlayback.h"
#include "ui/Display.h"

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"

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
    QueueHandle_t spk_queue_ = nullptr;   // ws_recv → AudioPlayback
    QueueHandle_t event_queue_ = nullptr; // ws_recv → ui

    // Tasks
    TaskHandle_t ws_send_task_ = nullptr;
    TaskHandle_t ui_task_ = nullptr;

    // Push-to-talk: mic frames only stream while the button is held.
    volatile bool talking_ = false;

    bool running_ = false;
};
