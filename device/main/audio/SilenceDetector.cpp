#include "SilenceDetector.h"

void SilenceDetector::reset() {
    total_frames_ = 0;
    speech_frames_ = 0;
    trailing_silence_ = 0;
    ended_by_cap_ = false;
}

int16_t SilenceDetector::frameRms(const int16_t* samples, size_t count) {
    if (!samples || count == 0) return 0;
    uint64_t sum_sq = 0;
    for (size_t i = 0; i < count; i++) {
        int32_t s = samples[i];
        sum_sq += static_cast<uint64_t>(s * s);
    }
    // Integer sqrt of the mean square.
    uint64_t mean_sq = sum_sq / count;
    uint32_t root = 0;
    uint32_t bit = 1u << 30;
    while (bit > mean_sq) bit >>= 2;
    uint64_t rem = mean_sq;
    while (bit != 0) {
        if (rem >= root + bit) {
            rem -= root + bit;
            root = (root >> 1) + bit;
        } else {
            root >>= 1;
        }
        bit >>= 2;
    }
    return static_cast<int16_t>(root);
}

bool SilenceDetector::update(const int16_t* samples, size_t count) {
    total_frames_++;

    const bool is_speech = frameRms(samples, count) >= cfg_.speech_rms;
    if (is_speech) {
        speech_frames_++;
        trailing_silence_ = 0;
    } else {
        trailing_silence_++;
    }

    // Hard cap regardless of speech content.
    if (cfg_.max_frames > 0 && total_frames_ >= cfg_.max_frames) {
        ended_by_cap_ = true;
        return true;
    }

    // End on trailing silence, but only after enough speech was heard.
    if (speech_frames_ >= cfg_.min_speech_frames &&
        trailing_silence_ >= cfg_.silence_frames) {
        return true;
    }

    return false;
}
