#pragma once

#include "Session.h"
#include "net/WiFiManager.h"
#include "net/WsClient.h"
#include "audio/AudioCapture.h"
#include "audio/AudioPlayback.h"
#if CONFIG_AEC_ENABLE
#include "audio/AfeProcessor.h"
#else
#include "audio/WakeWordDetector.h"
#endif
#include "audio/SilenceDetector.h"
#include "ui/Display.h"
#include "hal/BoardHAL.h"
#include "settings/NvsSettings.h"
#include "settings/SerialConfig.h"
#include "config.h"

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/stream_buffer.h"

/// Top-level orchestrator. Owns all components and queues,
/// manages the connection lifecycle and routes messages.
class Assistant {
public:
    /// Initialize all components and create queues.
    /// @param hal Board hardware abstraction (for volume control, etc.)
    bool init(BoardHAL* hal);

    /// Start all tasks — begins streaming audio and processing messages.
    void start();

    /// Stop all tasks and disconnect.
    void stop();

    /// Get current session state.
    Session::State getState() const { return session_.getState(); }

private:
    void onWiFiConnected();
    void onWiFiDisconnected();
    void onWsConnected();
    void onWsDisconnected();
    void onWsAudio(const int16_t* pcm, size_t samples, uint32_t sample_rate);
    void onWsMessage(const WsMessage& msg);

    static void wsSendTask(void* arg);
    static void uiTask(void* arg);
#if CONFIG_AEC_ENABLE
    static void afeFeedTask(void* arg);   // mic_queue → afe.feed()
    static void afeFetchTask(void* arg);  // afe.fetch() → wake/VAD + clean_queue
#if CONFIG_AEC_TEST_TONE
    static void testToneTask(void* arg);  // boot-time 1kHz tone for AEC self-test
#endif
#endif

    // Components
    Session session_;
    WiFiManager wifi_;
    WsClient ws_;
    AudioCapture capture_;
    AudioPlayback playback_;
#if CONFIG_AEC_ENABLE
    AfeProcessor afe_;
#else
    WakeWordDetector wake_word_;
#endif
    Display* display_ = nullptr;
    BoardHAL* hal_ = nullptr;
    NvsSettings nvs_;
    SerialConfig serial_config_;

    // Queues
    QueueHandle_t mic_queue_ = nullptr;   // AudioCapture → afe feed / ws_send
    StreamBufferHandle_t spk_stream_ = nullptr;  // ws_recv → AudioPlayback (byte stream)
    QueueHandle_t event_queue_ = nullptr; // ws_recv → ui
#if CONFIG_AEC_ENABLE
    QueueHandle_t clean_queue_ = nullptr; // afe fetch → ws_send (echo-cancelled mono)
#if !CONFIG_AEC_HW_REF
    StreamBufferHandle_t ref_stream_ = nullptr; // playback → afe feed (software echo ref)
#endif
#endif

    // Tasks
    TaskHandle_t ws_send_task_ = nullptr;
    TaskHandle_t ui_task_ = nullptr;
#if CONFIG_AEC_ENABLE
    TaskHandle_t afe_feed_task_ = nullptr;
    TaskHandle_t afe_fetch_task_ = nullptr;
    // Set by afeFetchTask when WakeNet fires; consumed by wsSendTask to open a
    // wake turn. AEC lets WakeNet run even during playback (no echo hangover).
    volatile bool wake_pending_ = false;
#endif

    // Push-to-talk state
    volatile bool talking_ = false;
    volatile bool eou_pending_ = false;
    volatile int drain_frames_ = 0;  // Frames to drain after release before EOU
    // How the current turn started: true = wake-word (ends on trailing silence),
    // false = PTT/none (ends on button release). Only meaningful while talking_.
    volatile bool wake_turn_ = false;

    bool running_ = false;
};
