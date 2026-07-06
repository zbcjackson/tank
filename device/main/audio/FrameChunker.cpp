#include "FrameChunker.h"

FrameChunker::FrameChunker(size_t chunk_samples)
    : chunk_samples_(chunk_samples == 0 ? 1 : chunk_samples) {
    buffer_.reserve(chunk_samples_ * 2);
}

void FrameChunker::push(const int16_t* samples, size_t count) {
    if (!samples || count == 0) return;
    buffer_.insert(buffer_.end(), samples, samples + count);
}

bool FrameChunker::pop(int16_t* out) {
    if (!out || buffer_.size() < chunk_samples_) {
        return false;
    }
    for (size_t i = 0; i < chunk_samples_; i++) {
        out[i] = buffer_[i];
    }
    buffer_.erase(buffer_.begin(), buffer_.begin() + chunk_samples_);
    return true;
}
