#pragma once

#include "driver/i2s_std.h"
#include "freertos/FreeRTOS.h"
#include "freertos/stream_buffer.h"
#include <cstdint>

/// Plays audio from a stream buffer to I2S speaker output.
/// Receives its TX channel handle from AudioCapture (shared full-duplex bus).
class AudioPlayback {
public:
    /// Initialize playback with a pre-created I2S TX channel.
    /// @param spk_stream StreamBuffer to read PCM audio bytes from.
    /// @param tx_channel I2S TX channel handle (owned by AudioCapture).
    bool init(StreamBufferHandle_t spk_stream, i2s_chan_handle_t tx_channel);

    /// Start the playback task (pinned to audio core).
    void start();

    /// Stop playback (does not delete I2S channel — AudioCapture owns it).
    void stop();

    /// Flush all buffered audio (on interrupt/new PTT press).
    void flush();

    /// Set software volume (0–100). Applied as PCM scaling before I2S output.
    void setVolume(uint8_t vol) { volume_ = vol; }

    /// Returns true if currently outputting audio.
    bool isPlaying() const { return playing_; }

private:
    static void playbackTask(void* arg);

    StreamBufferHandle_t spk_stream_ = nullptr;
    i2s_chan_handle_t tx_chan_ = nullptr;
    TaskHandle_t task_ = nullptr;
    bool running_ = false;
    bool playing_ = false;
    volatile uint8_t volume_ = 70;
};
