#pragma once

// Energy-based turn-end detector for wake-word mode.
//
// After the wake word fires there is no button release to end the turn, so we
// watch the mic stream and declare the utterance finished once we've seen a
// run of quiet frames following some speech. Two guards prevent false ends:
//   - min-speech floor: never end until at least some speech was observed, so
//     leading silence after the wake word doesn't immediately close the turn.
//   - max-listen cap: force an end after a hard time limit so a noisy room
//     can't stream forever.
//
// Pure logic — no ESP-IDF dependency — so it is covered by native tests.

#include <cstdint>
#include <cstddef>

class SilenceDetector {
public:
    struct Config {
        int16_t speech_rms;      // frame RMS above this counts as speech
        int silence_frames;      // consecutive quiet frames to end the turn
        int min_speech_frames;   // speech frames required before an end can fire
        int max_frames;          // hard cap on total frames before forcing end
    };

    explicit SilenceDetector(const Config& cfg) : cfg_(cfg) { reset(); }

    /// Feed one frame of `count` int16 samples. Returns true when the turn
    /// should end (either trailing silence after speech, or the max cap).
    bool update(const int16_t* samples, size_t count);

    /// Reset all counters — call when a new turn starts (wake word fires).
    void reset();

    /// True if the end fired because of the max-listen cap rather than silence.
    bool endedByCap() const { return ended_by_cap_; }

private:
    static int16_t frameRms(const int16_t* samples, size_t count);

    Config cfg_;
    int total_frames_;
    int speech_frames_;
    int trailing_silence_;
    bool ended_by_cap_;
};
