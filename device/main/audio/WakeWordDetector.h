#pragma once

// On-device wake word detection via Espressif esp-sr (WakeNet9, stock "Hi ESP").
//
// Wraps the esp_srmodel / esp_wn_iface C API. Audio arrives as 320-sample
// (20ms) frames from AudioCapture, but WakeNet wants a fixed chunk size
// (get_samp_chunksize, 480 for WakeNet9), so a FrameChunker re-buffers the
// stream to WakeNet's cadence. feed() returns true once on each detection.
//
// esp-sr is only available in the ESP-IDF build, so the whole implementation
// is gated on the wake-word mode flag and excluded from native tests. The
// pure re-chunking logic it relies on (FrameChunker) is tested separately.

#include <cstdint>
#include <cstddef>

#include "FrameChunker.h"

class WakeWordDetector {
public:
    WakeWordDetector() = default;
    ~WakeWordDetector();

    /// Load the WakeNet model from the `model` flash partition and create the
    /// detector. Returns false if no wake word model is present.
    bool init();

    /// Feed one frame of int16 PCM (16kHz mono). Returns true on the frame
    /// where the wake word is detected. Safe to call before init() (no-op).
    bool feed(const int16_t* samples, size_t count);

    /// Discard any buffered audio so the next feed() starts from a clean slate.
    /// Call when suppressing detection (e.g. after playback) so partial chunks
    /// captured during the assistant's own speech can't complete into a match.
    void reset();

    /// Whether init() succeeded and the detector is live.
    bool ready() const { return data_ != nullptr; }

private:
    // esp-sr handles held as void* so esp-sr headers stay out of this header
    // (esp_wn_iface_t is a typedef'd anonymous struct — a forward declaration
    // would not match). Cast to the real types in the .cpp.
    const void* iface_ = nullptr;   // const esp_wn_iface_t*
    void* data_ = nullptr;          // model_iface_data_t*
    void* models_ = nullptr;        // srmodel_list_t*
    FrameChunker* chunker_ = nullptr;
    int chunk_samples_ = 0;
};
