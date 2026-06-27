#pragma once

#include "driver/i2s_std.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include <cstdint>

/// Plays audio from a queue to I2S speaker output.
/// Receives its TX channel handle from AudioCapture (shared full-duplex bus).
class AudioPlayback {
public:
    /// Initialize playback with a pre-created I2S TX channel.
    /// @param spk_queue FreeRTOS queue to pull audio frames from.
    /// @param tx_channel I2S TX channel handle (owned by AudioCapture).
    bool init(QueueHandle_t spk_queue, i2s_chan_handle_t tx_channel);

    /// Start the playback task (pinned to audio core).
    void start();

    /// Stop playback (does not delete I2S channel — AudioCapture owns it).
    void stop();

    /// Flush all buffered audio (on interrupt).
    void flush();

    /// Returns true if currently outputting audio.
    bool isPlaying() const { return playing_; }

private:
    static void playbackTask(void* arg);

    QueueHandle_t spk_queue_ = nullptr;
    i2s_chan_handle_t tx_chan_ = nullptr;
    TaskHandle_t task_ = nullptr;
    bool running_ = false;
    bool playing_ = false;
};
