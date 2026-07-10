#pragma once

#include "driver/i2s_std.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include <cstdint>
#include "config.h"

/// Captures audio from the I2S microphone and pushes Int16 PCM frames to a queue.
/// Also owns the full-duplex I2S bus (creates both TX and RX channel handles).
///
/// Two capture modes, selected at compile time:
///   - Standard (default): single mono channel, one 20ms mic frame per queue item
///     (CONFIG_MIC_FRAME_BYTES).
///   - AEC/TDM (CONFIG_AEC_ENABLE): reads the ES7210 in 4-slot TDM, keeps slot 0
///     (MIC1) and slot 2 (MIC3 = speaker echo reference), and pushes them
///     interleaved as [mic, ref, mic, ref, ...] — one queue item is
///     CONFIG_MIC_FRAME_BYTES * CONFIG_AFE_TOTAL_CH bytes, ready for AFE feed().
class AudioCapture {
public:
    /// Initialize I2S in full-duplex mode (creates both TX+RX channels on I2S_NUM_0).
    /// @param mic_queue FreeRTOS queue to push captured frames into.
    bool init(QueueHandle_t mic_queue);

    /// Start the capture task (pinned to audio core).
    void start();

    /// Stop capture and release I2S resources.
    void stop();

    /// Pause/resume I2S RX channel (for PTT: disable mic during playback).
    void pause();
    void resume();

    /// Get the TX channel handle (for AudioPlayback to use).
    /// Only valid after init() succeeds.
    i2s_chan_handle_t getTxChannel() const { return tx_chan_; }

    /// Mute/unmute microphone (frames are still captured but zeroed).
    void setMute(bool muted) { muted_ = muted; }
    bool isMuted() const { return muted_; }

private:
    static void captureTask(void* arg);

    QueueHandle_t mic_queue_ = nullptr;
    TaskHandle_t task_ = nullptr;
    i2s_chan_handle_t rx_chan_ = nullptr;
    i2s_chan_handle_t tx_chan_ = nullptr;
    bool running_ = false;
    bool muted_ = false;
    volatile bool paused_ = false;  // Capture always runs; PTT gating is in wsSendTask
};
