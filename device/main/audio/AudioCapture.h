#pragma once

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include <cstdint>

/// Captures audio from I2S microphone and pushes Int16 PCM frames to a queue.
class AudioCapture {
public:
    /// Initialize I2S for microphone input.
    /// @param mic_queue FreeRTOS queue to push captured frames into.
    bool init(QueueHandle_t mic_queue);

    /// Start the capture task (pinned to audio core).
    void start();

    /// Stop capture and release I2S resources.
    void stop();

    /// Mute/unmute microphone (frames are still captured but zeroed).
    void setMute(bool muted) { muted_ = muted; }
    bool isMuted() const { return muted_; }

private:
    static void captureTask(void* arg);

    QueueHandle_t mic_queue_ = nullptr;
    TaskHandle_t task_ = nullptr;
    bool running_ = false;
    bool muted_ = false;
};
