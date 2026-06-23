#pragma once

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include <cstdint>

/// Plays audio from a queue to I2S speaker output.
class AudioPlayback {
public:
    /// Initialize I2S for speaker output.
    /// @param spk_queue FreeRTOS queue to pull audio frames from.
    bool init(QueueHandle_t spk_queue);

    /// Start the playback task (pinned to audio core).
    void start();

    /// Stop playback and release I2S resources.
    void stop();

    /// Flush all buffered audio (on interrupt).
    void flush();

    /// Returns true if currently outputting audio.
    bool isPlaying() const { return playing_; }

private:
    static void playbackTask(void* arg);

    QueueHandle_t spk_queue_ = nullptr;
    TaskHandle_t task_ = nullptr;
    bool running_ = false;
    bool playing_ = false;
};
