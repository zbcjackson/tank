#pragma once

#include <cstddef>
#include <cstdint>

/// Wraps the esp-sr AFE (Audio Front End) pipeline for the CoreS3.
///
/// The AFE takes channel-interleaved [mic, ref] audio (mic first, the speaker
/// echo reference last) and runs, in one integrated pipeline:
///   - AEC (acoustic echo cancellation) using the hardware reference channel
///   - VAD (voice activity detection)
///   - WakeNet ("Hi ESP") wake-word detection
/// and produces a single channel of echo-cancelled audio plus wake/VAD state.
///
/// feed() and fetch() run on separate tasks: feed() hands raw interleaved frames
/// to the AFE's internal ring buffer; fetch() blocks until the AFE has a
/// processed output frame ready. This mirrors the esp-sr reference design.
class AfeProcessor {
public:
    /// Which esp-sr front-end to instantiate:
    ///   SR — Speech Recognition (esp_afe_sr_v1): AEC + VAD + WakeNet. Used for
    ///        PTT/wake turns so "Hi ESP" works. AEC is comparatively weak.
    ///   VC — Voice Communication (esp_afe_vc_v1): AEC + VAD, NO WakeNet, but a
    ///        stronger AEC suited to full-duplex. Used in call mode where turn
    ///        boundaries come from the backend VAD (wake word not needed).
    enum class Type { SR, VC };

    struct FetchResult {
        const int16_t* data = nullptr;  // Echo-cancelled mono audio (owned by AFE)
        int samples = 0;                // Samples in `data`
        bool wake_detected = false;     // WakeNet fired on this frame
        bool speech = false;            // VAD says this frame contains speech
        bool valid = false;            // false if fetch failed / AFE not ready
    };

    /// @param type Which front-end to build (SR = wakenet, VC = strong AEC).
    bool init(Type type = Type::SR);
    void destroy();

    /// Number of samples PER CHANNEL that feed() expects per call.
    int feedChunkSamples() const { return feed_chunk_samples_; }

    /// Total interleaved samples (all channels) feed() expects per call.
    int feedChunkTotal() const { return feed_chunk_samples_ * feed_channels_; }

    /// Feed one interleaved [mic, ref, ...] chunk of feedChunkTotal() samples.
    /// Returns false if the AFE isn't initialized.
    bool feed(const int16_t* interleaved);

    /// Block until the AFE produces a processed frame. Returns the cleaned audio
    /// and detection state. On the fetch task loop.
    FetchResult fetch();

    /// Runtime enable/disable of AEC (e.g. to A/B test or save CPU).
    void enableAec(bool enable);

    bool ready() const { return afe_data_ != nullptr; }

private:
    // Opaque esp-sr handles (kept as void* to keep esp-sr headers out of this
    // header — they pull in C-only declarations).
    const void* afe_iface_ = nullptr;   // const esp_afe_sr_iface_t*
    void* afe_data_ = nullptr;          // esp_afe_sr_data_t*
    void* models_ = nullptr;            // srmodel_list_t*

    int feed_chunk_samples_ = 0;        // per-channel samples per feed()
    int feed_channels_ = 0;             // total channels fed (mic + ref)
};
