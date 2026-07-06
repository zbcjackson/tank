#pragma once

// Re-chunks a stream of int16 PCM samples into fixed-size chunks.
//
// WakeNet requires exactly get_samp_chunksize() samples per detect() call
// (480 for WakeNet9 @ 16kHz), but AudioCapture delivers 320-sample frames.
// FrameChunker buffers incoming samples and hands back full chunks as they
// accumulate, carrying the remainder to the next push.
//
// Pure logic — no ESP-IDF dependency — so it is covered by native tests.

#include <cstdint>
#include <cstddef>
#include <vector>

class FrameChunker {
public:
    /// @param chunk_samples Number of int16 samples per emitted chunk (> 0).
    explicit FrameChunker(size_t chunk_samples);

    /// Append `count` samples from `samples` to the internal buffer.
    void push(const int16_t* samples, size_t count);

    /// If at least one full chunk is buffered, copy it into `out` (which must
    /// hold chunk_samples() int16 values), consume it, and return true.
    /// Otherwise return false. Call in a loop to drain all ready chunks.
    bool pop(int16_t* out);

    /// Number of samples per chunk.
    size_t chunkSamples() const { return chunk_samples_; }

    /// Number of buffered samples not yet emitted as a chunk.
    size_t pending() const { return buffer_.size(); }

    /// Drop all buffered samples (e.g. on turn boundary).
    void reset() { buffer_.clear(); }

private:
    size_t chunk_samples_;
    std::vector<int16_t> buffer_;
};
